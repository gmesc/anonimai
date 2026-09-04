# -*- coding: utf-8 -*-
"""
App locale per l'anonimizzazione reversibile di documenti con il modello PII.

Flusso d'uso:
  1) ANONIMIZZA  - incolli testo o carichi un PDF; il modello + una rete regex/checksum
     trovano le PII. Ogni entita' riceve un ID univoco e reversibile: [FULLNAME_1],
     [IBAN_1], ... (valori uguali condividono lo stesso ID).
  2) COPIA       - copi il testo anonimizzato e lo incolli in ChatGPT/altro LLM.
  3) RIPRISTINA  - incolli la risposta dell'LLM (che contiene i placeholder) e l'app
     rimette i valori veri usando il dizionario locale.

Tutto in locale: il testo e il dizionario {placeholder -> valore} non lasciano la macchina.

Il modello e' affiancato da una rete REGEX + CHECKSUM (EMAIL, TELEFONO, IBAN, CF, PIVA,
carta di credito, importi, targhe, URL). Le entita' validate matematicamente (IBAN/CF/
PIVA/carta) hanno priorita' sul modello in caso di sovrapposizione.

Il dizionario di ripristino si puo' DISATTIVARE (switch nell'UI, --no-mapping, PII_MAPPING=0):
l'anonimizzazione diventa definitiva, nessuna chiave placeholder->valore viene costruita.

Endpoint HTTP:
  GET  /health    liveness/readiness senza inference (200 = modello caricato, 503 = no)
  POST /analyze   {"text": ...} oppure multipart con un file (.pdf/.md/.txt); campi
                  opzionali "exclude_tags" e "include_mapping" per override per-richiesta
  POST /pdf       stesso input di /analyze -> scarica il PDF ANONIMIZZATO (redazione
                  vera del PDF caricato, oppure PDF ricostruito dal testo). Campo
                  opzionale "manual_boxes": riquadri {page,x0,y0,x1,y1} in frazioni
                  0-1 da oscurare (firme/timbri); con i riquadri funziona anche
                  senza PII testuali. I PDF-scansione passano dall'OCR (vedi
                  pdf_export.py: serve la cartella tessdata, env PII_TESSDATA)
  POST /preview   multipart con un .pdf -> lo tiene in memoria per l'ANTEPRIMA a video e
                  ritorna {doc_id, n_pages, text}
  POST /pdf/preview  come /pdf, ma invece del binario ritorna {doc_id, n_pages, ...}:
                  il PDF anonimizzato resta in memoria e si guarda pagina per pagina
  GET  /doc/<id>/page/<n>.png   pagina renderizzata (anteprima a video)
  GET  /doc/<id>/file.pdf       download del documento tenuto in memoria
  GET  /settings  legenda dei 23 tag, tag esclusi, stato del dizionario reversibile
  POST /settings  {"excluded_tags": [...], "mapping_enabled": bool} -> salva in prefs.json
                  (/tags e' un alias storico degli stessi due endpoint)
  GET  /config, POST /config, GET /port-check   host/porta del server

Avvio:  python app.py   ->   http://127.0.0.1:5005
Configurazione host/porta (precedenza): CLI --host/--port > env PII_HOST/PII_PORT >
  config.json (vedi server_config.py) > default 127.0.0.1:5005
Preferenze di anonimizzazione (precedenza): campo nella richiesta > CLI --exclude-tags/
  --no-mapping > env PII_EXCLUDE_TAGS/PII_MAPPING > prefs.json > default
"""

import bisect
import os
import re
import secrets
import sys
import threading
from collections import OrderedDict
from pathlib import Path

import fitz  # PyMuPDF
import torch
from flask import (Flask, jsonify, render_template_string, request,
                   send_from_directory)

import pdf_export
import server_config
# Rete REGEX + CHECKSUM: modulo a parte, senza dipendenze dal modello. I nomi
# restano importabili da qui (`app.detect_regex`) per non rompere chi li usa.
from detectors import (DETECTORS, SOFT_REGEX_LABELS, avs_ok, cf_ok,  # noqa: F401
                       detect_iban, detect_regex, iban_ok, luhn_ok,
                       match_custom_terms, piva_ok)
from transformers import pipeline


def _resource_path(rel):
    """Percorso risorsa valido sia in sviluppo sia dentro l'exe PyInstaller."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


# MODELLO usato dall'app. Accetta tre forme, provate in quest'ordine:
#   "1.2.0"  -> models/rizzo-pii-0.3B-v1.2.0/   (versione di un run di training)
#   "main"   -> models/rizzo-pii-0.3B-main/     (revision scaricata da HF, senza numero)
#   percorso -> usato tal quale (assoluto o relativo alla root della repo)
# Metti None per usare AUTOMATICAMENTE l'ultima versione `-v*` disponibile.
APP_MODEL_VERSION = "1.5.0"

# Dentro l'exe il modello e' impacchettato come "pii_model" (vedi build.spec).
# In sviluppo: pin sopra -> auto-ultima versione -> vecchio non versionato -> legacy.
# Override puntuale a runtime: env PII_MODEL_DIR.
if getattr(sys, "_MEIPASS", None):
    MODEL_DIR = _resource_path("pii_model")
elif os.environ.get("PII_MODEL_DIR"):
    MODEL_DIR = os.environ["PII_MODEL_DIR"]
else:
    import re
    _models = Path(__file__).resolve().parents[2] / "models"
    _cands = []
    if APP_MODEL_VERSION:
        _cands = [_models / f"rizzo-pii-0.3B-v{APP_MODEL_VERSION}",
                  _models / f"rizzo-pii-0.3B-{APP_MODEL_VERSION}"]
        if os.sep in APP_MODEL_VERSION or "/" in APP_MODEL_VERSION:   # e' un percorso
            _cands += [Path(APP_MODEL_VERSION), _models.parent / APP_MODEL_VERSION]
    _pinned = next((p for p in _cands if p.is_dir()), None)
    _versioned = [p for p in _models.glob("rizzo-pii-0.3B-v*") if p.is_dir()]
    if _pinned:
        MODEL_DIR = str(_pinned)
    elif _versioned:
        MODEL_DIR = str(max(_versioned, key=lambda p: tuple(
            int(x) for x in re.search(r"-v([0-9][0-9.]*)$", p.name).group(1).split("."))))
    else:
        _prod = _models / "rizzo-pii-0.3B"
        MODEL_DIR = str(_prod if _prod.exists() else _models / "pii_model_legacy")

# Se la cartella non c'e', dirlo QUI e con il comando giusto: senza questo controllo si
# arriva a from_pretrained() con un path inventato (pii_model_legacy, ultimo fallback) e
# l'errore parla di una cartella che l'utente non ha mai sentito nominare.
if not getattr(sys, "_MEIPASS", None) and not os.path.isdir(MODEL_DIR):
    _v = APP_MODEL_VERSION or "1.5.0"
    print(f"ERRORE: modello non trovato in {MODEL_DIR}\n"
          f"Scaricalo con (la revision e la cartella devono combaciare):\n"
          f"  hf download rizzoaiacademy/rizzo-pii-0.3B --revision v{_v} "
          f"--local-dir models/rizzo-pii-0.3B-v{_v}\n"
          f"Oppure indica una cartella tua con la variabile PII_MODEL_DIR.",
          file=sys.stderr)
    sys.exit(2)

ASSETS_DIR = _resource_path("assets")   # icone / font / tokens (serviti su /assets/<file>)
APP_VERSION = "2.0.0"                    # versione mostrata nell'UI (allineata a tauri.conf.json)
MAX_WORDS = 120      # parole per chunk (~180 subword, sotto i 512 del training)
OVERLAP = 20         # parole di sovrapposizione tra chunk consecutivi

# --------------------------------------------------------------------------- #
# Caricamento modello (una sola volta all'avvio)
# --------------------------------------------------------------------------- #
device = 0 if torch.cuda.is_available() else -1
print(f"Carico il modello da {MODEL_DIR} su {'GPU' if device == 0 else 'CPU'}...")
nlp = pipeline(
    "token-classification",
    model=MODEL_DIR,
    tokenizer=MODEL_DIR,
    aggregation_strategy="simple",
    device=device,
)
print("Modello pronto.")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

# Estensioni accettate dall'upload (il PDF passa da PyMuPDF, il resto e' testo puro).
TEXT_EXTS = {".md", ".markdown", ".txt", ".text"}

# --------------------------------------------------------------------------- #
# Anteprima a video dei PDF (documento caricato a sinistra, anonimizzato a destra)
#
# I PDF vengono renderizzati QUI, con PyMuPDF, e serviti come PNG per pagina: non
# serve un viewer PDF nel browser (WebView2/WKWebView dentro Tauri non lo hanno in
# modo affidabile) ne' una libreria JS esterna (l'app e' offline, niente CDN).
#
# I documenti restano in memoria (mai su disco: valgono quanto il documento stesso)
# in una LRU piccola, e muoiono con il processo. Il render di una pagina e' pigro e
# poi tenuto in cache: aprire un PDF di 200 pagine non costa 200 render.
# --------------------------------------------------------------------------- #
PREVIEW_DPI = 110          # ~1150 px di larghezza su un A4: leggibile senza pesare
MAX_HIRES_PAGES = 8        # pagine ad ALTO dpi tenute per documento (una A4 a 220 dpi
                           # e' 1-3 MB: senza tetto un documento lungo gonfia lo store)
MAX_DOCS = 6               # documenti tenuti in memoria (LRU, i piu' vecchi cadono)

_DOCS = OrderedDict()      # doc_id -> {"pdf": bytes, "pages": {n: png}, "n_pages", "name"}
_DOCS_LOCK = threading.Lock()


def _safe_name(name, default="documento.pdf"):
    """Nome file pulito per Content-Disposition (ASCII, niente separatori)."""
    base = os.path.basename(name or "").strip()
    base = re.sub(r"[^A-Za-z0-9._\- ]+", "_", base).strip(" ._")
    return base or default


def _store_doc(data, name="documento.pdf"):
    """Mette un PDF nello store dell'anteprima. Ritorna (doc_id, n_pages)."""
    with fitz.open(stream=data, filetype="pdf") as doc:
        n_pages = doc.page_count
    doc_id = secrets.token_urlsafe(12)
    with _DOCS_LOCK:
        _DOCS[doc_id] = {"pdf": data, "pages": OrderedDict(), "n_pages": n_pages,
                         "name": _safe_name(name)}
        while len(_DOCS) > MAX_DOCS:
            _DOCS.popitem(last=False)
    return doc_id, n_pages


def _get_doc(doc_id):
    with _DOCS_LOCK:
        d = _DOCS.get(doc_id)
        if d is not None:
            _DOCS.move_to_end(doc_id)          # LRU: l'uso lo tiene in vita
    return d


def _page_png(d, n, dpi=PREVIEW_DPI):
    """PNG della pagina n (0-based) del documento, con cache per (pagina, dpi).

    Le pagine al dpi di default restano tutte (sono l'anteprima, si guardano
    scorrendo); quelle ad ALTO dpi — chieste dallo zoom, e quattro volte piu'
    pesanti — sono tenute a un tetto: le piu' vecchie cadono. Resta tutto in
    RAM e muore col processo, come il documento (invariante 6)."""
    if not (0 <= n < d["n_pages"]):
        return None
    key = (n, dpi)
    png = d["pages"].get(key)
    if png is None:
        with fitz.open(stream=d["pdf"], filetype="pdf") as doc:
            png = doc.load_page(n).get_pixmap(dpi=dpi).tobytes("png")
        d["pages"][key] = png
        if dpi != PREVIEW_DPI:
            hires = [k for k in d["pages"] if k[1] != PREVIEW_DPI]
            for old in hires[:-MAX_HIRES_PAGES]:
                d["pages"].pop(old, None)
    return png


# --------------------------------------------------------------------------- #
# Legenda dei tag + tag esclusi dall'anonimizzazione
#
# I 22 tag del modello (docs/TASSONOMIA_TAG.md) + URL, che e' solo-regex: il modello
# non e' stato addestrato su di esso, lo trova la rete regex.
# L'utente puo' DESELEZIONARE un tag: le entita' di quel tipo vengono rilevate ma non
# sostituite (restano in chiaro). Serve a chi deve confrontare gli importi (AMOUNT) o
# tenere eta'/sesso in un caso clinico.
# --------------------------------------------------------------------------- #
TAGS = [
    ("FULLNAME", "Nome di persona (anche ruoli legali: giudice, avvocato, parti, teste)",
     "Person name (legal roles included: judge, lawyer, parties, witness)", "Mario Rossi"),
    ("AGE", "Età", "Age", "45 anni"),
    ("GENDER", "Sesso / genere", "Sex / gender", "Femmina"),
    ("DATE", "Data di calendario", "Calendar date", "12/06/1985"),
    ("TIME", "Ora", "Time of day", "ore 15:30"),
    ("STREET", "Via / piazza / corso", "Street / square", "Via Garibaldi"),
    ("BUILDINGNUM", "Numero civico", "Building number", "24"),
    ("ZIPCODE", "CAP / NAP svizzero", "ZIP / Swiss postal code (NAP)", "00185 · CH-6600"),
    ("CITY", "Città", "City", "Milano"),
    ("PROVINCE", "Provincia / Cantone svizzero", "Province / Swiss canton", "MI · Canton Ticino"),
    ("EMAIL", "Email, PEC inclusa", "Email, certified mail included", "m.rossi@studio.it"),
    ("TELEPHONENUM", "Numero di telefono", "Phone number", "+39 333 1234567"),
    ("CF", "Codice fiscale (checksum verificato)", "Italian tax code (checksum verified)",
     "RSSMRA85H12F205Z"),
    ("PIVA", "Partita IVA (checksum verificato)", "VAT number (checksum verified)", "12345678901"),
    ("ID_DOC", "Numero di documento d'identità (carta, passaporto, patente, n. AVS)",
     "Identity document number (ID card, passport, driving licence, Swiss AVS number)",
     "CA12345AB · 756.1234.5678.97"),
    ("IBAN", "IBAN / numero di conto (checksum verificato)",
     "IBAN / account number (checksum verified)", "IT60X0542811101000000123456"),
    ("CREDITCARDNUMBER", "Numero di carta di credito (Luhn verificato)",
     "Credit card number (Luhn verified)", "4111 1111 1111 1111"),
    ("AMOUNT", "Importo in denaro", "Money amount", "€ 12.500,00"),
    ("TARGA", "Targa di veicolo (anche svizzera)", "Vehicle plate (Swiss included)",
     "AB 123 CD · TI 123456"),
    ("ORG", "Ragione sociale privata: società, studio legale, banca",
     "Private organization: company, law firm, bank", "Edilnord S.r.l."),
    ("DOCID", "Codice di un atto: ruolo generale, protocollo, repertorio, sentenza",
     "Document code: case number, protocol, repertoire, judgment", "1234/2024"),
    ("CATASTO", "Dati catastali: foglio, particella, subalterno",
     "Land registry data: sheet, parcel, subordinate", "Foglio 12, part. 345, sub. 6"),
    ("URL", "Indirizzo web (rilevato solo dalla rete regex, non dal modello)",
     "Web address (regex net only, not from the model)", "https://www.studiorossi.it"),
]
TAG_NAMES = [t[0] for t in TAGS]

# Preferenze di default del server (env > prefs.json). Gli argomenti CLI le sovrascrivono
# all'avvio; ogni singola richiesta puo' comunque passare le proprie.
#
# MAPPING_ENABLED = False -> l'anonimizzazione e' DEFINITIVA: nessun dizionario
# placeholder->valore viene costruito, restituito o salvato, e la risposta non contiene
# piu' il testo originale delle entita' (nemmeno dentro `segments`). Serve a chi non
# vuole che una chiave di ripristino esista, da nessuna parte.
_prefs = server_config.load_prefs()
EXCLUDED_TAGS = _prefs["excluded_tags"]
MAPPING_ENABLED = _prefs["mapping_enabled"]
# Termini personali: valori letterali che l'utente vuole SEMPRE rilevati, col
# loro tag (anche una label nuova: il placeholder e i colori sono per-label).
CUSTOM_TERMS = _prefs["custom_terms"]


# --------------------------------------------------------------------------- #
# Chunking word-safe + inferenza del modello su tutto il documento
# --------------------------------------------------------------------------- #
def chunk_text(text, max_words=MAX_WORDS, overlap=OVERLAP):
    """Ritorna [(sottostringa, offset_char_globale), ...] senza tagliare parole."""
    words = list(re.finditer(r"\S+", text))
    if not words:
        return []
    chunks, i = [], 0
    step = max(1, max_words - overlap)
    while i < len(words):
        block = words[i:i + max_words]
        start, end = block[0].start(), block[-1].end()
        chunks.append((text[start:end], start))      # slice esatto -> offset diretti
        if i + max_words >= len(words):
            break
        i += step
    return chunks


def detect_model(text):
    """Entita' trovate dal modello mmBERT su tutti i chunk, su offset globali."""
    chunks = chunk_text(text)
    ents = []
    if chunks:
        results = nlp([c for c, _ in chunks])
        if isinstance(results, dict):                 # singolo chunk -> normalizza
            results = [results]
        for (_, off), res in zip(chunks, results):
            for e in res:
                ents.append({
                    "label": e["entity_group"],
                    "start": int(e["start"]) + off,
                    "end": int(e["end"]) + off,
                    "score": float(e["score"]),
                    "validated": False,
                    "source": "modello",
                })
    return ents, len(chunks)


# --------------------------------------------------------------------------- #
# Fusione modello + regex, ID reversibili, testo anonimizzato
# --------------------------------------------------------------------------- #
def _is_word(ch):
    """Carattere interno a una parola (lettere accentate e cifre incluse)."""
    return ch.isalnum() or ch == "_"


def _merge(cands, text):
    """Greedy senza overlap. Priorita': checksum-valido > regex (non soft) > score
    > lunghezza.
    La rete regex copre campi a forma molto specifica: per quegli span e' piu' affidabile
    del modello (evita la frammentazione di CF/IBAN/carta in piu' pezzi). Fanno eccezione
    i tag in SOFT_REGEX_LABELS, dove la forma non ha un checksum a confermarla."""
    order = sorted(
        cands,
        key=lambda e: (1 if e["source"] == "utente" else 0,   # Termini personali: sopra tutto
                       1 if e["validated"] else 0,
                       1 if (e["source"] == "regex"
                             and e["label"] not in SOFT_REGEX_LABELS) else 0,
                       e["score"], e["end"] - e["start"]),
        reverse=True,
    )
    kept = []
    for e in order:
        # kept resta ordinata per start e senza sovrapposizioni: allora un candidato puo'
        # accavallarsi solo con i due vicini, che la ricerca binaria trova subito. Il
        # confronto con TUTTA kept era O(n^2): su un documento con 40.000 entita' (una chat
        # esportata di qualche MB) erano 111 s spesi qui, dopo l'inferenza.
        i = bisect.bisect_right(kept, e["start"], key=lambda k: k["start"])
        if (i and kept[i - 1]["end"] > e["start"]) or \
           (i < len(kept) and kept[i]["start"] < e["end"]):
            continue
        kept.insert(i, e)
    # niente spazi inglobati nei placeholder (il modello a volte include lo spazio iniziale)
    for e in kept:
        while e["start"] < e["end"] and text[e["start"]].isspace():
            e["start"] += 1
        while e["end"] > e["start"] and text[e["end"] - 1].isspace():
            e["end"] -= 1
    kept = [e for e in kept if e["end"] > e["start"]]

    # Allineamento ai confini di parola. Il modello etichetta i sotto-token e a volte ne
    # copre solo una parte ("No" di "Novara"): sostituendo la span cosi' com'e' resterebbe
    # "[CITY_1]vara", cioe' un valore ancora ricostruibile. Se una span taglia una parola
    # a meta', la si estende fino a coprirla. Nel dubbio si maschera un carattere in piu':
    # per un anonimizzatore l'errore per eccesso e' l'unico accettabile.
    for e in kept:
        while (e["start"] > 0
               and _is_word(text[e["start"] - 1]) and _is_word(text[e["start"]])):
            e["start"] -= 1
        while (e["end"] < len(text)
               and _is_word(text[e["end"]]) and _is_word(text[e["end"] - 1])):
            e["end"] += 1

    # L'estensione puo' rendere due span sovrapposte o adiacenti: si fondono, altrimenti
    # una stessa parola verrebbe sostituita due volte ("[CATASTO_1][CATASTO_2]").
    kept.sort(key=lambda e: (e["start"], -(e["end"] - e["start"])))
    merged = []
    for e in kept:
        if merged and e["start"] < merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], e["end"])
            continue
        if merged and e["start"] == merged[-1]["end"] and e["label"] == merged[-1]["label"]:
            merged[-1]["end"] = e["end"]
            continue
        merged.append(e)
    return merged


def _norm(s):
    return re.sub(r"\s+", " ", s.strip()).casefold()


def analyze(text, excluded=None, mapping_enabled=True):
    """excluded = tag da NON anonimizzare: le entita' di quel tipo vengono scartate
    prima della fusione, quindi il valore resta in chiaro nel testo di output.

    mapping_enabled=False -> anonimizzazione DEFINITIVA: nessun dizionario
    placeholder->valore, e i segmenti-entita' non riportano il testo originale
    (che altrimenti permetterebbe di ricostruire il dizionario dalla risposta).
    La numerazione dei placeholder resta: dice che due occorrenze sono lo stesso
    soggetto, ma da sola non fa risalire al valore."""
    excluded = set(excluded or ())
    model_ents, n_chunks = detect_model(text)
    cands = model_ents + detect_regex(text) + match_custom_terms(text, CUSTOM_TERMS)
    if excluded:
        cands = [e for e in cands if e["label"] not in excluded]
    kept = _merge(cands, text)

    # ID reversibili: stesso (label, valore-normalizzato) -> stesso placeholder.
    counters, seen, mapping = {}, {}, {}
    for e in kept:
        val = text[e["start"]:e["end"]]
        key = (e["label"], _norm(val))
        if key in seen:
            e["ph"] = seen[key]
        else:
            counters[e["label"]] = counters.get(e["label"], 0) + 1
            ph = f"[{e['label']}_{counters[e['label']]}]"
            seen[key] = ph
            if mapping_enabled:
                mapping[ph] = val
            e["ph"] = ph

    # segmenti per la preview + testo anonimizzato + statistiche
    segments, anon, by_label, by_source, pos = [], [], {}, {}, 0
    for e in kept:
        if e["start"] > pos:
            segments.append({"t": text[pos:e["start"]]})
            anon.append(text[pos:e["start"]])
        seg = {
            "label": e["label"],
            "ph": e["ph"],
            "src": e["source"],
            "validated": e["validated"],
        }
        if mapping_enabled:                       # senza dizionario niente valore originale
            seg["t"] = text[e["start"]:e["end"]]
        segments.append(seg)
        anon.append(e["ph"])
        by_label[e["label"]] = by_label.get(e["label"], 0) + 1
        by_source[e["source"]] = by_source.get(e["source"], 0) + 1
        pos = e["end"]
    if pos < len(text):
        segments.append({"t": text[pos:]})
        anon.append(text[pos:])

    return {
        "segments": segments,
        "anonymized_text": "".join(anon),
        "mapping": mapping,
        "mapping_enabled": mapping_enabled,
        "n_chunks": n_chunks,
        "n_chars": len(text),
        "n_entities": len(kept),
        "n_unique": len(seen),
        "by_label": dict(sorted(by_label.items(), key=lambda x: -x[1])),
        "by_source": by_source,
        "excluded_tags": sorted(excluded),
    }


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
def _page():
    return PAGE.replace("__VERSION__", APP_VERSION)


@app.route("/")
def index():
    return _page()


@app.route("/assets/<path:fn>")
def assets(fn):
    if os.path.isfile(os.path.join(ASSETS_DIR, fn)):
        return send_from_directory(ASSETS_DIR, fn)
    return ("", 404)


@app.route("/favicon.ico")
def favicon():
    if os.path.isfile(os.path.join(ASSETS_DIR, "detective.png")):
        return send_from_directory(ASSETS_DIR, "detective.png")
    return ("", 204)


@app.errorhandler(404)
def not_found(_e):
    return _page()


@app.route("/health")
@app.route("/healthz")
def health():
    """Liveness/readiness SENZA inference: sonda economica per orchestratori e sidecar.
    200 = modello caricato e pronto; 503 = server su ma modello non disponibile."""
    ready = nlp is not None
    body = {
        "status": "ok" if ready else "loading",
        "model_loaded": ready,
        "model": os.path.basename(str(MODEL_DIR).rstrip("/\\")),
        "model_version": APP_MODEL_VERSION,
        "app_version": APP_VERSION,
        "device": "cuda" if device == 0 else "cpu",
        "tags": len(TAG_NAMES),
        "excluded_tags": EXCLUDED_TAGS,
        "mapping_enabled": MAPPING_ENABLED,
        "ocr": pdf_export.ocr_available(),
    }
    return jsonify(body), (200 if ready else 503)


def _is_pdf(name, data):
    return os.path.splitext((name or "").lower())[1] == ".pdf" or data[:5] == b"%PDF-"


def _text_from_bytes(name, data):
    """Testo dai bytes di un upload: PDF via PyMuPDF, .md/.txt come testo puro.
    Per i PDF passa dall'OCR dove serve (scansioni, carta intestata come
    immagine): stessa lente della redazione, vedi pdf_export.page_textpage."""
    name = (name or "").lower()
    ext = os.path.splitext(name)[1]
    if _is_pdf(name, data):
        with fitz.open(stream=data, filetype="pdf") as doc:
            return "\n".join(pdf_export.extract_page_text(page) for page in doc)
    if ext in TEXT_EXTS or not ext:
        for enc in ("utf-8-sig", "utf-16", "latin-1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
    raise ValueError(
        f"Formato non supportato: {ext or name or 'sconosciuto'}. "
        "Accetto .pdf, .md, .txt oppure testo incollato."
    )


def _extract_upload(fs):
    """Testo da un file caricato (consuma lo stream)."""
    return _text_from_bytes(fs.filename, fs.read())


def _uploaded_file():
    """Il file dell'upload, se c'e'. "pdf" e' il nome storico del campo (l'UI lo
    usa ancora), "file" e' l'alias nuovo."""
    return next((request.files[k] for k in ("pdf", "file")
                 if k in request.files and request.files[k].filename), None)


@app.route("/analyze", methods=["POST"])
def analyze_route():
    up = _uploaded_file()
    was_pdf = up is not None and _is_pdf(up.filename, b"")
    if up is not None:
        try:
            text = _extract_upload(up)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:                       # PDF corrotto / protetto
            return jsonify({"error": f"Impossibile leggere il file: {e}"}), 400
        raw_excl = request.form.get("exclude_tags")
        raw_map = request.form.get("include_mapping")
    else:
        payload = request.get_json(silent=True) or {}
        text = payload.get("text", "")
        raw_excl = payload.get("exclude_tags")
        raw_map = payload.get("include_mapping")

    text = (text or "").strip()
    if not text:
        return jsonify({"error": "Nessun testo da analizzare."
                        + _ocr_hint(was_pdf)}), 400

    # override per-richiesta; senza override vale la configurazione del server
    excl = server_config.parse_tag_list(raw_excl) if raw_excl is not None else EXCLUDED_TAGS
    keep_map = (server_config.parse_bool(raw_map, MAPPING_ENABLED)
                if raw_map is not None else MAPPING_ENABLED)
    out = analyze(text, excl, keep_map)
    out["source_text"] = text
    return jsonify(out)


# --------------------------------------------------------------------------- #
# PDF anonimizzato da scaricare (issue #7, punto 1)
# --------------------------------------------------------------------------- #
def _pdf_response(data, report, redactions, filename="documento_anonimizzato.pdf"):
    """Risposta binaria + intestazioni diagnostiche. X-PII-Residual e
    X-PII-Skipped sono le due che l'UI trasforma in AVVISO: valori del documento
    che, per motivi diversi, sono rimasti in chiaro."""
    resp = app.response_class(data, mimetype="application/pdf")
    resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    resp.headers["X-PII-Redactions"] = str(redactions)
    resp.headers["X-PII-Residual"] = str(len(report.get("residual", [])))
    resp.headers["X-PII-Skipped"] = str(len(report.get("skipped", [])))
    resp.headers["X-PII-Notfound"] = str(len(report.get("not_found", [])))
    return resp


class _ReqError(Exception):
    """Errore da rendere al client come {"error": ...} con uno status preciso."""

    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.msg, self.status = msg, status


def _ocr_hint(is_pdf_input):
    """Coda del messaggio d'errore quando un PDF non da' testo e l'OCR non c'e':
    dire COME abilitarlo, non solo che manca."""
    if is_pdf_input and not pdf_export.ocr_available():
        return (" L'OCR per le scansioni non e' attivo: metti i language data di "
                "Tesseract (ita/eng .traineddata) in una cartella e indicala con "
                "PII_TESSDATA, oppure installa Tesseract.")
    return ""


def _build_anonymized_pdf():
    """Costruisce il PDF ANONIMIZZATO dall'input della richiesta. Stesso input di
    /analyze:

    - multipart con un file .pdf  -> REDAZIONE VERA del documento originale: le
      PII sono rimosse dal content stream e sostituite dai placeholder, il layout
      resta quello di partenza (piu' metadati/annotazioni/campi modulo/segnalibri
      ripuliti e allegati rimossi);
    - multipart con .md/.txt oppure {"text": ...} -> PDF ricostruito impaginando
      da zero il solo testo anonimizzato.

    Il dizionario placeholder->valore NON viaggia sulla rete in nessuna delle due
    direzioni: viene ricostruito qui, serve solo a localizzare le PII nel PDF e
    muore con la richiesta. Per questo funziona identico anche con il dizionario
    reversibile disattivato (MAPPING_ENABLED=False), dove il client non ne ha
    nessuno.

    Ritorna (bytes, report, n_redazioni, nome_file). Solleva _ReqError sugli errori.
    """
    up = _uploaded_file()
    if up is not None:
        name, data = up.filename, up.read()
        try:
            text = _text_from_bytes(name, data)
        except ValueError as e:
            raise _ReqError(str(e))
        except Exception as e:                       # PDF corrotto / protetto
            raise _ReqError(f"Impossibile leggere il file: {e}")
        raw_excl = request.form.get("exclude_tags")
        raw_boxes = request.form.get("manual_boxes")
    else:
        payload = request.get_json(silent=True) or {}
        name, data, text = "", b"", payload.get("text", "")
        raw_excl = payload.get("exclude_tags")
        raw_boxes = payload.get("manual_boxes")

    try:
        mboxes = pdf_export.parse_manual_boxes(raw_boxes)
    except pdf_export.PdfError as e:
        raise _ReqError(str(e))
    is_pdf_input = bool(data) and _is_pdf(name, data)
    if not is_pdf_input:
        mboxes = []          # i riquadri esistono solo sulle pagine di un PDF

    text = (text or "").strip()
    if not text and not mboxes:
        raise _ReqError("Nessun testo da anonimizzare." + _ocr_hint(is_pdf_input))

    stem = os.path.splitext(_safe_name(name, "documento.pdf"))[0] or "documento"
    out_name = f"{stem}_anonimizzato.pdf"

    excl = server_config.parse_tag_list(raw_excl) if raw_excl is not None else EXCLUDED_TAGS
    # mapping_enabled=True e' interno: il risultato non esce da questa funzione.
    # Con soli riquadri (scansione senza testo leggibile) il modello non gira.
    res = (analyze(text, excl, mapping_enabled=True) if text
           else {"mapping": {}, "anonymized_text": "", "n_entities": 0})
    if not res["mapping"] and not mboxes:
        raise _ReqError("Nessuna PII trovata: non c'e' niente da "
                        "anonimizzare in questo documento.", 422)

    if is_pdf_input:
        try:
            out, report = pdf_export.redact_pdf(data, res["mapping"],
                                                manual_boxes=mboxes)
        except pdf_export.PdfError as e:
            raise _ReqError(str(e))
        if report["occurrences"] == 0 and not report.get("manual_boxes"):
            raise _ReqError("Nessuna occorrenza trovata nel PDF: se il documento "
                            "e' una scansione (testo dentro un'immagine) la "
                            "redazione del layer testuale non puo' agire."
                            + _ocr_hint(True), 422)
        n_red = report["occurrences"] + report.get("manual_boxes", 0)
        return out, report, n_red, out_name

    try:
        out = pdf_export.text_to_pdf(res["anonymized_text"])
    except pdf_export.PdfError as e:
        raise _ReqError(str(e))
    # testo reimpaginato da zero: nell'output c'e' solo il testo anonimizzato,
    # quindi niente residui e niente valori saltati da segnalare.
    return out, {}, res["n_entities"], out_name


@app.route("/pdf", methods=["POST"])
def pdf_route():
    """Scarica il documento ANONIMIZZATO in PDF (vedi _build_anonymized_pdf)."""
    try:
        out, report, redactions, name = _build_anonymized_pdf()
    except _ReqError as e:
        return jsonify({"error": e.msg}), e.status
    return _pdf_response(out, report, redactions, name)


@app.route("/pdf/preview", methods=["POST"])
def pdf_preview_route():
    """Come /pdf, ma il binario resta in memoria e si guarda a video: la risposta
    e' il descrittore del documento ({doc_id, n_pages, ...}), le pagine si prendono
    poi da /doc/<id>/page/<n>.png e il file da /doc/<id>/file.pdf.

    Serve a non anonimizzare due volte: l'anteprima a destra e il download del PDF
    usano lo STESSO documento, generato una volta sola."""
    try:
        out, report, redactions, name = _build_anonymized_pdf()
    except _ReqError as e:
        return jsonify({"error": e.msg}), e.status
    doc_id, n_pages = _store_doc(out, name)
    return jsonify({
        "doc_id": doc_id,
        "n_pages": n_pages,
        "filename": name,
        "redactions": redactions,
        "residual": len(report.get("residual", [])),
        "skipped": len(report.get("skipped", [])),
        "not_found": len(report.get("not_found", [])),
    })


# --------------------------------------------------------------------------- #
# Anteprima a video del documento CARICATO + pagine renderizzate
# --------------------------------------------------------------------------- #
@app.route("/preview", methods=["POST"])
def preview_route():
    """Tiene in memoria il PDF appena caricato per mostrarlo a sinistra e ne
    ritorna anche il testo estratto (cosi' l'UI puo' offrire "PDF" o "Testo"
    senza una seconda estrazione)."""
    up = _uploaded_file()
    if up is None:
        return jsonify({"error": "Nessun file caricato."}), 400
    name, data = up.filename, up.read()
    if not _is_pdf(name, data):
        return jsonify({"error": "L'anteprima renderizzata vale solo per i PDF."}), 400
    try:
        text = _text_from_bytes(name, data)
        doc_id, n_pages = _store_doc(data, name)
    except Exception as e:                           # PDF corrotto / protetto
        return jsonify({"error": f"Impossibile leggere il file: {e}"}), 400
    return jsonify({"doc_id": doc_id, "n_pages": n_pages,
                    "filename": _safe_name(name), "text": text})


@app.route("/doc/<doc_id>/page/<int:n>.png")
def doc_page(doc_id, n):
    """Pagina n (0-based) renderizzata in PNG, al dpi chiesto (`?dpi=220` per lo
    zoom; lista chiusa). 404 se il documento e' scaduto dalla LRU: l'UI in quel
    caso avvisa e si rifa' l'upload."""
    d = _get_doc(doc_id)
    if d is None:
        return ("", 404)
    # dpi = risoluzione chiesta dallo zoom, su lista chiusa (vedi pdf_export)
    dpi = pdf_export.parse_preview_dpi(request.args.get("dpi"), PREVIEW_DPI)
    png = _page_png(d, n, dpi)
    if png is None:
        return ("", 404)
    resp = app.response_class(png, mimetype="image/png")
    resp.headers["Cache-Control"] = "private, max-age=600"
    return resp


@app.route("/doc/<doc_id>/file.pdf")
def doc_file(doc_id):
    """Download del PDF tenuto in memoria (quello gia' anonimizzato da
    /pdf/preview): non ricalcola niente."""
    d = _get_doc(doc_id)
    if d is None:
        return jsonify({"error": "Documento non piu' disponibile."}), 404
    resp = app.response_class(d["pdf"], mimetype="application/pdf")
    resp.headers["Content-Disposition"] = f"attachment; filename={d['name']}"
    return resp


# --------------------------------------------------------------------------- #
# Impostazioni: legenda dei tag, tag esclusi, dizionario reversibile on/off
# (/tags resta come alias storico dello stesso endpoint)
# --------------------------------------------------------------------------- #
@app.route("/settings", methods=["GET"])
@app.route("/tags", methods=["GET"])
def settings_get():
    return jsonify({
        "tags": [{"tag": t, "it": it, "en": en, "example": ex} for t, it, en, ex in TAGS],
        "excluded_tags": EXCLUDED_TAGS,
        "mapping_enabled": MAPPING_ENABLED,
        "custom_terms": CUSTOM_TERMS,
        "config_path": str(server_config.prefs_path()),
        "env_override": "PII_EXCLUDE_TAGS" in os.environ or "PII_MAPPING" in os.environ,
    })


@app.route("/settings", methods=["POST"])
@app.route("/tags", methods=["POST"])
def settings_post():
    global EXCLUDED_TAGS, MAPPING_ENABLED, CUSTOM_TERMS
    data = request.get_json(silent=True) or {}
    tags = None
    if "excluded_tags" in data:
        tags = server_config.parse_tag_list(data["excluded_tags"])
        # ammessi anche i tag coniati nei Termini personali (in arrivo o salvati)
        term_tags = {t["tag"] for t in
                     server_config.parse_custom_terms(data.get("custom_terms"))} | \
                    {t["tag"] for t in CUSTOM_TERMS}
        unknown = [t for t in tags if t not in TAG_NAMES and t not in term_tags]
        if unknown:
            return jsonify({"error": f"Tag sconosciuti: {', '.join(unknown)}"}), 400
    mapping = data.get("mapping_enabled")
    terms = data.get("custom_terms") if "custom_terms" in data else None
    if tags is None and mapping is None and terms is None:
        return jsonify({"error": "Niente da salvare: passa excluded_tags, "
                                 "mapping_enabled e/o custom_terms."}), 400
    saved = server_config.save_prefs(excluded_tags=tags, mapping_enabled=mapping,
                                     custom_terms=terms)
    EXCLUDED_TAGS = saved["excluded_tags"]
    MAPPING_ENABLED = saved["mapping_enabled"]
    CUSTOM_TERMS = saved["custom_terms"]
    return jsonify({"ok": True, "excluded_tags": EXCLUDED_TAGS,
                    "mapping_enabled": MAPPING_ENABLED,
                    "custom_terms": CUSTOM_TERMS})


# --------------------------------------------------------------------------- #
# Config host/porta (GET = leggi, POST = salva per il prossimo avvio)
# --------------------------------------------------------------------------- #
@app.route("/config", methods=["GET"])
def config_get():
    cfg = server_config.load_config()
    return jsonify({
        "host": cfg.get("host", server_config.DEFAULT_HOST),
        "port": cfg.get("port", server_config.DEFAULT_PORT),
        "config_path": str(server_config.config_path()),
    })


@app.route("/config", methods=["POST"])
def config_post():
    data = request.get_json(silent=True) or {}
    host = str(data.get("host", server_config.DEFAULT_HOST)).strip()
    try:
        port = int(data.get("port", server_config.DEFAULT_PORT))
    except (ValueError, TypeError):
        return jsonify({"error": "Porta non valida."}), 400
    if not (1024 <= port <= 65535):
        return jsonify({"error": "La porta deve essere tra 1024 e 65535."}), 400
    server_config.save_config(host, port)
    return jsonify({"ok": True, "host": host, "port": port})


@app.route("/port-check")
def port_check():
    host = request.args.get("host", server_config.DEFAULT_HOST)
    try:
        port = int(request.args.get("port", server_config.DEFAULT_PORT))
    except (ValueError, TypeError):
        return jsonify({"available": False})
    return jsonify({"available": server_config.port_available(host, port)})


# --------------------------------------------------------------------------- #
# UI (single page)
# --------------------------------------------------------------------------- #
PAGE = r"""
<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="/assets/detective.png">
<script>document.documentElement.dataset.theme=localStorage.getItem('pii_theme')||'chiaro';</script>
<title>AnonimAI · locale</title>
<link rel="stylesheet" href="/assets/tokens.css">
<style>
/* ============================================================
   AnonimAI — pelle applicativa sugli standard StudIA.
   I token (palette, barre, tema, ombre) vivono in /assets/tokens.css,
   caricato PRIMA: qui c'e' solo cio' che e' specifico di quest'app.
   Regole del sistema: zero border-radius (eccetto chip-toggle e pallini),
   bordi 1px, ombra solo su hover/flottanti, tre accenti coi ruoli fissi
   (teal=azione, giallo=segni dell'utente, blu=riferimento), metadati in
   maiuscolo. Vedi ~/.claude/skills/studia-app-layout/SKILL.md.
   ============================================================ */

/* La pagina tiene la SUA scrollbar: qui non c'e' il binario .navdots che in
   StudIA la sostituisce (skill §7: mai nascondere senza rimpiazzare). */
html{scrollbar-width:auto}
html::-webkit-scrollbar{width:initial;height:initial;display:initial}

body{height:100vh;display:flex;flex-direction:column;overflow:hidden;
     font-size:14.5px;line-height:1.55}
/* con un risultato la pagina scrolla (il dizionario sta sotto le colonne) */
body:has(.app.has-result){height:auto;overflow:visible}

.app{flex:1;min-height:0;width:100%;
     padding:0;display:flex;flex-direction:column;overflow:hidden}
.app.has-result{flex:none;height:auto;overflow:visible}

/* ---- topbar: e' la barra degli strumenti dell'app, un decimo piu' grande ---- */
.topbar{flex:none}
.brand{cursor:pointer;padding:0 .5rem;margin-left:-.5rem;transition:background var(--speed)}
.brand:hover{background:var(--hover)}
.brand .brand-ic{font-size:26px;line-height:1}
.brand .bl{display:flex;flex-direction:column;line-height:1.1;gap:1px;text-align:left}
.brand .ver{font-weight:500;color:var(--muted);letter-spacing:.06em}
#modeLabel{color:var(--teal-strong)}
/* la riga comandi della card di input sta su UNA riga sola: niente a capo.
   Quando la colonna si stringe cadono prima le cose che si possono dedurre —
   la scorciatoia, poi la parola "reversibile", poi l'etichetta intera: lo
   switch col suo badge e la ⓘ restano sempre. */
.row.acts{flex-wrap:nowrap;gap:8px;min-width:0}
.row.acts .btn,.row.acts .ghost{flex:0 0 auto}
/* lo switch cede spazio prima dei bottoni, e dentro di lui cede SOLO
   l'etichetta: interruttore, badge di stato e ⓘ non si tagliano mai. */
.mapsw .tsw,.mapsw .st,.mapsw .infodot{flex:0 0 auto}
.mapsw .ttl{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
            display:block;font-size:11px;font-weight:700;
            text-transform:uppercase;letter-spacing:.08em}
#fileName{margin-left:.6rem}
.badge{display:inline-flex;align-items:center;gap:.45rem;height:var(--tb-h);
       padding:0 .6rem;font-size:10px;font-weight:700;text-transform:uppercase;
       letter-spacing:.12em;color:var(--teal-strong)}
.topbar select{height:var(--tb-h);border:0;background:transparent;cursor:pointer;
       font-size:var(--tb-fs);font-weight:700;text-transform:uppercase;
       letter-spacing:.08em;color:var(--ink);padding:0 .3rem}
.topbar select:hover{background:var(--hover)}
#thTog .mo{opacity:.3}
html[data-theme="scuro"] #thTog .su{opacity:.3}
html[data-theme="scuro"] #thTog .mo{opacity:1}
/* avviso ⚠️: popup ancorato al bottone, flottante -> bordo + ombra */
.info{position:relative}
.info .tip{position:absolute;top:calc(100% + 8px);right:0;width:300px;z-index:60;
       background:var(--panel);border:1px solid var(--line);box-shadow:var(--sh-3d);
       padding:.8rem .9rem;font-size:12.5px;font-weight:400;color:var(--ink);
       line-height:1.5;text-align:left;text-transform:none;letter-spacing:0;
       opacity:0;visibility:hidden;transform:translateY(-4px);
       transition:opacity var(--speed),transform var(--speed);pointer-events:none}
.info.open .tip{opacity:1;visibility:visible;transform:none;pointer-events:auto}
.info .tip b{color:var(--ink)}
.info .tip a{color:var(--blue-strong);font-weight:700}

/* ---- riquadri: le due colonne sono CONTIGUE (bordo condiviso, gap 0)
   e riempiono tutta la larghezza della finestra ---- */
.grid{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr;gap:0;flex:1;min-height:0}
.workspace{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr;gap:0;
           align-items:stretch;flex:1;min-height:0}
/* le card non hanno cornice propria: il contenitore e' la finestra. L'unica
   linea verticale e' il confine FRA le due colonne, e in alto confinano con la
   topbar (che porta gia' la sua linea). Il margine interno resta in .bd. */
.card{background:var(--panel);border:0;display:flex;
      flex-direction:column;overflow:hidden;min-height:0}
.workspace > .card + .card,.grid > .card + .card{border-left:1px solid var(--line)}
/* la testata di ogni riquadro E' una .tbar (skill §5bis) e sta SEMPRE su una
   riga: niente wrap — cedono gli elementi elastici (nome file, hint) in
   ellipsis, e sotto una certa larghezza della COLONNA (@container, non @media:
   la colonna e' meta' finestra) i comandi perdono prima le etichette a parole,
   poi i rientri. Nessun comando se ne va davvero. */
.card .hd{display:flex;align-items:center;gap:.5rem;flex-wrap:nowrap;flex:none;
          height:var(--tb-bar-h);padding:0 .5rem 0 .95rem;overflow:hidden;
          border-bottom:1px solid var(--line);container-type:inline-size}
.card .hd h2{font-size:11px;margin:0;text-transform:uppercase;letter-spacing:.14em;
             color:var(--muted);font-weight:700;white-space:nowrap;flex:none}
.card .hd .right{margin-left:auto;display:flex;gap:.1rem;align-items:center;
                 flex:none;min-width:0}
/* gli elastici: si accorciano loro, mai i comandi */
.card .hd .tbnota,.card .hd .hint{flex:0 1 auto;min-width:0;overflow:hidden;
                 text-overflow:ellipsis;white-space:nowrap}
.card .hd .right .hint{flex:0 1 auto}
.seg-tabs button,#boxBtn{white-space:nowrap}
/* colonna stretta: via l'etichetta di Riquadri (resta ✏️ + contatore)... */
@container (max-width: 640px){
  .card .hd .hint{display:none}
  #boxBtn [data-i18n]{display:none}
  .card .hd #boxBtn{min-width:var(--tb-min);padding:0 .3rem}
}
/* ...piu' stretta ancora: rientri e zoom ridotti (specificita' >= delle
   regole base, che nel foglio vengono DOPO e a parita' vincerebbero) */
@container (max-width: 520px){
  .card .hd .seg-tabs button{padding:0 .38rem;letter-spacing:.03em}
  .card .hd .zoomg .lvl{min-width:38px}
  .card .hd .zoomg button{min-width:22px;padding:0 .25rem}
  /* ultimo a cedere: il titolo si tronca, i comandi restano interi */
  .card .hd h2{flex:0 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;
         letter-spacing:.07em}
}
.card .bd{padding:14px 16px;flex:1;min-height:0;display:flex;flex-direction:column}

/* comandi di testata: stessi vestiti dei .tbtn */
.seg-tabs{display:inline-flex;align-items:center;height:var(--tb-h)}
.seg-tabs button{border:0;background:transparent;color:var(--ink);cursor:pointer;height:100%;
     padding:0 var(--tb-pad-x);font-size:var(--tb-fs);font-weight:var(--tb-peso);
     letter-spacing:var(--tb-track);text-transform:uppercase;border-radius:0;
     transition:background var(--speed)}
.seg-tabs button:hover{background:var(--hover)}
.seg-tabs button.on{background:color-mix(in srgb,var(--teal) 26%,var(--panel));
     color:var(--teal-strong)}
#boxBtn{height:var(--tb-h);min-width:var(--tb-min);border:0;border-radius:0;
     background:transparent;color:var(--ink);padding:0 var(--tb-pad-x);
     font-size:var(--tb-fs);font-weight:var(--tb-peso);letter-spacing:var(--tb-track);
     text-transform:uppercase;display:inline-flex;align-items:center;gap:.35rem;
     cursor:pointer;transition:background var(--speed)}
#boxBtn:hover{background:var(--hover)}
#boxBtn.on{background:color-mix(in srgb,var(--yellow) 30%,var(--panel));
     color:var(--yellow-strong)}
#boxBtn .n{color:var(--yellow-strong);font-weight:800}

textarea{width:100%;flex:1;min-height:0;resize:none;border:1px solid var(--line);
         border-radius:0;padding:12px 13px;font-size:14px;line-height:1.6;
         color:var(--ink);background:var(--bg);
         font-family:var(--font-text),var(--emoji-font),sans-serif}
textarea:focus{outline:2px solid var(--primary);outline-offset:-2px}
textarea.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace,var(--emoji-font);font-size:13px}

/* drag&drop su tutta la finestra: overlay flottante (bordo + ombra) */
#dropOverlay{position:fixed;inset:0;z-index:90;display:none;align-items:center;
      justify-content:center;background:color-mix(in srgb,var(--teal) 14%,rgba(15,17,21,.45))}
#dropOverlay.on{display:flex}
#dropOverlay .dz{display:flex;flex-direction:column;align-items:center;gap:12px;
      pointer-events:none;background:var(--panel);border:2px dashed var(--teal-strong);
      box-shadow:var(--sh-3d);padding:2.2rem 3rem;font-size:14px;font-weight:700;
      text-transform:uppercase;letter-spacing:.1em;color:var(--teal-strong)}
#dropOverlay .dz::first-line{font-size:14px}
#dropOverlay .dz{font-size:44px}
#dropOverlay .dz span{font-size:13px}

/* bottoni fuori dalle barre: due sole facce, azione (teal) e neutra */
.row{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-top:12px;flex:none}
button{font-family:var(--font-text),var(--emoji-font),sans-serif}
.btn{height:var(--ctl-h);border:1px solid transparent;border-radius:0;cursor:pointer;
     display:inline-flex;align-items:center;gap:.5rem;padding:0 1.1rem;
     font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;
     background:color-mix(in srgb,var(--teal) 22%,var(--panel));color:var(--teal-strong);
     transition:background var(--speed),box-shadow var(--speed)}
.btn:hover:not(:disabled){background:color-mix(in srgb,var(--teal) 32%,var(--panel));
     box-shadow:var(--sh-3d)}
.btn.lg{padding:0 1.5rem;font-size:12.5px}
.ghost{height:var(--ctl-h);border:1px solid var(--line);border-radius:0;cursor:pointer;
     display:inline-flex;align-items:center;gap:.5rem;padding:0 .95rem;
     font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;
     background:var(--panel);color:var(--ink);
     transition:background var(--speed),box-shadow var(--speed)}
.ghost:hover:not(:disabled){background:var(--hover);box-shadow:var(--sh-3d)}
button:disabled{opacity:.45;cursor:default}
.spin{width:14px;height:14px;border:2px solid color-mix(in srgb,var(--teal-strong) 30%,transparent);
      border-top-color:var(--teal-strong);border-radius:50%;animation:sp .7s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.hint{color:var(--muted);font-size:12px;margin-left:auto}

/* viste */
.view{flex:1;overflow:auto;border:1px solid var(--line);padding:14px;
      background:var(--bg);min-height:0}
#src,#anon{flex:1;min-height:0}
#pane2 textarea{flex:1;min-height:0}
.app.has-result{height:auto;overflow:visible}
.app.has-result .workspace{flex:none}
.app.has-result #src,.app.has-result #anon,.app.has-result .view{flex:none;height:60vh}
#pane2 textarea,#pane2 .view{min-height:60vh}
@media(max-width:920px){
  .grid{grid-template-columns:1fr}
  body,.app{height:auto;overflow:visible}
  .workspace{grid-template-columns:1fr;grid-template-rows:none;flex:none;min-height:auto}
  #src,#anon,.view,#pane2 textarea{flex:none;height:60vh}
}

/* render del PDF: pagine su fondo neutro, cornice 1px, niente ombre a riposo */
.pdfview{padding:12px;background:var(--hover)}
/* Lo zoom e' la LARGHEZZA della pagina (non un transform): le barre di scorrimento
   restano quelle native, il layout non va calcolato a mano e i riquadri manuali —
   che sono in frazioni della pagina — continuano a cadere dove devono. */
.pdfview .pg{position:relative;width:calc(100% * var(--z,1));max-width:none;
             margin:0 0 12px;background:#fff;
             border:1px solid var(--line);overflow:hidden}
.pdfview .pg:last-child{margin-bottom:0}
.pdfview .pg img{display:block;width:100%;height:auto;min-height:24px}
.pdfview .pgn{position:absolute;right:6px;bottom:6px;background:var(--ink);color:var(--bg);
              font-size:9.5px;font-weight:700;text-transform:uppercase;
              letter-spacing:.08em;padding:2px 6px}
/* comandi dello zoom: gli stessi .tbtn della barra, solo piu' stretti */
.zoomg{display:inline-flex;align-items:center;height:var(--tb-h)}
.zoomg button{border:0;background:transparent;color:var(--ink);cursor:pointer;height:100%;
     min-width:26px;padding:0 .4rem;font-size:var(--tb-fs);font-weight:var(--tb-peso);
     letter-spacing:var(--tb-track);transition:background var(--speed)}
.zoomg button:hover:not(:disabled){background:var(--hover)}
.zoomg button:disabled{opacity:.4;cursor:default}
.zoomg .lvl{min-width:46px;font-variant-numeric:tabular-nums}
.zoomg .lvl.on{color:var(--teal-strong)}

.pdfbusy{display:flex;align-items:center;justify-content:center;gap:10px;height:100%;
         color:var(--muted);font-size:12px;font-weight:700;text-transform:uppercase;
         letter-spacing:.1em}

/* riquadri manuali: segni DELL'UTENTE -> giallo (ruolo fisso dell'accento);
   in modalita' disegno l'hover per eliminare passa al rosso d'errore */
.pdfview.boxing .pg{cursor:crosshair;user-select:none}
.pdfview.boxing .pg img{pointer-events:none}
.pii-box{position:absolute;border:2px solid var(--yellow-strong);
         background:color-mix(in srgb,var(--yellow) 38%,transparent);
         pointer-events:none;z-index:4;box-sizing:border-box}
.pdfview.boxing .pii-box{pointer-events:auto;cursor:pointer}
.pdfview.boxing .pii-box:hover{border-color:var(--err-ink);
         background:color-mix(in srgb,var(--err) 32%,transparent)}
.pii-box.draft{pointer-events:none;border-style:dashed;
         background:color-mix(in srgb,var(--yellow) 18%,transparent)}

/* anteprima con i placeholder evidenziati (colore deterministico per tag) */
.preview{white-space:pre-wrap;word-wrap:break-word;font-size:14px;line-height:1.7}
.ph{padding:1px 7px 2px;font-weight:600;font-size:12px;cursor:help;border:1px solid;
    white-space:nowrap;display:inline-block;line-height:1.4;transition:opacity var(--speed)}
.ph .ck{font-size:10px;opacity:.8;margin-left:3px}
.ph.dim{opacity:.25;filter:grayscale(.6)}
.empty{color:var(--muted);display:flex;flex-direction:column;align-items:center;
       justify-content:center;height:100%;gap:9px;text-align:center;font-size:13.5px}
.empty .big{font-size:64px;opacity:.9}

/* legenda cliccabile + statistiche */
.legend{display:flex;gap:7px;flex-wrap:wrap;padding:12px 16px;border-top:1px solid var(--line-weak)}
.chip{display:inline-flex;align-items:center;gap:7px;border:1px solid var(--line);
      border-radius:999px;padding:4px 11px;font-size:12px;font-weight:600;color:var(--ink);
      cursor:pointer;background:var(--panel);user-select:none;transition:background var(--speed)}
.chip:hover{background:var(--hover)}
.chip.off{opacity:.4;text-decoration:line-through}
.chip .sw{width:10px;height:10px;flex:none}
.chip .n{color:var(--muted);font-weight:700}
.meta{display:flex;gap:8px;flex-wrap:wrap;padding:0 16px 12px}
.stat{background:var(--hover);border:1px solid var(--line-weak);padding:5px 10px;
      font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
.stat b{color:var(--ink);font-weight:800;letter-spacing:0}

/* dizionario */
.tablewrap{max-height:240px;overflow:auto;padding:0 16px 16px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{position:sticky;top:0;background:var(--panel);text-align:left;color:var(--muted);
   font-weight:700;font-size:10px;text-transform:uppercase;letter-spacing:.08em;
   padding:8px;border-bottom:1px solid var(--line)}
td{padding:8px;border-bottom:1px solid var(--line-weak);vertical-align:top}
td.k{font-family:ui-monospace,Consolas,monospace;font-weight:600;white-space:nowrap}
td.v{word-break:break-word}
tr:hover td{background:var(--hover)}
.dict{margin-top:16px;flex:none}
.dict .bd{padding:0;display:block}
.dict .meta{padding:13px 16px 6px}
.dict .legend{padding:0 16px 12px;border-top:none}
.dict .tablewrap{max-height:300px;overflow:auto;padding:0 16px 16px}

/* pannello Ripristina */
.pane{display:none}
.pane.on{display:flex;flex-direction:column;flex:1;min-height:0}
#pane2 .callout{margin:0;border-bottom:1px solid var(--line)}
/* callout informativo = blu (riferimento); l'avvertenza #rOff = giallo */
.callout{display:flex;gap:11px;border-left:4px solid var(--blue);
         background:color-mix(in srgb,var(--blue) 6%,var(--panel));
         padding:12px 14px;font-size:13px;color:var(--ink);margin-bottom:14px;flex:none}
.callout b{color:var(--blue-strong)}
.callout .ic{font-size:16px}
#rOff{border-left-color:var(--yellow);
      background:color-mix(in srgb,var(--yellow) 8%,var(--panel))}
#rOff b{color:var(--yellow-strong)}

/* crediti */
/* crediti e spiegazioni: non piu' un footer, ma due schede dentro ⚙️ */
.cfg-card .tabs{margin:-4px 0 16px}
.cfg-body{max-height:58vh;overflow:auto}
.cfg-body h4{font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);
        margin:16px 0 6px;font-weight:700}
.cfg-body h4:first-child{margin-top:0}
.cfg-body p{font-size:13px;line-height:1.6;margin:0 0 10px}
.cfg-body ul{margin:0 0 10px 1.1rem;font-size:13px;line-height:1.6}
.cfg-body li{margin:.25rem 0}
.cfg-body a{color:var(--blue-strong);font-weight:700}
.cfg-body code{font-family:ui-monospace,Consolas,monospace;font-size:12px;
        background:var(--hover);padding:1px 5px}
.cfg-body .kv{display:flex;gap:.6rem;font-size:12.5px;padding:.45rem 0;
        border-bottom:1px solid var(--line-weak)}
.cfg-body .kv:last-child{border-bottom:0}
.cfg-body .kv b{flex:0 0 116px;font-weight:700;text-transform:uppercase;font-size:10.5px;
        letter-spacing:.08em;color:var(--muted);padding-top:2px}

/* toast: flottante -> bordo, ombra e costola d'accento a sinistra */
#toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%) translateY(20px);
       background:var(--panel);border:1px solid var(--line);
       border-left:5px solid var(--err);color:var(--ink);
       padding:.7rem 1.1rem;font-size:13px;font-weight:600;box-shadow:var(--sh-3d);
       opacity:0;pointer-events:none;transition:opacity var(--speed),transform var(--speed);
       z-index:80;display:flex;align-items:center;gap:9px;max-width:80vw}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
#toast.ok{border-left-color:var(--teal)}
#toast.ok::before{content:"✓";color:var(--teal-strong);font-weight:800}
.kbd{font-family:ui-monospace,Consolas,monospace;background:var(--hover);
     border:1px solid var(--line-weak);padding:1px 6px;font-size:11px;color:var(--muted)}

/* switch "Dizionario reversibile": ON = teal, OFF = attenzione (giallo).
   Sta nella STESSA riga dei bottoni e ha la loro altezza (--ctl-h): la
   spiegazione lunga vive nel popup della ⓘ, non in una riga di testo grigio. */
.mapsw{display:inline-flex;align-items:center;gap:9px;height:var(--ctl-h);
       padding:0 11px;box-sizing:border-box;flex:0 1 auto;min-width:0;
       /* niente overflow:hidden qui: taglierebbe il popup della ⓘ — il
          troncamento vive sull'etichetta, che e' l'unica che deve cedere */
       border:1px solid var(--line);border-left:4px solid var(--teal);
       background:color-mix(in srgb,var(--teal) 6%,var(--panel));
       transition:background var(--speed)}
.mapsw.off{border-left-color:var(--yellow);
       background:color-mix(in srgb,var(--yellow) 8%,var(--panel))}
.tsw{position:relative;width:38px;height:21px;border-radius:999px;background:var(--teal-strong);
     border:0;padding:0;flex:none;cursor:pointer;transition:background var(--speed)}
.tsw .knob{position:absolute;top:3px;left:3px;width:15px;height:15px;border-radius:50%;
           background:var(--panel);transition:transform var(--speed);
           box-shadow:0 1px 3px rgba(0,0,0,.28)}
.tsw.off{background:var(--yellow-strong)}
.tsw.off .knob{transform:translateX(17px)}
.mapsw .st{font-size:9.5px;font-weight:800;letter-spacing:.1em;padding:2px 7px;
           background:color-mix(in srgb,var(--teal) 20%,var(--panel));color:var(--teal-strong)}
.mapsw.off .st{background:color-mix(in srgb,var(--yellow) 26%,var(--panel));
           color:var(--yellow-strong)}
/* Popup d'uso sui bottoni: compare dopo 900 ms di puntatore fermo e sparisce
   subito. Il ritardo e' tutto nel transition-delay — niente timer JS: un
   suggerimento che scatta al primo passaggio del mouse e' rumore, uno che
   aspetta chi si e' fermato a chiedersi "e questo?" e' un aiuto. */
.htip{position:relative;display:inline-flex}
.htip > .tip{position:absolute;bottom:calc(100% + 8px);left:0;width:310px;z-index:70;
      background:var(--panel);border:1px solid var(--line);box-shadow:var(--sh-3d);
      padding:.7rem .8rem;font-size:12px;font-weight:400;line-height:1.5;color:var(--ink);
      text-align:left;text-transform:none;letter-spacing:0;white-space:normal;
      opacity:0;visibility:hidden;pointer-events:none;
      transition:opacity var(--speed) 0s,visibility 0s var(--speed)}
.htip:hover > .tip,.htip:focus-within > .tip{opacity:1;visibility:visible;
      transition:opacity var(--speed) .9s,visibility 0s .9s}
.htip > .tip b{color:var(--ink)}
.htip.r > .tip{left:auto;right:0}
.htip > .tip .warn{color:var(--err-ink);font-weight:700}

/* la ⓘ col popup: flottante -> bordo + ombra, come gli altri popup del sistema */
.infodot{position:relative;display:inline-flex;align-items:center;justify-content:center;
         width:18px;height:18px;flex:none;cursor:help;font-size:13px;color:var(--muted)}
.infodot:hover,.infodot:focus-visible{color:var(--ink)}
.infodot .tip{position:absolute;bottom:calc(100% + 8px);right:-8px;width:280px;z-index:70;
         background:var(--panel);border:1px solid var(--line);box-shadow:var(--sh-3d);
         padding:.7rem .8rem;font-size:12px;font-weight:400;line-height:1.5;color:var(--ink);
         text-align:left;text-transform:none;letter-spacing:0;white-space:normal;
         opacity:0;visibility:hidden;transform:translateY(4px);pointer-events:none;
         transition:opacity var(--speed),transform var(--speed)}
.infodot:hover .tip,.infodot:focus-visible .tip{opacity:1;visibility:visible;transform:none}

/* modali (flottanti: bordo + ombra, testa/piede separati da linea) */
.cfg-overlay{position:fixed;inset:0;background:rgba(15,17,21,.55);z-index:100;
             display:flex;align-items:center;justify-content:center;opacity:0;
             visibility:hidden;transition:opacity var(--speed)}
.cfg-overlay.open{opacity:1;visibility:visible}
.cfg-card{background:var(--panel);border:1px solid var(--line);box-shadow:var(--sh-3d);
          padding:22px 24px 18px;width:380px;max-width:92vw;max-height:88vh;overflow:auto}
.cfg-card h3{margin:0 0 16px;font-size:13px;font-weight:800;display:flex;align-items:center;
             gap:9px;text-transform:uppercase;letter-spacing:.1em;padding-bottom:12px;
             border-bottom:1px solid var(--line)}
.cfg-card.wide{width:620px}
.cfg-row{display:flex;flex-direction:column;gap:5px;margin-bottom:14px}
.cfg-row label{font-size:10.5px;font-weight:700;color:var(--muted);text-transform:uppercase;
               letter-spacing:.1em}
.cfg-row input{height:var(--ctl-h);border:1px solid var(--line);border-radius:0;
               padding:0 12px;font:inherit;font-size:13.5px;color:var(--ink);background:var(--bg)}
.cfg-row input:focus{outline:2px solid var(--primary);outline-offset:-2px}
.cfg-status{font-size:12px;font-weight:700;padding:7px 11px;margin-bottom:14px;display:none}
.cfg-status.ok{display:block;background:var(--ok-bg);color:var(--ok-ink)}
.cfg-status.fail{display:block;background:color-mix(in srgb,var(--err) 12%,var(--panel));
                 color:var(--err-ink)}
.cfg-btns{display:flex;gap:9px;align-items:center;padding-top:4px}
.cfg-note{font-size:10.5px;color:var(--muted);margin-top:12px;text-transform:uppercase;
          letter-spacing:.06em}

/* modale dei tag */
.tg-sub{font-size:12.5px;color:var(--muted);margin:-4px 0 14px;line-height:1.5;text-transform:none}
.tg-bar{display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap}
.tg-bar .mini,.ct-add .mini{height:30px;background:var(--panel);color:var(--muted);
              border:1px solid var(--line);
              border-radius:0;padding:0 10px;font-size:11px;font-weight:700;cursor:pointer;
              text-transform:uppercase;letter-spacing:.06em}
.tg-bar .mini:hover,.ct-add .mini:hover{background:var(--hover);color:var(--ink)}
.tg-bar .count{margin-left:auto;font-size:11px;color:var(--muted);font-weight:700;
               text-transform:uppercase;letter-spacing:.06em}
.tg-list{max-height:46vh;overflow:auto;border:1px solid var(--line);padding:0;background:var(--panel)}
.tg-row{display:flex;align-items:flex-start;gap:10px;padding:8px 10px;cursor:pointer;
        user-select:none;border-bottom:1px solid var(--line-weak);transition:background var(--speed)}
.tg-row:last-child{border-bottom:0}
.tg-row:hover{background:var(--hover)}
.tg-row input{margin:3px 0 0;accent-color:var(--teal-strong);width:15px;height:15px;
              flex:none;cursor:pointer}
.tg-row .sw{width:10px;height:10px;margin-top:5px;flex:none}
.tg-row .txt{min-width:0}
.tg-row .nm{font-family:ui-monospace,Consolas,monospace;font-size:12px;font-weight:700}
.tg-row .ds{font-size:12.5px;color:var(--muted);line-height:1.45}
.tg-row .ex{font-size:11px;color:var(--muted);opacity:.75}
.tg-row.off{opacity:.55}
.tg-row.off .nm{text-decoration:line-through}

/* Termini personali: stessa grammatica delle righe-tag qui sopra */
.ct-head{margin:18px 0 4px;font-size:11px;font-weight:800;text-transform:uppercase;
         letter-spacing:.12em;color:var(--muted)}
.ct-add{display:flex;gap:8px;margin:8px 0 10px}
.ct-add input{height:30px;border:1px solid var(--line);border-radius:0;background:var(--bg);
              color:var(--ink);padding:0 9px;font-size:12.5px;
              font-family:var(--font-text),var(--emoji-font),sans-serif}
.ct-add input:focus{outline:2px solid var(--focus);outline-offset:-2px}
#ctVal{flex:1;min-width:0}
#ctTag{width:150px;text-transform:uppercase}
.ct-list{border:1px solid var(--line);background:var(--panel);max-height:22vh;overflow:auto}
.ct-list:empty{display:none}
.ct-row{display:flex;align-items:center;gap:10px;padding:6px 10px;
        border-bottom:1px solid var(--line-weak)}
.ct-row:last-child{border-bottom:0}
.ct-row .val{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
             font-size:12.5px}
.ct-row .nm{font-family:ui-monospace,Consolas,monospace;font-size:11px;font-weight:700;flex:none}
.ct-row .rm{border:0;background:transparent;color:var(--muted);cursor:pointer;font-size:14px;
            padding:0 4px;flex:none}
.ct-row .rm:hover{color:var(--err-ink)}
</style>
</head>
<body>
<header class="topbar tbar-lg">
  <button class="brand" id="modeBtn" onclick="toggleMode()"
          title="Cambia modalità (Anonimizza / Deanonimizza)"
          aria-label="Cambia modalità (Anonimizza / Deanonimizza)">
    <span class="brand-ic" aria-hidden="true">🕵️</span>
    <span class="bl"><span>AnonimAI — <span id="modeLabel">Anonimizza</span> <span class="ver">v__VERSION__</span></span>
      <small data-i18n="tagline">modello locale su CPU · GDPR compliant</small></span>
  </button>
  <div class="controls">
    <span class="badge"><span class="dot on"></span> <span data-i18n="badge">100% in locale</span></span>
    <span class="tbsep"></span>
    <select id="lang" title="Lingua / Language" aria-label="Lingua / Language">
      <option value="it">🇮🇹 IT</option>
      <option value="en">🇬🇧 EN</option>
    </select>
    <span class="tbsep"></span>
    <button class="tbtn" id="thTog" title="Tema chiaro / scuro" aria-label="Tema chiaro / scuro"><span class="su">☀️</span><span class="mo">🌙</span></button>
    <button class="tbtn" id="tagsBtn" title="Tag da anonimizzare" aria-label="PII tags" onclick="openTags()">🏷️</button>
    <button class="tbtn" id="gearBtn" title="Configurazione server" aria-label="Server config" onclick="openConfig()">⚙️</button>
    <span class="info tbtn" id="infoBtn" tabindex="0" role="button" aria-label="Avviso / info">⚠️<span class="tip" data-i18n="notice"></span></span>
  </div>
</header>
<div class="app">

  <!-- ============ PANE 1: ANONIMIZZA ============ -->
  <div class="pane on" id="pane1">
    <div class="workspace">
      <!-- input -->
      <div class="card">
        <div class="hd"><h2 data-i18n="in_title">① Il tuo documento</h2>
          <span class="tbnota" id="fileName"></span>
          <div class="right">
            <span class="hint" id="inHint" data-i18n="in_hint">incolla il testo o trascina un documento nella finestra</span>
            <span class="zoomg" id="zoomG" style="display:none">
              <button id="zOut" onclick="zoomStep(-1)" title="Riduci">−</button>
              <button class="lvl" id="zLvl" onclick="zoomSet(1)" title="Adatta alla colonna">100%</button>
              <button id="zIn" onclick="zoomStep(1)" title="Ingrandisci">+</button>
            </span>
            <button id="boxBtn" style="display:none" onclick="toggleBoxMode()"
                    title="Riquadri manuali per firme e timbri">✏️ <span data-i18n="box_btn">Riquadri</span><span class="n" id="boxCount"></span></button>
            <div class="seg-tabs" id="srcTabs" style="display:none">
              <button class="on" id="sPdf" onclick="setSrcView('pdf')" data-i18n="v_pdf">Anteprima PDF</button>
              <button id="sText" onclick="setSrcView('text')" data-i18n="v_raw">Testo</button>
            </div>
          </div></div>
        <div class="bd">
          <div class="view pdfview" id="pdfSrcView" style="display:none"></div>
          <textarea id="src" data-i18n-ph="src_ph" placeholder="Incolla qui il testo dell'atto, del contratto o della sentenza…&#10;&#10;Oppure trascina un PDF, un .md o un .txt in un punto qualsiasi della finestra."></textarea>
          <input type="file" id="pdf" accept=".pdf,.md,.markdown,.txt,application/pdf,text/markdown,text/plain" hidden>
          <div class="row acts">
            <button class="btn lg" id="go">🛡️ <span data-i18n="go">Anonimizza</span></button>
            <button class="ghost" id="clear" data-i18n="clear">Pulisci</button>
            <div class="mapsw" id="mapSw">
              <button class="tsw" id="mapToggle" role="switch" aria-checked="true"
                      aria-labelledby="mapTtl" onclick="toggleMapping()"><span class="knob"></span></button>
              <span class="ttl" id="mapTtl" data-i18n="map_ttl">Dizionario</span>
              <span class="st" id="mapState">ATTIVO</span>
              <span class="infodot" id="mapInfoBtn" tabindex="0" role="button"
                    aria-label="Come funziona il dizionario reversibile">ⓘ<span class="tip" id="mapSub"></span></span>
            </div>
          </div>
        </div>
      </div>

      <!-- output -->
      <div class="card out">
        <div class="hd">
          <h2 data-i18n="out_title">② Risultato</h2>
          <div class="right">
            <div class="seg-tabs">
              <button class="on" id="vPrev" onclick="setView('prev')" data-i18n="v_prev">Anteprima</button>
              <button id="vText" onclick="setView('text')" data-i18n="v_text">Testo da copiare</button>
              <button id="vPdf" onclick="setView('pdf')" data-i18n="v_opdf">PDF censurato</button>
            </div>
          </div>
        </div>
        <div class="bd">
          <div class="view" id="viewPrev">
            <div class="empty" id="emptyPrev">
              <div class="big">🕵️</div>
              <div data-i18n="empty_prev">L'anteprima con le PII evidenziate apparirà qui.</div>
            </div>
            <div class="preview" id="prev" style="display:none"></div>
          </div>
          <div class="view pdfview" id="pdfOutView" style="display:none"></div>
          <textarea class="mono" id="anon" style="display:none" readonly
                    data-i18n-ph="anon_ph" placeholder="Il testo anonimizzato apparirà qui."></textarea>
          <div class="row">
            <span class="htip"><button class="btn" id="copy">📋 <span data-i18n="copy">Copia testo</span></button>
              <span class="tip" data-i18n="tip_copy"></span></span>
            <span class="htip"><button class="ghost" id="dlpdf">⬇️ <span data-i18n="dlpdf">PDF anonimo</span></button>
              <span class="tip" data-i18n="tip_pdf"></span></span>
            <span class="htip"><button class="ghost" id="dl">⬇️ <span data-i18n="dl">Scarica dizionario</span></button>
              <span class="tip" data-i18n="tip_dict"></span></span>
            <span class="hint" id="ulock"></span>
          </div>
        </div>
      </div>
    </div>

    <!-- dizionario: staccato, a tutta larghezza sotto le due colonne, scrollabile -->
    <div class="card dict" id="dictCard" style="display:none">
      <div class="hd">
        <h2 data-i18n="dict_title">Dizionario reversibile</h2>
        <div class="right hint" id="dictHint" data-i18n="dict_hint">resta solo qui, in locale</div>
      </div>
      <div class="bd">
        <div class="meta" id="meta"></div>
        <div class="legend" id="legend"></div>
        <div class="callout" id="dictNone" style="display:none;margin:0 16px 14px">
          <span class="ic">🔒</span><div data-i18n="dict_off">Nessun dizionario: l'anonimizzazione di questo testo è <b>definitiva</b>.</div>
        </div>
        <div class="tablewrap" id="tablewrap">
          <table><thead><tr><th data-i18n="th_id">ID</th><th data-i18n="th_val">Valore originale</th><th data-i18n="th_type">Tipo</th></tr></thead>
          <tbody id="maprows"></tbody></table>
        </div>
      </div>
    </div>
  </div>

  <!-- ============ PANE 2: RIPRISTINA ============ -->
  <div class="pane" id="pane2">
    <div class="callout" id="rOff" style="display:none">
      <span class="ic">🔒</span>
      <div data-i18n="r_off">Lo switch <b>Dizionario reversibile</b> è su DISATTIVO: le nuove
      anonimizzazioni non producono chiavi. Qui puoi comunque ripristinare con un dizionario
      <b>.json salvato in precedenza</b>.</div>
    </div>
    <div class="callout">
      <span class="ic">💡</span>
      <div data-i18n="callout">Incolla qui la <b>risposta dell'LLM</b> (che contiene i placeholder come
      <span class="kbd">[FULLNAME_1]</span>): l'app rimette i valori veri usando il dizionario
      di questa sessione. Se hai chiuso e riaperto l'app, <b>carica il dizionario .json</b> che
      avevi salvato.</div>
    </div>
    <div class="grid">
      <div class="card">
        <div class="hd"><h2 data-i18n="r_title1">Risposta con i placeholder</h2>
          <div class="right">
            <label class="chip" style="cursor:pointer"><span data-i18n="loaddict">📁 Carica dizionario</span>
              <input type="file" id="dictFile" accept="application/json" hidden></label>
          </div></div>
        <div class="bd">
          <textarea id="rin" data-i18n-ph="rin_ph" placeholder="Incolla qui la risposta di ChatGPT…"></textarea>
          <div class="row">
            <button class="btn lg" id="rev">🔓 <span data-i18n="rev">Ripristina valori</span></button>
            <button class="ghost" id="rclear" data-i18n="clear">Pulisci</button>
            <span class="hint" id="dictInfo"></span>
          </div>
        </div>
      </div>
      <div class="card">
        <div class="hd"><h2 data-i18n="r_title2">Testo ripristinato</h2></div>
        <div class="bd">
          <div class="view"><div class="preview" id="rout">
            <div class="empty"><div class="big">🔓</div>
            <div data-i18n="empty_rout">Il testo con i valori reali apparirà qui.</div></div>
          </div></div>
          <div class="row"><button class="btn" id="rcopy">📋 <span data-i18n="rcopy">Copia testo ripristinato</span></button></div>
        </div>
      </div>
    </div>
  </div>

</div>

<div id="dropOverlay" aria-hidden="true"><div class="dz">🕵️<span data-i18n="drop_here">Rilascia il documento — PDF, .md o .txt</span></div></div>

<div id="toast"></div>

<!-- config modal -->
<div class="cfg-overlay" id="cfgOverlay">
  <div class="cfg-card wide">
    <h3>⚙️ <span data-i18n="set_title">Impostazioni</span></h3>
    <div class="tabs" role="tablist">
      <button class="tab" role="tab" aria-selected="true" id="stServer"
              onclick="setSettingsTab('server')" data-i18n="set_tab_server">Server</button>
      <button class="tab" role="tab" aria-selected="false" id="stHow"
              onclick="setSettingsTab('how')" data-i18n="set_tab_how">Come funziona</button>
      <button class="tab" role="tab" aria-selected="false" id="stSec"
              onclick="setSettingsTab('sec')" data-i18n="set_tab_sec">Sicurezza</button>
      <button class="tab" role="tab" aria-selected="false" id="stCred"
              onclick="setSettingsTab('cred')" data-i18n="set_tab_cred">Crediti</button>
    </div>

    <div class="cfg-body" id="setServer">
      <div class="cfg-row">
        <label data-i18n="cfg_host">Indirizzo</label>
        <input id="cfgHost" type="text" value="127.0.0.1" spellcheck="false">
      </div>
      <div class="cfg-row">
        <label data-i18n="cfg_port">Porta</label>
        <input id="cfgPort" type="number" min="1024" max="65535" value="5005">
      </div>
      <div class="cfg-status" id="cfgStatus"></div>
      <div class="cfg-btns">
        <button class="btn" id="cfgSave" onclick="saveConfig()">💾 <span data-i18n="cfg_save">Salva</span></button>
        <button class="ghost" id="cfgCheck" onclick="checkPort()"><span data-i18n="cfg_check">Verifica porta</span></button>
      </div>
      <div class="cfg-note" data-i18n="cfg_restart_note">Le modifiche avranno effetto al prossimo avvio.</div>
    </div>

    <div class="cfg-body" id="setHow" style="display:none" data-i18n="how_body"></div>
    <div class="cfg-body" id="setSec" style="display:none" data-i18n="sec_body"></div>
    <div class="cfg-body" id="setCred" style="display:none" data-i18n="cred_body"></div>

    <div class="cfg-btns" style="border-top:1px solid var(--line);margin-top:14px;padding-top:12px">
      <span style="flex:1"></span>
      <button class="ghost" onclick="closeConfig()" data-i18n="cfg_close">Chiudi</button>
    </div>
  </div>
</div>

<!-- tags modal: legenda + selezione dei tag da anonimizzare -->
<div class="cfg-overlay" id="tagsOverlay">
  <div class="cfg-card wide">
    <h3>🏷️ <span data-i18n="tg_title">Tag da anonimizzare</span></h3>
    <div class="tg-sub" data-i18n="tg_sub">Deseleziona i tipi che vuoi <b>lasciare in chiaro</b>: verranno comunque rilevati, ma non sostituiti da un placeholder.</div>
    <div class="tg-bar">
      <button class="mini" onclick="setAllTags(true)" data-i18n="tg_all">Seleziona tutti</button>
      <button class="mini" onclick="setAllTags(false)" data-i18n="tg_none">Nessuno</button>
      <span class="count" id="tgCount"></span>
    </div>
    <div class="tg-list" id="tgList"></div>
    <div class="ct-head">📌 <span data-i18n="ct_title">Termini personali</span></div>
    <div class="tg-sub" data-i18n="ct_sub">Valori che vuoi <b>sempre</b> anonimizzare (nome dello studio, un progetto, una sigla interna): match esatto, con il tag che scegli — anche uno nuovo. <b>Restano salvati su questo computer</b> (prefs.json).</div>
    <div class="ct-add">
      <input id="ctVal" data-i18n-ph="ct_val_ph" placeholder="es. Istituto Elvetico">
      <input id="ctTag" list="ctTagList" data-i18n-ph="ct_tag_ph" placeholder="TAG (es. ORG)">
      <datalist id="ctTagList"></datalist>
      <button class="mini" onclick="addTerm()" data-i18n="ct_add">Aggiungi</button>
    </div>
    <div class="ct-list" id="ctList"></div>
    <div class="cfg-status" id="tgStatus"></div>
    <div class="cfg-btns" style="margin-top:14px">
      <button class="btn" onclick="saveTags()">💾 <span data-i18n="cfg_save">Salva</span></button>
      <button class="ghost" onclick="closeTags()" data-i18n="cfg_cancel">Annulla</button>
    </div>
    <div class="cfg-note" id="tgNote"></div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
let DATA = null;            // ultimo risultato analyze
let MAP = {};              // {placeholder -> valore} sessione corrente
const off = new Set();     // label nascoste nella preview
let L = 'it';              // lingua UI corrente
let TAGS = [];             // legenda dei tag servita da /settings
let EXCL = new Set();      // tag da NON anonimizzare (scelta corrente)
let TAGS_LOADED = false;   // /settings ha risposto -> possiamo mandare gli override
let MAPPING = true;        // dizionario reversibile on/off (switch nella card di input)
let SRC_DOC = null;        // PDF caricato, renderizzato dal server (colonna sinistra)
let OUT_DOC = null;        // PDF anonimizzato (colonna destra), generato pigramente
let VIEW = 'prev';         // vista attiva a destra: prev | text | pdf
let MODE = 1;              // 1 = Anonimizza, 2 = Deanonimizza (toggle sul brand)

/* ---- i18n (IT default, EN opzionale) ---- */
const T = {
 it:{
  tagline:"modello locale su CPU · GDPR compliant", badge:"100% in locale",
  notice:"<b>Versione in sviluppo.</b> Il modello AI non è perfetto e può commettere errori: verifica sempre il risultato prima di usarlo. Queste sono le prime versioni e il progetto è completamente <b>open source</b>. Se ti è utile, <b>lascia una ⭐ alla repo</b> e contribuisci a migliorarlo: <a href=\"https://github.com/Rizzo-AI-Academy/rizzo-pii\" target=\"_blank\" rel=\"noopener\">apri la repo su GitHub ↗</a>",
  mode_anon:"Anonimizza", mode_deanon:"Deanonimizza",
  drop_here:"Rilascia il documento — PDF, .md o .txt",
  in_title:"① Il tuo documento", in_hint:"incolla il testo o trascina un documento nella finestra",
  src_ph:"Incolla qui il testo dell'atto, del contratto o della sentenza…\n\nOppure trascina un PDF, un .md o un .txt in un punto qualsiasi della finestra.",
  go:"Anonimizza", clear:"Pulisci",
  out_title:"② Risultato", v_prev:"Anteprima", v_text:"Testo da copiare",
  v_pdf:"Anteprima PDF", v_raw:"Testo", v_opdf:"PDF censurato",
  t_prev_loading:"Renderizzo il PDF…", t_prev_err:"Anteprima del PDF non disponibile",
  t_pdf_render:"Genero il PDF anonimizzato…",
  empty_prev:"L'anteprima con le PII evidenziate apparirà qui.",
  anon_ph:"Il testo anonimizzato apparirà qui.",
  copy:"Copia testo", dl:"Scarica dizionario", dlpdf:"PDF anonimo",
  t_pdf_making:"Genero il PDF…", t_pdf_ok:"PDF anonimizzato scaricato",
  t_pdf_err:"Errore nella creazione del PDF",
  t_pdf_warn:(r,s)=>"PDF scaricato · ATTENZIONE: "+(r+s)+" valori sono rimasti in chiaro"
    +" ("+r+" non redatti, "+s+" troppo corti per essere cercati): controlla il file"
    +" prima di condividerlo",
  dict_title:"Dizionario reversibile", dict_hint:"resta solo qui, in locale",
  th_id:"ID", th_val:"Valore originale", th_type:"Tipo",
  callout:"Incolla qui la <b>risposta dell'LLM</b> (che contiene i placeholder come <span class=\"kbd\">[FULLNAME_1]</span>): l'app rimette i valori veri usando il dizionario di questa sessione. Se hai chiuso e riaperto l'app, <b>carica il dizionario .json</b> che avevi salvato.",
  r_title1:"Risposta con i placeholder", loaddict:"📁 Carica dizionario",
  rin_ph:"Incolla qui la risposta di ChatGPT…",
  rev:"Ripristina valori", r_title2:"Testo ripristinato",
  empty_rout:"Il testo con i valori reali apparirà qui.", rcopy:"Copia testo ripristinato",
  st_ent:"entità", st_uniq:"valori unici", st_model:"dal modello",
  st_regex:"da regex/checksum", st_chars:"caratteri", analyzing:"Analizzo…",
  t_need_input:"Inserisci del testo o un PDF", t_error:"Errore",
  t_copied:"Testo anonimizzato copiato", t_need_anon:"Prima anonimizza un testo",
  t_nothing_dl:"Niente da scaricare", t_dl_ok:"Dizionario scaricato",
  t_paste_restore:"Incolla la risposta da ripristinare",
  t_no_dict:"Nessun dizionario: caricane uno .json", t_restored:"Valori ripristinati",
  t_nothing_copy:"Niente da copiare", t_restored_copied:"Testo ripristinato copiato",
  t_dict_loaded:"Dizionario caricato", t_json_invalid:"JSON non valido",
  t_drag_pdf:"Formato non supportato: usa PDF, .md o .txt",
  pii_found:(n,u)=>n+" PII trovate · "+u+" valori unici",
  dict_n:n=>n+" ID nel dizionario",
  dict_loaded_n:n=>"dizionario caricato · "+n+" ID",
  dict_session:n=>"dizionario sessione · "+n+" ID",
  chars:n=>n.toLocaleString('it'),
  set_title:"Impostazioni", set_tab_server:"Server", set_tab_how:"Come funziona",
  set_tab_sec:"Sicurezza", set_tab_cred:"Crediti", cfg_close:"Chiudi",
  sec_body:"<h4>Prima di condividere</h4><ul><li><b>Rileggi sempre l'output.</b> Il modello può sbagliare: un nome fuori posto, una sigla scambiata per un'altra cosa. La rilettura è tua, non delegabile.</li><li><b>Se l'app ti avvisa, fermati.</b> Dopo il PDF può comparire «N valori sono rimasti in chiaro»: sono i <b>residui</b> (ancora leggibili nell'output) e i <b>saltati</b> (frammenti troppo corti per essere cercati senza devastare il documento). Vai a vederli.</li><li><b>Controlla i tag attivi</b> (🏷️): i tipi che deselezioni vengono rilevati ma <b>lasciati in chiaro</b> apposta. È una scelta tua, ma va ricordata prima di mandare fuori il file.</li></ul><h4>Il dizionario è la chiave</h4><ul><li>Il file <code>dizionario_anonimizzazione.json</code> contiene <b>tutte le PII in chiaro</b>. Chi ce l'ha può deanonimizzare qualsiasi cosa: <b>vale quanto il documento originale</b>.</li><li><b>Non allegarlo mai insieme</b> al documento anonimizzato, non metterlo nella stessa cartella condivisa, non incollarlo in un LLM.</li><li>Finché il dizionario esiste, quella che hai è una <b>pseudonimizzazione</b>: per il GDPR resta dato personale. Vuoi un'anonimizzazione <b>definitiva</b>? Spegni lo switch: nessuna chiave viene creata e il ripristino diventa impossibile, per tutti.</li><li>Il dizionario della sessione vive nel browser: <b>Pulisci</b> lo cancella. I documenti stanno in memoria e muoiono con l'app: sul disco non resta niente.</li><li>Unica eccezione voluta: i <b>Termini personali</b> (🏷️ → 📌) sono salvati in chiaro in <code>prefs.json</code> su questo computer — sono i valori che hai chiesto di rilevare sempre. Rimuovili da lì se il computer cambia mani.</li></ul><h4>Quello che il testo non copre</h4><ul><li><b>Firme, timbri, loghi</b>: non sono testo, nessun modello li legge. Coprili con i <b>riquadri manuali</b> (✏️) — sotto il riquadro i pixel vengono cancellati davvero.</li><li><b>Scansioni e foto</b>: servono i file OCR. Se nella scheda Server l'OCR non risulta attivo, un PDF fotografato non può essere redatto — e l'app lo dice invece di consegnarti un file intatto.</li><li><b>Scritte verticali e a margine</b> (protocolli, sigle laterali): l'OCR le prende male. Riquadro manuale.</li></ul><h4>Quale bottone, quando</h4><ul><li><b>Copia testo</b> → per <i>conversare</i> col modello e poi ripristinare la risposta. Non porta con sé layout, firme, immagini.</li><li><b>PDF anonimo</b> → per <i>consegnare o caricare il documento</i>. È l'unico che protegge anche ciò che non è testo.</li><li>Nel dubbio: <b>PDF</b>, e rileggilo.</li></ul><h4>Rete</h4><ul><li>Il server ascolta su <code>127.0.0.1</code>: solo questo computer. Se lo esponi (<code>--host 0.0.0.0</code>, Docker su un server d'ufficio) chiunque nella rete può usarlo, e i documenti degli altri passano da lì: mettilo dietro a un accesso controllato.</li><li>Anche esposto, l'app non chiama nessuno: nessuna API, nessuna telemetria. Ciò che entra non esce.</li></ul>",
  tip_copy:"<b>Testo anonimizzato negli appunti.</b> Incollalo nella chat: la risposta che torna contiene i placeholder e in modalità <b>Deanonimizza</b> ridiventa leggibile. Non porta con sé impaginazione, firme e immagini — per quelle serve il PDF.",
  tip_pdf:"<b>Il documento vero, redatto.</b> Layout intatto, PII rimosse dal contenuto del file, pixel cancellati sotto i riquadri manuali, metadati e allegati ripuliti. È la scelta giusta per caricare o consegnare il file. <span class=\"warn\">Rileggilo prima di condividerlo:</span> se qualcosa resta in chiaro l'app te lo dice.",
  tip_dict:"<span class=\"warn\">🔒 Contiene tutte le PII in chiaro.</span> È la chiave che deanonimizza: vale quanto il documento originale. Serve a ripristinare in una sessione futura. Tienilo separato dal documento anonimizzato, non allegarlo mai insieme e non incollarlo in un LLM.",
  how_body:"<h4>Che cosa fa</h4><p>AnonimAI trova i dati personali in un testo o in un PDF e li sostituisce con segnaposto numerati (<code>[FULLNAME_1]</code>, <code>[IBAN_1]</code>…): puoi usare un LLM di frontiera senza mandargli i dati veri. Con il <b>dizionario reversibile</b> attivo, la risposta dell'LLM torna in chiaro in locale (modalità <b>Deanonimizza</b>).</p><h4>Perché i dati non escono</h4><ul><li><b>Tutto gira sulla tua macchina</b>: il modello (~0,3B parametri, base mmBERT) è caricato in locale su CPU. A runtime l'app non fa chiamate di rete: niente API, niente telemetria, nessuna CDN.</li><li><b>I documenti stanno in memoria</b>, mai su disco: valgono quanto la sessione e muoiono col processo.</li><li><b>Il dizionario non viaggia sulla rete</b>: resta qui. Quando serve al server per redigere il PDF viene ricostruito lì e muore con la richiesta.</li><li>Il server ascolta su <code>127.0.0.1</code>: dall'esterno non è raggiungibile, a meno che tu non lo configuri apposta.</li></ul><h4>Come trova i dati personali</h4><ul><li><b>Modello</b>: 22 categorie (nomi, indirizzi, date, importi, targhe, ragioni sociali, dati catastali…).</li><li><b>Rete regex + checksum</b>: email, telefoni, URL e gli identificativi che si validano matematicamente — IBAN, codice fiscale, partita IVA, carta di credito. Dove il checksum torna, <b>vince sul modello</b>.</li><li><b>OCR</b> per i PDF scansionati o fotografati e per le carte intestate incorporate come immagine.</li><li><b>Riquadri manuali</b> (✏️) per firme e timbri: non sono testo, nessun modello li legge.</li></ul><h4>Che cosa succede dentro il PDF</h4><p>La redazione è <b>vera</b>: i caratteri escono dal contenuto del file, non ci si disegna sopra un rettangolo; sotto i riquadri manuali i pixel vengono cancellati. Si ripuliscono anche metadati, annotazioni, campi modulo e segnalibri, e gli allegati incorporati vengono rimossi. Alla fine l'app <b>rilegge il documento che ha prodotto</b> (ri-OCR incluso sulle scansioni) e ti avvisa se un valore è rimasto leggibile.</p><h4>Che cosa NON ti promette</h4><ul><li>Il modello può sbagliare: <b>rileggi sempre il risultato</b> prima di condividerlo. Quando un valore resta in chiaro l'app te lo dice, invece di consegnarti un file che <i>sembra</i> anonimo.</li><li>Col dizionario <b>attivo</b> ottieni una <b>pseudonimizzazione</b>: reversibile per chi ha il dizionario e, per il GDPR, ancora dato personale finché quel dizionario esiste. Custodiscilo come custodiresti l'originale.</li><li>Col dizionario <b>disattivato</b> l'anonimizzazione è <b>definitiva</b>: nessuna chiave viene creata e dall'output non si risale ai valori.</li></ul>",
  cred_body:"<h4>Il progetto originale</h4><p>AnonimAI è costruito su <b>rizzo-pii</b>, di <b>Simone Rizzo</b> — Rizzo AI Academy. Il modello, il dataset e la pipeline di training vengono da lì.</p><div class=\"kv\"><b>Repository</b><span><a href=\"https://github.com/Rizzo-AI-Academy/rizzo-pii\" target=\"_blank\" rel=\"noopener\">github.com/Rizzo-AI-Academy/rizzo-pii ↗</a></span></div><div class=\"kv\"><b>Sito</b><span><a href=\"https://www.rizzoaiacademy.com\" target=\"_blank\" rel=\"noopener\">www.rizzoaiacademy.com ↗</a></span></div><div class=\"kv\"><b>Modello</b><span><span id=\"credModel\">rizzo-pii:0.3B</span></span></div><div class=\"kv\"><b>Pesi</b><span><a href=\"https://huggingface.co/rizzoaiacademy/rizzo-pii-0.3B\" target=\"_blank\" rel=\"noopener\">rizzoaiacademy/rizzo-pii-0.3B ↗</a> · base <a href=\"https://huggingface.co/jhu-clsp/mmBERT-base\" target=\"_blank\" rel=\"noopener\">jhu-clsp/mmBERT-base ↗</a></span></div><div class=\"kv\"><b>Dataset</b><span><a href=\"https://huggingface.co/datasets/rizzoaiacademy/anonimizzazione-testi-italiano\" target=\"_blank\" rel=\"noopener\">rizzoaiacademy/anonimizzazione-testi-italiano ↗</a></span></div><h4>Licenze</h4><ul><li><b>Codice sorgente</b>: MIT — © 2026 Simone Rizzo, Rizzo AI Academy.</li><li><b>Binari distribuiti</b>: AGPL-3.0, perché incorporano PyMuPDF (AGPL-3.0 o licenza commerciale Artifex).</li><li><b>Icone</b>: OpenMoji — CC BY-SA 4.0.</li><li><b>Librerie</b>: PyTorch · Transformers · tokenizers · safetensors (Apache-2.0) · Flask (BSD-3-Clause) · Tauri (MIT o Apache-2.0) · Tesseract, dentro PyMuPDF (Apache-2.0).</li></ul><p>L'elenco completo e verificabile è in <code>THIRD_PARTY_LICENSES.md</code> nel repository.</p>",
  cfg_title:"Configurazione server", cfg_host:"Indirizzo", cfg_port:"Porta",
  cfg_check:"Verifica porta", cfg_save:"Salva", cfg_cancel:"Annulla",
  cfg_available:"Porta disponibile ✓", cfg_in_use:"Porta occupata ✗",
  cfg_saved:"Configurazione salvata (riavvia per applicare)",
  cfg_restart_note:"Le modifiche avranno effetto al prossimo avvio.",
  tg_title:"Tag da anonimizzare",
  tg_sub:"Deseleziona i tipi che vuoi <b>lasciare in chiaro</b>: verranno comunque rilevati, ma non sostituiti da un placeholder.",
  tg_all:"Seleziona tutti", tg_none:"Nessuno",
  tg_saved:"Selezione salvata", tg_err:"Salvataggio non riuscito",
  tg_note:p=>"Salvato in "+p+" · vale anche per l'API /analyze.",
  ct_title:"Termini personali",
  ct_sub:"Valori che vuoi <b>sempre</b> anonimizzare (nome dello studio, un progetto, una sigla interna): match esatto, con il tag che scegli — anche uno nuovo. <b>Restano salvati su questo computer</b> (prefs.json).",
  ct_val_ph:"es. Istituto Elvetico", ct_tag_ph:"TAG (es. ORG)", ct_add:"Aggiungi",
  ct_del:"Rimuovi", ct_short:"Termine troppo corto: servono almeno 3 caratteri",
  ct_badtag:"Tag non valido: 2-20 tra lettere, cifre e _",
  tg_env:"⚠️ La variabile d'ambiente PII_EXCLUDE_TAGS ha la precedenza al prossimo avvio.",
  tg_count:(on,tot)=>on+" di "+tot+" tag anonimizzati",
  st_excl:"tag esclusi",
  box_btn:"Riquadri",
  t_doc_expired:"Documento non piu' in memoria: ricaricalo per rivedere le pagine.",
  t_box_hint:"Disegna un rettangolo su una firma o un timbro. Click su un riquadro per eliminarlo.",
  t_box_del:"Click per eliminare il riquadro",
  t_box_added:n=>n===1?"1 riquadro manuale: verrà oscurato nel PDF"
    :n+" riquadri manuali: verranno oscurati nel PDF",
  map_ttl:"Dizionario <span class=\"lbl-long\">reversibile</span>", map_on:"ATTIVO", map_off:"DISATTIVO",
  map_sub_on:"Ogni PII riceve un ID: potrai ripristinare i valori veri dalla risposta dell'LLM.",
  map_sub_off:"Anonimizzazione <b>definitiva</b>: nessuna chiave placeholder → valore viene creata, salvata o scaricabile. Il ripristino non sarà possibile.",
  t_map_on:"Dizionario reversibile attivo", t_map_off:"Dizionario disattivato: anonimizzazione definitiva",
  dict_off:"Nessun dizionario: l'anonimizzazione di questo testo è <b>definitiva</b>.",
  dict_off_hint:"lo switch è su DISATTIVO",
  r_off:"Lo switch <b>Dizionario reversibile</b> è su DISATTIVO: le nuove anonimizzazioni non producono chiavi. Qui puoi comunque ripristinare con un dizionario <b>.json salvato in precedenza</b>.",
 },
 en:{
  tagline:"local model on CPU · GDPR compliant", badge:"100% local",
  notice:"<b>Work in progress.</b> The AI model isn't perfect and can make mistakes: always double-check the result before relying on it. These are the very first versions and the project is fully <b>open source</b>. If you find it useful, <b>leave a ⭐ on the repo</b> and help improve it: <a href=\"https://github.com/Rizzo-AI-Academy/rizzo-pii\" target=\"_blank\" rel=\"noopener\">open the repo on GitHub ↗</a>",
  mode_anon:"Anonymize", mode_deanon:"De-anonymize",
  drop_here:"Drop the document — PDF, .md or .txt",
  in_title:"① Your document", in_hint:"paste text or drop a document anywhere in the window",
  src_ph:"Paste here the text of the deed, contract or judgment…\n\nOr drop a PDF, .md or .txt anywhere in the window.",
  go:"Anonymize", clear:"Clear",
  out_title:"② Result", v_prev:"Preview", v_text:"Text to copy",
  v_pdf:"PDF preview", v_raw:"Text", v_opdf:"Redacted PDF",
  t_prev_loading:"Rendering the PDF…", t_prev_err:"PDF preview not available",
  t_pdf_render:"Building the anonymized PDF…",
  empty_prev:"The preview with highlighted PII will appear here.",
  anon_ph:"The anonymized text will appear here.",
  copy:"Copy text", dl:"Download dictionary", dlpdf:"Anonymized PDF",
  t_pdf_making:"Building the PDF…", t_pdf_ok:"Anonymized PDF downloaded",
  t_pdf_err:"Error while creating the PDF",
  t_pdf_warn:(r,s)=>"PDF downloaded · WARNING: "+(r+s)+" values were left in clear"
    +" ("+r+" not redacted, "+s+" too short to be searched safely): check the file"
    +" before sharing it",
  dict_title:"Reversible dictionary", dict_hint:"stays here only, locally",
  th_id:"ID", th_val:"Original value", th_type:"Type",
  callout:"Paste here the <b>LLM's answer</b> (containing placeholders like <span class=\"kbd\">[FULLNAME_1]</span>): the app puts the real values back using this session's dictionary. If you closed and reopened the app, <b>load the .json dictionary</b> you saved.",
  r_title1:"Answer with placeholders", loaddict:"📁 Load dictionary",
  rin_ph:"Paste ChatGPT's answer here…",
  rev:"Restore values", r_title2:"Restored text",
  empty_rout:"The text with the real values will appear here.", rcopy:"Copy restored text",
  st_ent:"entities", st_uniq:"unique values", st_model:"from the model",
  st_regex:"from regex/checksum", st_chars:"characters", analyzing:"Analyzing…",
  t_need_input:"Enter some text or a PDF", t_error:"Error",
  t_copied:"Anonymized text copied", t_need_anon:"Anonymize a text first",
  t_nothing_dl:"Nothing to download", t_dl_ok:"Dictionary downloaded",
  t_paste_restore:"Paste the answer to restore",
  t_no_dict:"No dictionary: load a .json one", t_restored:"Values restored",
  t_nothing_copy:"Nothing to copy", t_restored_copied:"Restored text copied",
  t_dict_loaded:"Dictionary loaded", t_json_invalid:"Invalid JSON",
  t_drag_pdf:"Unsupported format: use PDF, .md or .txt",
  pii_found:(n,u)=>n+" PII found · "+u+" unique values",
  dict_n:n=>n+" IDs in the dictionary",
  dict_loaded_n:n=>"dictionary loaded · "+n+" IDs",
  dict_session:n=>"session dictionary · "+n+" IDs",
  chars:n=>n.toLocaleString('en'),
  set_title:"Settings", set_tab_server:"Server", set_tab_how:"How it works",
  set_tab_sec:"Security", set_tab_cred:"Credits", cfg_close:"Close",
  sec_body:"<h4>Before you share</h4><ul><li><b>Always re-read the output.</b> The model can be wrong: a name missed, an abbreviation mistaken for something else. That check is yours and cannot be delegated.</li><li><b>If the app warns you, stop.</b> After the PDF you may see “N values were left in the clear”: those are <b>residuals</b> (still readable in the output) and <b>skipped</b> values (fragments too short to search for without wrecking the document). Go and look at them.</li><li><b>Check the active tags</b> (🏷️): the types you untick are still detected but <b>left in the clear</b> on purpose. Your choice — worth remembering before the file goes out.</li></ul><h4>The dictionary is the key</h4><ul><li>The file <code>dizionario_anonimizzazione.json</code> holds <b>every PII in the clear</b>. Whoever has it can de-anonymise anything: <b>it is worth as much as the original document</b>.</li><li><b>Never attach it together</b> with the anonymised document, never put it in the same shared folder, never paste it into an LLM.</li><li>As long as the dictionary exists you have <b>pseudonymisation</b>: under the GDPR that is still personal data. Want <b>irreversible</b> anonymisation? Switch the dictionary off: no key is created and restoring becomes impossible, for everyone.</li><li>The session dictionary lives in the browser: <b>Clear</b> deletes it. Documents live in memory and die with the app: nothing is left on disk.</li><li>One deliberate exception: <b>Personal terms</b> (🏷️ → 📌) are saved in the clear in <code>prefs.json</code> on this computer — they are the values you asked to always detect. Remove them there if the computer changes hands.</li></ul><h4>What text does not cover</h4><ul><li><b>Signatures, stamps, logos</b>: not text, no model reads them. Cover them with the <b>manual boxes</b> (✏️) — under the box the pixels are actually erased.</li><li><b>Scans and photos</b>: they need the OCR files. If OCR is not active, a photographed PDF cannot be redacted — and the app says so instead of handing you an untouched file.</li><li><b>Vertical and margin writing</b> (protocol stamps, side codes): OCR reads them badly. Use a manual box.</li></ul><h4>Which button, when</h4><ul><li><b>Copy text</b> → to <i>talk</i> to the model and restore its answer afterwards. Carries no layout, signatures or images.</li><li><b>Anonymized PDF</b> → to <i>hand over or upload the document</i>. The only one that also protects what is not text.</li><li>When in doubt: <b>PDF</b>, and re-read it.</li></ul><h4>Network</h4><ul><li>The server listens on <code>127.0.0.1</code>: this machine only. If you expose it (<code>--host 0.0.0.0</code>, Docker on an office server) anyone on the network can use it and other people's documents go through it: put it behind controlled access.</li><li>Even exposed, the app calls nobody: no API, no telemetry. What comes in does not go out.</li></ul>",
  tip_copy:"<b>Anonymised text in the clipboard.</b> Paste it into the chat: the answer comes back with the placeholders and becomes readable again in <b>De-anonymize</b> mode. It carries no layout, signatures or images — for those you need the PDF.",
  tip_pdf:"<b>The real document, redacted.</b> Layout intact, PII removed from the file's content, pixels erased under the manual boxes, metadata and attachments scrubbed. The right choice to upload or hand over the file. <span class=\"warn\">Re-read it before sharing:</span> if anything is left in the clear the app tells you.",
  tip_dict:"<span class=\"warn\">🔒 It holds every PII in the clear.</span> This is the key that de-anonymises: worth as much as the original document. Use it to restore in a later session. Keep it apart from the anonymised document, never attach them together, never paste it into an LLM.",
  how_body:"<h4>What it does</h4><p>AnonimAI finds personal data in text or in a PDF and replaces it with numbered placeholders (<code>[FULLNAME_1]</code>, <code>[IBAN_1]</code>…), so you can use a frontier LLM without sending it the real data. With the <b>reversible dictionary</b> on, the LLM's answer is restored locally (<b>De-anonymize</b> mode).</p><h4>Why the data never leaves</h4><ul><li><b>Everything runs on your machine</b>: the model (~0.3B parameters, mmBERT backbone) is loaded locally on CPU. At runtime the app makes no network calls: no API, no telemetry, no CDN.</li><li><b>Documents live in memory</b>, never on disk: they last as long as the session and die with the process.</li><li><b>The dictionary never travels</b>: it stays here. When the server needs it to redact the PDF it is rebuilt there and dies with the request.</li><li>The server listens on <code>127.0.0.1</code>: unreachable from outside unless you configure it otherwise.</li></ul><h4>How it finds personal data</h4><ul><li><b>Model</b>: 22 categories (names, addresses, dates, amounts, plates, company names, land-registry data…).</li><li><b>Regex + checksum net</b>: emails, phone numbers, URLs and the identifiers that validate mathematically — IBAN, Italian tax code, VAT number, credit cards. Where the checksum holds, it <b>overrides the model</b>.</li><li><b>OCR</b> for scanned or photographed PDFs and for letterheads embedded as images.</li><li><b>Manual boxes</b> (✏️) for signatures and stamps: they are not text, no model reads them.</li></ul><h4>What happens inside the PDF</h4><p>Redaction is <b>real</b>: the glyphs are removed from the file's content, not covered with a rectangle; under manual boxes the pixels are erased. Metadata, annotations, form fields and bookmarks are scrubbed too, and embedded attachments are removed. Finally the app <b>re-reads the document it produced</b> (re-OCR included on scans) and warns you if a value is still readable.</p><h4>What it does NOT promise</h4><ul><li>The model can be wrong: <b>always re-read the result</b> before sharing it. When a value stays in the clear the app says so, instead of handing you a file that merely <i>looks</i> anonymous.</li><li>With the dictionary <b>on</b> you get <b>pseudonymisation</b>: reversible for whoever holds the dictionary and, under the GDPR, still personal data as long as that dictionary exists. Guard it like the original.</li><li>With the dictionary <b>off</b> anonymisation is <b>final</b>: no key is created and the output cannot be traced back.</li></ul>",
  cred_body:"<h4>The original project</h4><p>AnonimAI is built on <b>rizzo-pii</b>, by <b>Simone Rizzo</b> — Rizzo AI Academy. The model, the dataset and the training pipeline come from there.</p><div class=\"kv\"><b>Repository</b><span><a href=\"https://github.com/Rizzo-AI-Academy/rizzo-pii\" target=\"_blank\" rel=\"noopener\">github.com/Rizzo-AI-Academy/rizzo-pii ↗</a></span></div><div class=\"kv\"><b>Website</b><span><a href=\"https://www.rizzoaiacademy.com\" target=\"_blank\" rel=\"noopener\">www.rizzoaiacademy.com ↗</a></span></div><div class=\"kv\"><b>Model</b><span><span id=\"credModel\">rizzo-pii:0.3B</span></span></div><div class=\"kv\"><b>Weights</b><span><a href=\"https://huggingface.co/rizzoaiacademy/rizzo-pii-0.3B\" target=\"_blank\" rel=\"noopener\">rizzoaiacademy/rizzo-pii-0.3B ↗</a> · backbone <a href=\"https://huggingface.co/jhu-clsp/mmBERT-base\" target=\"_blank\" rel=\"noopener\">jhu-clsp/mmBERT-base ↗</a></span></div><div class=\"kv\"><b>Dataset</b><span><a href=\"https://huggingface.co/datasets/rizzoaiacademy/anonimizzazione-testi-italiano\" target=\"_blank\" rel=\"noopener\">rizzoaiacademy/anonimizzazione-testi-italiano ↗</a></span></div><h4>Licences</h4><ul><li><b>Source code</b>: MIT — © 2026 Simone Rizzo, Rizzo AI Academy.</li><li><b>Released binaries</b>: AGPL-3.0, because they bundle PyMuPDF (AGPL-3.0 or Artifex commercial licence).</li><li><b>Icons</b>: OpenMoji — CC BY-SA 4.0.</li><li><b>Libraries</b>: PyTorch · Transformers · tokenizers · safetensors (Apache-2.0) · Flask (BSD-3-Clause) · Tauri (MIT or Apache-2.0) · Tesseract, inside PyMuPDF (Apache-2.0).</li></ul><p>The full, verifiable list is in <code>THIRD_PARTY_LICENSES.md</code> in the repository.</p>",
  cfg_title:"Server configuration", cfg_host:"Host", cfg_port:"Port",
  cfg_check:"Check port", cfg_save:"Save", cfg_cancel:"Cancel",
  cfg_available:"Port available ✓", cfg_in_use:"Port in use ✗",
  cfg_saved:"Config saved (restart to apply)",
  cfg_restart_note:"Changes take effect on next startup.",
  tg_title:"Tags to anonymize",
  tg_sub:"Untick the types you want to <b>leave in clear text</b>: they are still detected, but not replaced by a placeholder.",
  tg_all:"Select all", tg_none:"None",
  tg_saved:"Selection saved", tg_err:"Could not save",
  tg_note:p=>"Saved to "+p+" · also applies to the /analyze API.",
  ct_title:"Personal terms",
  ct_sub:"Values you <b>always</b> want anonymized (your firm's name, a project, an internal code): exact match, with the tag you choose — even a new one. <b>They stay saved on this computer</b> (prefs.json).",
  ct_val_ph:"e.g. Istituto Elvetico", ct_tag_ph:"TAG (e.g. ORG)", ct_add:"Add",
  ct_del:"Remove", ct_short:"Term too short: at least 3 characters needed",
  ct_badtag:"Invalid tag: 2-20 letters, digits or _",
  tg_env:"⚠️ The PII_EXCLUDE_TAGS environment variable takes precedence on next startup.",
  tg_count:(on,tot)=>on+" of "+tot+" tags anonymized",
  st_excl:"excluded tags",
  box_btn:"Boxes",
  t_doc_expired:"Document no longer in memory: load it again to see the pages.",
  t_box_hint:"Draw a rectangle over a signature or a stamp. Click a box to remove it.",
  t_box_del:"Click to remove this box",
  t_box_added:n=>n===1?"1 manual box: it will be blacked out in the PDF"
    :n+" manual boxes: they will be blacked out in the PDF",
  map_ttl:"<span class=\"lbl-long\">Reversible </span>dictionary", map_on:"ON", map_off:"OFF",
  map_sub_on:"Every PII gets an ID: you will be able to restore the real values from the LLM's answer.",
  map_sub_off:"<b>Irreversible</b> anonymization: no placeholder → value key is created, stored or downloadable. Restoring will not be possible.",
  t_map_on:"Reversible dictionary on", t_map_off:"Dictionary off: anonymization is irreversible",
  dict_off:"No dictionary: anonymization of this text is <b>irreversible</b>.",
  dict_off_hint:"the switch is OFF",
  r_off:"The <b>Reversible dictionary</b> switch is OFF: new anonymizations produce no keys. You can still restore here using a <b>.json dictionary saved earlier</b>.",
 }
};
const tt=k=>T[L][k];

function routEmpty(){
  return '<div class="empty"><div class="big">🔓</div><div>'+tt('empty_rout')+'</div></div>';
}

function applyLang(l){
  L=(l==='en')?'en':'it';
  localStorage.setItem('pii_lang',L);
  document.documentElement.lang=L;$('lang').value=L;
  document.querySelectorAll('[data-i18n]').forEach(el=>{
    const v=T[L][el.getAttribute('data-i18n')]; if(v!=null) el.innerHTML=v;});
  document.querySelectorAll('[data-i18n-ph]').forEach(el=>{
    const v=T[L][el.getAttribute('data-i18n-ph')]; if(v!=null) el.placeholder=v;});
  $('modeLabel').textContent=MODE===1?tt('mode_anon'):tt('mode_deanon');
  if(!$('rout')._raw) $('rout').innerHTML=routEmpty();
  renderMapping();
  if(TAGS.length && $('tagsOverlay').classList.contains('open')) renderTags();
  if(DATA) render();
}

/* ---- scroll sincronizzato editor (sx) <-> anteprima/testo (dx) ---- */
let syncing=false;
function matchScroll(target,from){
  const rf=from.scrollHeight-from.clientHeight, rt=target.scrollHeight-target.clientHeight;
  target.scrollTop = rf>0 ? (from.scrollTop/rf)*rt : 0;
  // con lo zoom nasce l'asse X: senza questo le due colonne restano allineate
  // in verticale e sfasate in orizzontale (sulle textarea wf e' 0, quindi inerte)
  const wf=from.scrollWidth-from.clientWidth, wt=target.scrollWidth-target.clientWidth;
  target.scrollLeft = wf>0 ? (from.scrollLeft/wf)*wt : 0;
}
function linkScroll(a,b){
  a.addEventListener('scroll',()=>{
    if(syncing)return; syncing=true; matchScroll(b,a);
    setTimeout(()=>syncing=false,0);});   // reset robusto (rAF puo' non scattare in bg)
}

/* ---- colore deterministico per tipo di tag (due rampe: tema chiaro/scuro) ---- */
function hue(s){let h=0;for(const c of s)h=(h*31+c.charCodeAt(0))%360;return h;}
function colors(label){const h=hue(label);
  if(document.documentElement.dataset.theme==='scuro')
    return {bg:`hsl(${h} 40% 20%)`,bd:`hsl(${h} 35% 38%)`,tx:`hsl(${h} 70% 78%)`};
  return {bg:`hsl(${h} 56% 96%)`,bd:`hsl(${h} 42% 81%)`,tx:`hsl(${h} 40% 38%)`};}

/* ---- tema chiaro/scuro (standard StudIA: attributo su <html>, solo token) ---- */
function applyTheme(t){
  document.documentElement.dataset.theme=t;
  localStorage.setItem('pii_theme',t);
  if(DATA)render();                       // i colori dei tag cambiano rampa
}
$('thTog').onclick=()=>applyTheme(
  document.documentElement.dataset.theme==='scuro'?'chiaro':'scuro');

function toast(msg,ok=true,ms=1800){const t=$('toast');t.textContent=msg;t.className='show'+(ok?' ok':'');
  clearTimeout(t._t);t._t=setTimeout(()=>t.className='',ms);}

/* ---- render di un PDF a video ----------------------------------------------
   Le pagine arrivano gia' renderizzate dal server (/doc/<id>/page/<n>.png):
   niente viewer PDF del browser (dentro Tauri non c'e' garanzia che ci sia) e
   niente libreria JS esterna (l'app e' offline, nessuna CDN raggiungibile).
   `loading=lazy` -> un PDF di 200 pagine non scarica 200 immagini all'apertura. */
let EXPIRED=false;
function renderPages(el,doc){
  el.innerHTML='';EXPIRED=false;
  el.style.setProperty('--z',ZOOM);
  for(let i=0;i<doc.n_pages;i++){
    const pg=document.createElement('div');pg.className='pg';pg.dataset.page=i;
    const im=document.createElement('img');
    im.loading='lazy';im.alt=(i+1)+' / '+doc.n_pages;   // alt = pagina: se il render manca si vede quale
    im.src=`/doc/${doc.doc_id}/page/${i}.png`;
    // il documento vive in una LRU in memoria: se e' scaduto la pagina da' 404 e
    // qui resterebbe un buco bianco. Meglio dirlo (una volta sola, non per pagina).
    im.onerror=()=>{if(!EXPIRED){EXPIRED=true;toast(tt('t_doc_expired'),false,6000);}};
    pg.appendChild(im);
    const n=document.createElement('span');n.className='pgn';
    n.textContent=(i+1)+' / '+doc.n_pages;pg.appendChild(n);
    el.appendChild(pg);
  }
  el.scrollTop=0;
}
function busy(el,msg){
  el.innerHTML='<div class="pdfbusy"><span class="spin"></span>'+msg+'</div>';}

/* ---- zoom delle anteprime (issue #92) ---------------------------------------
   UNO stato per due colonne: `ZOOM` si applica come `--z` su entrambe le viste,
   quindi non possono sfasarsi. Lo scroll lo specchia gia' linkScroll (ora anche
   in orizzontale). Zoom AL PUNTATORE: si legge il punto del documento sotto il
   mouse e dopo il reflow si correggono le barre perche' quel punto resti fermo.
   Niente librerie: l'app e' offline (invariante 1). */
const ZMIN=1, ZMAX=3, ZK=1.15;
const HIRES_DA=1.5;          // oltre, le pagine si richiedono a dpi maggiore
let ZOOM=1;

function zViews(){return [$('pdfSrcView'),$('pdfOutView')];}

function applyZoom(){
  for(const el of zViews()) el.style.setProperty('--z',ZOOM);
  const pct=Math.round(ZOOM*100)+'%';
  $('zLvl').textContent=pct;
  $('zLvl').classList.toggle('on',ZOOM!==1);
  $('zOut').disabled=ZOOM<=ZMIN+1e-6;
  $('zIn').disabled=ZOOM>=ZMAX-1e-6;
  scheduleDpi();
}

/* Cambio di zoom tenendo fermo il punto (cx,cy) in coordinate finestra dentro
   `el`. Se il punto non c'e' (bottoni della barra) si tiene fermo il centro. */
function zoomTo(z,el,cx,cy){
  z=Math.min(ZMAX,Math.max(ZMIN,z));
  if(Math.abs(z-ZOOM)<1e-6)return;
  const view=el||$('pdfSrcView');
  const r=view.getBoundingClientRect();
  const px=(cx==null?r.width/2:cx-r.left), py=(cy==null?r.height/2:cy-r.top);
  const docX=view.scrollLeft+px, docY=view.scrollTop+py;
  const w0=view.scrollWidth, h0=view.scrollHeight;
  ZOOM=z; applyZoom();
  /* ⚠️ Il fattore si MISURA, non si deduce da z: padding del contenitore e
     margini fra le pagine non scalano, quindi il contenuto cresce di poco meno
     del fattore di zoom. Con k=z/ZOOM il punto sotto il puntatore scivolava di
     ~7 px per passo (misurato); col rapporto vero resta fermo. */
  const kx=w0>0?view.scrollWidth/w0:1, ky=h0>0?view.scrollHeight/h0:1;
  view.scrollLeft=docX*kx-px;     // il reflow e' sincrono: si corregge subito
  view.scrollTop =docY*ky-py;
  matchScroll(view===$('pdfSrcView')?$('pdfOutView'):$('pdfSrcView'),view);
}
function zoomStep(dir){zoomTo(ZOOM*(dir>0?ZK:1/ZK),null,null,null);}
function zoomSet(z){zoomTo(z,null,null,null);}

/* ctrl/cmd + rotella: e' anche il pinch del trackpad su macOS. La rotella nuda
   resta lo scroll — toglierlo renderebbe il documento inscorribile. */
for(const el of ['pdfSrcView','pdfOutView']){
  $(el).addEventListener('wheel',e=>{
    if(!(e.ctrlKey||e.metaKey))return;
    e.preventDefault();
    zoomTo(ZOOM*Math.pow(ZK,-e.deltaY/100),$(el),e.clientX,e.clientY);
  },{passive:false});
  $(el).addEventListener('dblclick',()=>{ if(!BOX_MODE) zoomSet(ZOOM===1?2:1); });
}

/* Oltre HIRES_DA il PNG a 110 dpi sgrana: si richiedono le pagine VISIBILI a 220.
   Un timer qui e' giustificato (sono richieste di rete, non un effetto grafico):
   durante un pinch il fattore cambia dieci volte al secondo. */
let DPI_JOB=null;
function scheduleDpi(){clearTimeout(DPI_JOB);DPI_JOB=setTimeout(refreshDpi,180);}
function refreshDpi(){
  const dpi=ZOOM>HIRES_DA?220:110;
  for(const el of zViews()){
    const doc=(el===$('pdfSrcView'))?SRC_DOC:OUT_DOC;
    if(!doc)continue;
    const vr=el.getBoundingClientRect();
    el.querySelectorAll('.pg').forEach(pg=>{
      const im=pg.querySelector('img'); if(!im)return;
      const r=pg.getBoundingClientRect();
      if(r.bottom<vr.top-200||r.top>vr.bottom+200)return;   // fuori vista: resta lazy
      const src=`/doc/${doc.doc_id}/page/${pg.dataset.page}.png`+(dpi===220?'?dpi=220':'');
      if(im.getAttribute('src')===src)return;
      // si precarica e si scambia a caricamento finito: niente lampo bianco
      const pre=new Image();
      pre.onload=()=>{im.src=src;};
      pre.src=src;
    });
  }
}

/* ---- riquadri manuali per firme e timbri (issue #98 punto 2) ----------------
   L'utente disegna rettangoli sull'anteprima di sinistra; le coordinate sono
   FRAZIONI 0-1 della pagina come mostrata (nessun DPI/pt nel client: la
   geometria vive solo nel server). I riquadri viaggiano con la richiesta di
   anonimizzazione e muoiono con lei: niente stato sul server. */
let BOXES=[];let BOX_MODE=false;let DRAFT=null;
function resetBoxes(){BOXES=[];BOX_MODE=false;DRAFT=null;
  $('boxBtn').classList.remove('on');$('boxBtn').style.display='none';
  $('boxCount').textContent='';$('pdfSrcView').classList.remove('boxing');
  $('zoomG').style.display='none';ZOOM=1;applyZoom();}
function boxesChanged(){
  OUT_DOC=null;$('pdfOutView').innerHTML='';   // il PDF censurato va rifatto
  $('boxCount').textContent=BOXES.length?' '+BOXES.length:'';
  renderBoxes();
}
function toggleBoxMode(){
  if(!SRC_DOC)return;
  BOX_MODE=!BOX_MODE;
  $('boxBtn').classList.toggle('on',BOX_MODE);
  $('pdfSrcView').classList.toggle('boxing',BOX_MODE);
  if(BOX_MODE){setSrcView('pdf');toast(tt('t_box_hint'),true,3400);}
}
function renderBoxes(){
  const v=$('pdfSrcView');
  v.querySelectorAll('.pii-box:not(.draft)').forEach(b=>b.remove());
  BOXES.forEach((b,i)=>{
    const pg=v.querySelector('.pg[data-page="'+b.page+'"]');if(!pg)return;
    const d=document.createElement('div');d.className='pii-box';d.title=tt('t_box_del');
    d.style.left=(b.x0*100)+'%';d.style.top=(b.y0*100)+'%';
    d.style.width=((b.x1-b.x0)*100)+'%';d.style.height=((b.y1-b.y0)*100)+'%';
    d.onclick=e=>{e.stopPropagation();BOXES.splice(i,1);boxesChanged();};
    pg.appendChild(d);
  });
}
$('pdfSrcView').addEventListener('mousedown',e=>{
  if(!BOX_MODE)return;
  const pg=e.target.closest('.pg');
  if(!pg||e.target.classList.contains('pii-box'))return;
  e.preventDefault();
  const r=pg.getBoundingClientRect();
  DRAFT={page:+pg.dataset.page,r,
         sx:(e.clientX-r.left)/r.width,sy:(e.clientY-r.top)/r.height,
         el:document.createElement('div')};
  DRAFT.el.className='pii-box draft';pg.appendChild(DRAFT.el);
});
document.addEventListener('mousemove',e=>{
  if(!DRAFT)return;
  const r=DRAFT.r;
  DRAFT.cx=Math.min(Math.max((e.clientX-r.left)/r.width,0),1);
  DRAFT.cy=Math.min(Math.max((e.clientY-r.top)/r.height,0),1);
  const x0=Math.min(DRAFT.sx,DRAFT.cx),x1=Math.max(DRAFT.sx,DRAFT.cx);
  const y0=Math.min(DRAFT.sy,DRAFT.cy),y1=Math.max(DRAFT.sy,DRAFT.cy);
  Object.assign(DRAFT.el.style,{left:x0*100+'%',top:y0*100+'%',
    width:(x1-x0)*100+'%',height:(y1-y0)*100+'%'});
});
document.addEventListener('mouseup',()=>{
  if(!DRAFT)return;
  const {sx,sy,cx,cy,page,el}=DRAFT;el.remove();DRAFT=null;
  if(cx!=null){
    const x0=Math.min(sx,cx),x1=Math.max(sx,cx),y0=Math.min(sy,cy),y1=Math.max(sy,cy);
    // sotto ~0.8% del lato e' un click, non un riquadro
    if(x1-x0>0.008&&y1-y0>0.008){
      BOXES.push({page,x0,y0,x1,y1});
      toast(T[L].t_box_added(BOXES.length),true,2200);
    }
  }
  boxesChanged();
});

/* ---- tabs ---- */
function showTab(n){
  MODE=n;
  $('pane1').classList.toggle('on',n===1);$('pane2').classList.toggle('on',n===2);
  $('modeLabel').textContent=n===1?tt('mode_anon'):tt('mode_deanon');
}
function toggleMode(){showTab(MODE===1?2:1);}

/* ---- documento caricato: anteprima renderizzata (sx) ----------------------
   Appena si sceglie un PDF lo si manda a /preview: il server lo tiene in memoria,
   ne ritorna il testo estratto e le pagine da renderizzare. Da li' in poi la
   colonna sinistra ha due viste, "Anteprima PDF" (default) e "Testo".
   Per .md/.txt non c'e' niente da renderizzare: resta la sola textarea. */
function setSrcView(v){
  const p=(v==='pdf'&&SRC_DOC);
  $('sPdf').classList.toggle('on',!!p);$('sText').classList.toggle('on',!p);
  $('pdfSrcView').style.display=p?'':'none';
  $('src').style.display=p?'none':'';
}

async function onFile(f){
  $('fileName').textContent='📎 '+f.name;
  SRC_DOC=null;$('srcTabs').style.display='none';$('inHint').style.display='';
  resetBoxes();                              // documento nuovo -> riquadri suoi
  setSrcView('text');
  if(!(f.type==='application/pdf'||/\.pdf$/i.test(f.name)))return;
  $('inHint').textContent=tt('t_prev_loading');
  busy($('pdfSrcView'),tt('t_prev_loading'));
  $('srcTabs').style.display='';$('pdfSrcView').style.display='';$('src').style.display='none';
  $('sPdf').classList.add('on');$('sText').classList.remove('on');
  try{
    const fd=new FormData();fd.append('pdf',f);
    const r=await fetch('/preview',{method:'POST',body:fd});
    const d=await r.json();
    if(!r.ok)throw new Error(d.error||'');
    SRC_DOC=d;$('src').value=d.text||'';
    renderPages($('pdfSrcView'),d);
    $('boxBtn').style.display='';            // c'e' un PDF: i riquadri hanno una tela
    $('zoomG').style.display='';             // ...e lo zoom ha qualcosa da ingrandire
    $('inHint').style.display='none';
  }catch(e){
    SRC_DOC=null;$('srcTabs').style.display='none';setSrcView('text');
    $('inHint').innerHTML=tt('in_hint');$('inHint').style.display='';
    toast(tt('t_prev_err'),false);          // il file resta valido: l'analisi funziona lo stesso
  }
}

/* ---- analyze ---- */
async function run(){
  const file=$('pdf').files[0];const text=$('src').value.trim();
  if(!file&&!text){toast(tt('t_need_input'),false);return;}
  $('go').disabled=true;const old=$('go').innerHTML;
  $('go').innerHTML='<span class="spin"></span> '+tt('analyzing');
  try{
    let resp;
    // override della UI. Se /settings non ha risposto non mandiamo nulla: comanda il server.
    const excl=TAGS_LOADED?[...EXCL]:null;
    if(file){const fd=new FormData();fd.append('pdf',file);
      if(excl){fd.append('exclude_tags',excl.join(','));fd.append('include_mapping',MAPPING?'1':'0');}
      resp=await fetch('/analyze',{method:'POST',body:fd});}
    else{const body={text};if(excl){body.exclude_tags=excl;body.include_mapping=MAPPING;}
      resp=await fetch('/analyze',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(body)});}
    const d=await resp.json();
    if(!resp.ok){toast(d.error||tt('t_error'),false);return;}
    if(d.source_text&&file)$('src').value=d.source_text;
    DATA=d;off.clear();
    // senza dizionario non tocchiamo MAP ne' il localStorage: nessuna chiave nuova nasce
    if(d.mapping_enabled!==false){MAP=d.mapping;localStorage.setItem('pii_map',JSON.stringify(MAP));}
    render();
    toast(T[L].pii_found(d.n_entities,d.n_unique));
  }catch(e){toast(tt('t_error')+': '+e.message,false);}
  finally{$('go').disabled=false;$('go').innerHTML=old;}
}

function render(){
  const d=DATA;
  OUT_DOC=null;$('pdfOutView').innerHTML='';  // risultato nuovo -> il PDF censurato va rifatto
  $('dictCard').style.display='';            // mostra la card dizionario (sotto le due colonne)
  document.querySelector('.app').classList.add('has-result');  // -> scroll pagina, niente schiacciamento
  // preview evidenziata
  const prev=$('prev');prev.innerHTML='';prev.style.display='';$('emptyPrev').style.display='none';
  for(const s of d.segments){
    if(s.label){
      const c=colors(s.label);const sp=document.createElement('span');
      sp.className='ph'+(off.has(s.label)?' dim':'');
      sp.style.background=c.bg;sp.style.borderColor=c.bd;sp.style.color=c.tx;
      // senza dizionario il server non manda il valore originale: niente da mostrare al passaggio
      sp.title=(s.t?s.t+'\n':'')+`(${s.src}${s.validated?' · checksum ✓':''})`;
      sp.innerHTML=s.ph.replace(/[\[\]]/g,'')+(s.validated?'<span class="ck">✓</span>':'');
      prev.appendChild(sp);
    }else prev.appendChild(document.createTextNode(s.t));
  }
  // testo da copiare
  $('anon').value=d.anonymized_text;
  // meta
  $('meta').innerHTML=
    `<span class="stat"><b>${d.n_entities}</b> ${tt('st_ent')}</span>`+
    `<span class="stat"><b>${d.n_unique}</b> ${tt('st_uniq')}</span>`+
    `<span class="stat"><b>${(d.by_source.modello||0)}</b> ${tt('st_model')}</span>`+
    `<span class="stat"><b>${(d.by_source.regex||0)}</b> ${tt('st_regex')}</span>`+
    `<span class="stat"><b>${T[L].chars(d.n_chars)}</b> ${tt('st_chars')}</span>`+
    ((d.excluded_tags&&d.excluded_tags.length)
      ? `<span class="stat" title="${d.excluded_tags.join(', ')}"><b>${d.excluded_tags.length}</b> ${tt('st_excl')}</span>` : '');
  // legenda cliccabile (toggle highlight)
  const lg=$('legend');lg.innerHTML='';
  for(const [k,v] of Object.entries(d.by_label)){
    const c=colors(k);const el=document.createElement('span');
    el.className='chip'+(off.has(k)?' off':'');
    el.innerHTML=`<span class="sw" style="background:${c.bd}"></span>${k}<span class="n">${v}</span>`;
    el.onclick=()=>{off.has(k)?off.delete(k):off.add(k);render();};
    lg.appendChild(el);
  }
  // dizionario (assente quando lo switch e' su DISATTIVO)
  const hasMap=d.mapping_enabled!==false;
  const rows=$('maprows');rows.innerHTML='';
  const keys=hasMap?Object.keys(d.mapping):[];
  $('tablewrap').style.display=keys.length?'':'none';
  $('dictNone').style.display=hasMap?'none':'';
  $('dictHint').innerHTML=hasMap?tt('dict_hint'):tt('dict_off_hint');
  $('dl').style.display=hasMap?'':'none';
  for(const ph of keys){const lab=ph.slice(1,ph.lastIndexOf('_'));const c=colors(lab);
    const tr=document.createElement('tr');
    tr.innerHTML=`<td class="k" style="color:${c.tx}">${ph}</td>`+
      `<td class="v">${escapeHtml(d.mapping[ph])}</td>`+
      `<td><span class="chip" style="cursor:default"><span class="sw" style="background:${c.bd}"></span>${lab}</span></td>`;
    rows.appendChild(tr);}
  $('ulock').textContent=keys.length?T[L].dict_n(keys.length):'';
  if(VIEW==='pdf')setView('pdf');            // stavo guardando il PDF: lo rigenero
}

function escapeHtml(s){return s.replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));}

/* ---- view toggle (dx): anteprima con i tag | testo da copiare | PDF censurato ---- */
async function setView(v){
  if(v==='pdf'&&!DATA&&!$('pdf').files.length&&!$('src').value.trim()){
    toast(tt('t_need_anon'),false);return;}
  VIEW=v;
  $('vPrev').classList.toggle('on',v==='prev');
  $('vText').classList.toggle('on',v==='text');
  $('vPdf').classList.toggle('on',v==='pdf');
  $('viewPrev').style.display=v==='prev'?'':'none';
  $('anon').style.display=v==='text'?'':'none';
  $('pdfOutView').style.display=v==='pdf'?'':'none';
  if(v!=='pdf'){
    matchScroll(v==='prev'?$('viewPrev'):$('anon'),$('src'));  // allinea la vista appena mostrata
    return;
  }
  if(OUT_DOC){renderPages($('pdfOutView'),OUT_DOC);return;}
  busy($('pdfOutView'),tt('t_pdf_render'));
  const d=await buildOutPdf();
  if(VIEW!=='pdf')return;                    // l'utente ha cambiato vista nel frattempo
  if(!d){setView('prev');return;}
  renderPages($('pdfOutView'),d);
  if(d.residual+d.skipped>0)toast(T[L].t_pdf_warn(d.residual,d.skipped),false,9000);
}

/* Genera UNA volta il PDF anonimizzato e lo lascia sul server: la stessa copia
   serve sia l'anteprima a destra sia il download (una sola inferenza).
   Come /pdf, il dizionario non viene inviato: il server lo ricostruisce e lo
   butta, quindi funziona anche con lo switch "dizionario" su DISATTIVO. */
let PDF_JOB=null;
function buildOutPdf(){
  if(OUT_DOC)return Promise.resolve(OUT_DOC);
  if(PDF_JOB)return PDF_JOB;                 // click su tab + download insieme -> una richiesta sola
  const file=$('pdf').files[0];const text=$('src').value.trim();
  if(!DATA&&!file&&!text){toast(tt('t_need_anon'),false);return Promise.resolve(null);}
  const excl=TAGS_LOADED?[...EXCL]:null;
  PDF_JOB=(async()=>{
    try{
      let resp;
      if(file){const fd=new FormData();fd.append('pdf',file);
        if(excl)fd.append('exclude_tags',excl.join(','));
        if(BOXES.length)fd.append('manual_boxes',JSON.stringify(BOXES));
          resp=await fetch('/pdf/preview',{method:'POST',body:fd});}
      else{const body={text};if(excl)body.exclude_tags=excl;
          resp=await fetch('/pdf/preview',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify(body)});}
      const d=await resp.json();
      if(!resp.ok){toast(d.error||tt('t_pdf_err'),false);return null;}
      OUT_DOC=d;return d;
    }catch(e){toast(tt('t_pdf_err')+': '+e.message,false);return null;}
    finally{PDF_JOB=null;}
  })();
  return PDF_JOB;
}

/* ---- copy / download ---- */
$('copy').onclick=()=>{if(!DATA){toast(tt('t_need_anon'),false);return;}
  navigator.clipboard.writeText(DATA.anonymized_text).then(()=>toast(tt('t_copied')));};
$('dl').onclick=()=>{if(!DATA||!Object.keys(MAP).length){toast(tt('t_nothing_dl'),false);return;}
  const blob=new Blob([JSON.stringify(MAP,null,2)],{type:'application/json'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);
  a.download='dizionario_anonimizzazione.json';a.click();URL.revokeObjectURL(a.href);
  toast(tt('t_dl_ok'));};

/* ---- PDF anonimizzato (issue #7): redazione vera del PDF caricato, oppure PDF
       ricostruito dal testo anonimizzato quando l'input non era un PDF.
       Se lo si e' gia' guardato nella vista "PDF censurato" il file esiste gia'
       sul server: si scarica quello, senza una seconda anonimizzazione. ---- */
$('dlpdf').onclick=async()=>{
  const btn=$('dlpdf');btn.disabled=true;const old=btn.innerHTML;
  btn.innerHTML='<span class="spin"></span> '+tt('t_pdf_making');
  try{
    const d=await buildOutPdf();
    if(!d)return;
    const a=document.createElement('a');
    a.href='/doc/'+d.doc_id+'/file.pdf';
    a.download=d.filename||'documento_anonimizzato.pdf';a.click();
    // residui = valori ancora leggibili nell'output; saltati = valori troppo corti
    // per essere cercati senza devastare il documento. Entrambi restano IN CHIARO.
    if(d.residual+d.skipped>0)toast(T[L].t_pdf_warn(d.residual,d.skipped),false,9000);
    else toast(tt('t_pdf_ok'));
  }finally{btn.disabled=false;btn.innerHTML=old;}
};

/* ---- reverse ---- */
function reverse(){
  const txt=$('rin').value;
  if(!txt.trim()){toast(tt('t_paste_restore'),false);return;}
  if(!Object.keys(MAP).length){toast(tt('t_no_dict'),false);return;}
  // placeholder piu' lunghi prima (evita FULLNAME_1 dentro FULLNAME_10)
  const keys=Object.keys(MAP).sort((a,b)=>b.length-a.length);
  let out=txt;
  for(const ph of keys){
    const inner=ph.slice(1,-1);                 // FULLNAME_1
    // tollerante: parentesi opzionali / spazi, eventuale grassetto markdown
    const rx=new RegExp('\\**\\[?\\s*'+inner.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'\\s*\\]?\\**','g');
    out=out.replace(rx,MAP[ph].replace(/\$/g,'$$$$'));
  }
  const o=$('rout');o.textContent=out;o._raw=out;
  toast(tt('t_restored'));
}
$('rev').onclick=reverse;
$('rcopy').onclick=()=>{const o=$('rout');if(!o._raw){toast(tt('t_nothing_copy'),false);return;}
  navigator.clipboard.writeText(o._raw).then(()=>toast(tt('t_restored_copied')));};
$('rclear').onclick=()=>{$('rin').value='';$('rout').innerHTML=routEmpty();$('rout')._raw='';};

/* ---- carica dizionario da file (per sessioni diverse) ---- */
$('dictFile').onchange=e=>{const f=e.target.files[0];if(!f)return;
  const r=new FileReader();r.onload=()=>{try{MAP=JSON.parse(r.result);
    $('dictInfo').textContent=T[L].dict_loaded_n(Object.keys(MAP).length);
    toast(tt('t_dict_loaded'));}catch{toast(tt('t_json_invalid'),false);}};
  r.readAsText(f);};

/* ---- input helpers ---- */
$('go').onclick=run;
$('clear').onclick=()=>{$('src').value='';$('pdf').value='';$('fileName').textContent='';
  DATA=null;$('prev').style.display='none';$('emptyPrev').style.display='';
  $('anon').value='';$('meta').innerHTML='';$('legend').innerHTML='';
  $('dictCard').style.display='none';$('ulock').textContent='';
  // la card era solo nascosta: senza queste tre righe il dizionario resta in MAP e su
  // disco, e al riavvio ricompare zitto al posto di quello del documento nuovo
  MAP={};localStorage.removeItem('pii_map');$('dictInfo').textContent='';
  SRC_DOC=null;OUT_DOC=null;$('pdfSrcView').innerHTML='';$('pdfOutView').innerHTML='';
  resetBoxes();
  $('srcTabs').style.display='none';$('inHint').innerHTML=tt('in_hint');
  $('inHint').style.display='';setSrcView('text');setView('prev');
  document.querySelector('.app').classList.remove('has-result');};

/* drag&drop su TUTTA la finestra (solo in modalita' Anonimizza): niente
   dropzone dedicata — l'overlay compare quando entra un file e sparisce
   al rilascio. Il contatore DRAGN assorbe i dragenter/leave annidati. */
$('pdf').onchange=e=>{const f=e.target.files[0];if(f)onFile(f);};
const OK_EXT=/\.(pdf|md|markdown|txt|text)$/i;
let DRAGN=0;
function dragHasFiles(e){return e.dataTransfer&&Array.from(e.dataTransfer.types||[]).includes('Files');}
window.addEventListener('dragenter',e=>{
  if(!dragHasFiles(e))return;
  e.preventDefault();
  if(MODE!==1)return;
  DRAGN++;$('dropOverlay').classList.add('on');
});
window.addEventListener('dragover',e=>{if(dragHasFiles(e))e.preventDefault();});
window.addEventListener('dragleave',e=>{
  if(!dragHasFiles(e))return;
  if(--DRAGN<=0){DRAGN=0;$('dropOverlay').classList.remove('on');}
});
window.addEventListener('drop',e=>{
  if(!dragHasFiles(e))return;
  e.preventDefault();DRAGN=0;$('dropOverlay').classList.remove('on');
  if(MODE!==1)return;
  const f=e.dataTransfer.files[0];
  if(f&&(f.type==='application/pdf'||OK_EXT.test(f.name))){
    const dt=new DataTransfer();dt.items.add(f);$('pdf').files=dt.files;
    onFile(f);
  }else toast(tt('t_drag_pdf'),false);
});

/* scroll sincronizzato: editor (sx) <-> anteprima e testo (dx) */
linkScroll($('src'),$('viewPrev'));linkScroll($('viewPrev'),$('src'));
linkScroll($('src'),$('anon'));linkScroll($('anon'),$('src'));
/* e le due viste PDF fra loro: stesso documento, prima e dopo la censura */
linkScroll($('pdfSrcView'),$('pdfOutView'));linkScroll($('pdfOutView'),$('pdfSrcView'));
/* scorrendo a zoom alto entrano pagine nuove: vanno chieste anch'esse nitide */
for(const el of ['pdfSrcView','pdfOutView']) $(el).addEventListener('scroll',scheduleDpi);

/* lingua: selettore + applicazione iniziale (default IT, preferenza salvata) */
$('lang').onchange=e=>applyLang(e.target.value);
applyLang(localStorage.getItem('pii_lang')||'it');

/* avviso: popup a click (non hover), si chiude cliccando fuori o con Esc */
$('infoBtn').addEventListener('click',e=>{e.stopPropagation();$('infoBtn').classList.toggle('open');});
$('infoBtn').addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();$('infoBtn').classList.toggle('open');}});
document.addEventListener('click',e=>{if(!$('infoBtn').contains(e.target))$('infoBtn').classList.remove('open');});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('infoBtn').classList.remove('open');closeConfig();closeTags();}});

/* ---- config modal ---- */
/* Impostazioni a tre schede: Server · Come funziona · Crediti.
   I due pannelli di testo sono riempiti da applyLang (chiavi how_body/cred_body),
   quindi cambiano lingua da soli. */
function setSettingsTab(w){
  for(const [id,pane] of [['stServer','setServer'],['stHow','setHow'],
                          ['stSec','setSec'],['stCred','setCred']]){
    const on=id==='st'+w.charAt(0).toUpperCase()+w.slice(1);
    $(id).setAttribute('aria-selected',String(on));
    $(pane).style.display=on?'':'none';
  }
}
async function openConfig(){
  const r=await fetch('/config');const d=await r.json();
  $('cfgHost').value=d.host||'127.0.0.1';
  $('cfgPort').value=d.port||5005;
  $('cfgStatus').className='cfg-status';$('cfgStatus').textContent='';
  setSettingsTab('server');
  $('cfgOverlay').classList.add('open');
  // il modello VERO che sta girando, non un numero scritto a mano nei crediti
  try{
    const h=await (await fetch('/health')).json();
    if($('credModel'))$('credModel').textContent=(h.model||'')+' · v'+(h.model_version||'?')
      +' · '+(h.device||'cpu').toUpperCase();
  }catch(e){}
}
function closeConfig(){$('cfgOverlay').classList.remove('open');}
$('cfgOverlay').addEventListener('click',e=>{if(e.target===$('cfgOverlay'))closeConfig();});
async function checkPort(){
  const h=$('cfgHost').value.trim(),p=parseInt($('cfgPort').value);
  if(!p||p<1024||p>65535){$('cfgStatus').className='cfg-status fail';$('cfgStatus').textContent=tt('cfg_in_use');return;}
  const r=await fetch(`/port-check?host=${encodeURIComponent(h)}&port=${p}`);
  const d=await r.json();
  $('cfgStatus').className=d.available?'cfg-status ok':'cfg-status fail';
  $('cfgStatus').textContent=d.available?tt('cfg_available'):tt('cfg_in_use');
}
async function saveConfig(){
  const h=$('cfgHost').value.trim(),p=parseInt($('cfgPort').value);
  if(!p||p<1024||p>65535){toast(tt('cfg_in_use'),false);return;}
  await fetch('/config',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({host:h,port:p})});
  toast(tt('cfg_saved'));
  closeConfig();
}

/* ---- switch "Dizionario reversibile" ---- */
function renderMapping(){
  const on=MAPPING;
  $('mapToggle').classList.toggle('off',!on);
  $('mapToggle').setAttribute('aria-checked',String(on));
  $('mapSw').classList.toggle('off',!on);
  $('mapState').textContent=on?tt('map_on'):tt('map_off');
  $('mapSub').innerHTML=on?tt('map_sub_on'):tt('map_sub_off');
  $('rOff').style.display=on?'none':'';
  $('dl').style.display=on?'':'none';      // niente dizionario -> niente download
}
async function toggleMapping(){
  MAPPING=!MAPPING;
  renderMapping();
  toast(MAPPING?tt('t_map_on'):tt('t_map_off'),MAPPING);
  try{                                 // persiste: vale anche per l'API /analyze
    await fetch('/settings',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({mapping_enabled:MAPPING})});
  }catch(e){}
}

/* ---- tags modal: legenda + selezione dei tag da anonimizzare ---- */
let TAGS_META={};
async function loadTags(){
  try{
    const d=await (await fetch('/settings')).json();
    TAGS=d.tags||[];EXCL=new Set(d.excluded_tags||[]);TAGS_META=d;TAGS_LOADED=true;
    MAPPING=d.mapping_enabled!==false;renderMapping();
  }catch(e){/* server vecchio o offline: si continua con il comportamento di default */}
}
function renderTags(){
  const list=$('tgList');list.innerHTML='';
  for(const t of TAGS){
    const c=colors(t.tag),on=!EXCL.has(t.tag);
    const row=document.createElement('label');
    row.className='tg-row'+(on?'':' off');
    row.innerHTML=`<input type="checkbox" ${on?'checked':''}>`+
      `<span class="sw" style="background:${c.bd}"></span>`+
      `<span class="txt"><span class="nm" style="color:${c.tx}">${t.tag}</span>`+
      `<div class="ds">${escapeHtml(L==='en'?t.en:t.it)}</div>`+
      `<div class="ex">${escapeHtml(t.example||'')}</div></span>`;
    row.querySelector('input').onchange=e=>{
      e.target.checked?EXCL.delete(t.tag):EXCL.add(t.tag);
      row.classList.toggle('off',!e.target.checked);tgCount();};
    list.appendChild(row);
  }
  tgCount();
}
function tgCount(){$('tgCount').textContent=T[L].tg_count(TAGS.length-EXCL.size,TAGS.length);}

/* ---- Termini personali (lista {value, tag} salvata in prefs.json) ---- */
let TERMS=[];
function renderTerms(){
  const list=$('ctList');list.innerHTML='';
  for(const [i,t] of TERMS.entries()){
    const c=colors(t.tag);
    const row=document.createElement('div');row.className='ct-row';
    row.innerHTML=`<span class="nm" style="color:${c.tx}">${escapeHtml(t.tag)}</span>`+
      `<span class="val">${escapeHtml(t.value)}</span>`+
      `<button class="rm" title="${tt('ct_del')}">✕</button>`;
    row.querySelector('.rm').onclick=()=>{TERMS.splice(i,1);renderTerms();};
    list.appendChild(row);
  }
  const dl=$('ctTagList');dl.innerHTML='';
  for(const t of TAGS){const o=document.createElement('option');o.value=t.tag;dl.appendChild(o);}
}
function addTerm(){
  const val=$('ctVal').value.trim();
  const tag=$('ctTag').value.trim().toUpperCase().replace(/\s+/g,'_');
  const alnum=(val.match(/[\p{L}\p{N}]/gu)||[]).length;
  if(alnum<3){toast(tt('ct_short'),false);return;}
  if(!/^[A-Z0-9_]{2,20}$/.test(tag)){toast(tt('ct_badtag'),false);return;}
  if(TERMS.some(t=>t.value.toLowerCase()===val.toLowerCase()&&t.tag===tag)){return;}
  TERMS.push({value:val,tag});
  $('ctVal').value='';$('ctTag').value='';
  renderTerms();
}
$('ctVal').addEventListener('keydown',e=>{if(e.key==='Enter')addTerm();});
$('ctTag').addEventListener('keydown',e=>{if(e.key==='Enter')addTerm();});
function setAllTags(on){
  EXCL=on?new Set():new Set(TAGS.map(t=>t.tag));
  renderTags();
}
async function openTags(){
  if(!TAGS.length)await loadTags();
  if(!TAGS.length){toast(tt('t_error'),false);return;}
  $('tgStatus').className='cfg-status';$('tgStatus').textContent='';
  $('tgNote').innerHTML=(TAGS_META.env_override?'<b>'+tt('tg_env')+'</b><br>':'')+
    T[L].tg_note(TAGS_META.config_path||'');
  TERMS=(TAGS_META.custom_terms||[]).map(t=>({value:t.value,tag:t.tag}));
  renderTags();
  renderTerms();
  $('tagsOverlay').classList.add('open');
}
function closeTags(){$('tagsOverlay').classList.remove('open');loadTags();}  // ricarica: annulla = scarta
$('tagsOverlay').addEventListener('click',e=>{if(e.target===$('tagsOverlay'))closeTags();});
async function saveTags(){
  try{
    const r=await fetch('/settings',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({excluded_tags:[...EXCL],custom_terms:TERMS})});
    const d=await r.json();
    if(!r.ok)throw new Error(d.error||'');
    EXCL=new Set(d.excluded_tags||[]);
    TAGS_META.custom_terms=d.custom_terms||[];
    toast(tt('tg_saved'));
    $('tagsOverlay').classList.remove('open');
  }catch(e){$('tgStatus').className='cfg-status fail';$('tgStatus').textContent=tt('tg_err');}
}
loadTags();

/* recupera dizionario da sessione precedente (dopo applyLang -> testo nella lingua giusta) */
try{const m=localStorage.getItem('pii_map');if(m){MAP=JSON.parse(m);
  if(Object.keys(MAP).length)$('dictInfo').textContent=T[L].dict_session(Object.keys(MAP).length);}}catch{}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    import argparse as _ap
    _p = _ap.ArgumentParser(description="AnonimAI — server locale di anonimizzazione.")
    _p.add_argument("--host", default=None, help="indirizzo su cui ascoltare (default da config/env/127.0.0.1)")
    _p.add_argument("--port", type=int, default=None, help="porta su cui ascoltare (default da config/env/5005)")
    _p.add_argument("--exclude-tags", default=None, metavar="TAG,TAG",
                    help="tag PII da NON anonimizzare, es. AGE,GENDER (default da env/prefs.json)")
    _p.add_argument("--no-mapping", action="store_true",
                    help="anonimizzazione definitiva: non costruire il dizionario di ripristino")
    _args = _p.parse_args()

    if _args.exclude_tags is not None:
        EXCLUDED_TAGS = server_config.parse_tag_list(_args.exclude_tags)
        _unknown = [t for t in EXCLUDED_TAGS if t not in TAG_NAMES]
        if _unknown:
            print(f"ERRORE: tag sconosciuti in --exclude-tags: {', '.join(_unknown)}")
            print(f"Tag validi: {', '.join(TAG_NAMES)}")
            sys.exit(2)
    if _args.no_mapping:
        MAPPING_ENABLED = False
    if EXCLUDED_TAGS:
        print(f"Tag esclusi dall'anonimizzazione: {', '.join(EXCLUDED_TAGS)}")
    print("Dizionario reversibile: " +
          ("ATTIVO (si puo' ripristinare)" if MAPPING_ENABLED
           else "DISATTIVO (anonimizzazione definitiva)"))

    _host, _port = server_config.resolve(cli_host=_args.host, cli_port=_args.port)

    if not server_config.port_available(_host, _port):
        print(f"ERRORE: porta {_port} occupata su {_host}")
        sys.exit(server_config.EXIT_PORT_CONFLICT)

    print(f"Server su http://{_host}:{_port}")
    try:
        app.run(host=_host, port=_port, threaded=True)
    except OSError as e:
        print(f"ERRORE bind: {e}")
        sys.exit(server_config.EXIT_PORT_CONFLICT)
