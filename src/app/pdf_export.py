# -*- coding: utf-8 -*-
"""
Generazione del PDF anonimizzato (issue #7, punto 1).

Due modalita', entrambe 100% in locale e senza dipendenze dal modello: il modulo
lavora solo su bytes + dizionario {placeholder -> valore}, quindi e' testabile in
isolamento (nessun import di torch/transformers).

  redact_pdf(pdf_bytes, mapping)
      Redazione VERA del PDF originale: per ogni valore del dizionario cerca le
      occorrenze nelle pagine, RIMUOVE il testo dal content stream
      (page.apply_redactions(), non un rettangolo disegnato sopra) e scrive il
      placeholder al suo posto. Layout conservato.

      Il matching e' CHAR-PRECISO con CONFINI DI PAROLA: la pagina viene
      indicizzata carattere per carattere (get_text("rawdict"), ogni glifo con il
      suo bbox) e i valori sono cercati con regex ancorate (?<!\\w)...(?!\\w).
      Cosi' "DE" NON viene redatto dentro "CORDELLA" e una cifra non cancella i
      numeri di un referto: si redige il token/la sequenza esatta, ovunque ma
      intera. Il pattern tollera la SILLABAZIONE a fine riga ("Fran-\\ncesco") e
      gli spazi flessibili tra i token (anche a cavallo di riga).

  text_to_pdf(text)
      PDF "ricostruito" solo testo, impaginato da zero a partire dal testo gia'
      anonimizzato (input incollato oppure file .md/.txt).

Cosa viene ripulito oltre al testo di pagina (tutti posti dove si nasconde PII e
che apply_redactions() da solo NON tocca):
  - metadati classici + XMP;
  - contenuto delle ANNOTAZIONI (commenti, FreeText, note);
  - valore dei CAMPI MODULO (widget AcroForm);
  - titoli dei SEGNALIBRI (outline/TOC);
  - ALLEGATI incorporati (embedded files), rimossi in blocco.

Rete di sicurezza finale: `report["residual"]` elenca i placeholder il cui valore
e' ANCORA leggibile nell'output (testo di pagina + annotazioni + widget + TOC).
Deve essere vuota; l'UI avvisa se non lo e'.

OCR (issue #98 / #7 punto 2): il testo dentro le immagini raster — scansioni intere
o carta intestata/loghi su pagine normali — viene reso visibile con l'OCR integrato
di PyMuPDF (Tesseract compilato dentro la wheel: servono SOLO i file tessdata, non
il binario). Tre modalita' per pagina, decise da `page_textpage()`:
  - solo testo nativo             -> nessun OCR (zero costo nuovo);
  - immagini, testo scarso        -> OCR dell'intera pagina (scansione);
  - immagini + testo nativo       -> OCR delle sole immagini, fuso col nativo.
Sulle pagine-scansione redatte si scrive anche un layer di testo INVISIBILE
(render_mode=3) con il testo OCR non-PII: l'output diventa ricercabile.
Senza tessdata (`ocr_available()` False) tutto degrada al comportamento di prima.

Riquadri manuali (issue #98 punto 2, firme e timbri): `manual_boxes` in
`redact_pdf` — rettangoli {page, x0..y1} in FRAZIONI 0-1 della pagina come
mostrata; i pixel sotto vengono cancellati (`PDF_REDACT_IMAGE_PIXELS`), non
coperti. Con i riquadri il dizionario puo' anche essere vuoto.

Limiti noti (= punti 3-4 della issue #7):
  - firme e timbri NON vengono riconosciuti da soli: si coprono con i riquadri
    manuali (non sono testo, l'OCR non li vede);
  - valori troppo corti/ambigui (< 2 caratteri alfanumerici, o 2 sole cifre) NON
    vengono redatti: cercarli ovunque devasterebbe il documento. Finiscono in
    `report["skipped"]` e l'UI DEVE avvisare, perche' restano in chiaro;
  - se in tutto il PDF non si trova NESSUNA occorrenza (e non ci sono riquadri),
    il chiamante deve rifiutare: meglio un errore che un PDF "anonimizzato" che
    non lo e'.
"""

import json
import os
import re
import unicodedata

import fitz  # PyMuPDF


class PdfError(ValueError):
    """Errore d'uso (PDF non valido, protetto, dizionario vuoto...)."""


# --------------------------------------------------------------------------- #
# OCR — PyMuPDF ha Tesseract compilato dentro la wheel: serve SOLO la cartella
# dei language data (tessdata), niente binario di sistema. Se manca, tutte le
# funzioni degradano al comportamento senza OCR: mai un crash per una feature
# opzionale.
# --------------------------------------------------------------------------- #
OCR_LANGS = os.environ.get("PII_OCR_LANGS", "ita+eng")
OCR_DPI = 300               # sotto i 300 Tesseract perde i corpi piccoli dei footer
_MIN_NATIVE_CHARS = 30      # sotto: la pagina e' una scansione, OCR dell'intera pagina
_MIN_IMG_SIDE = 20          # pt: immagini piu' piccole (icone) non giustificano l'OCR

_TESSDATA = "?"             # sentinella: None = cercato e non trovato


def _has_langs(d):
    """La cartella ha TUTTE le lingue configurate? Una tessdata senza ita
    farebbe fallire ogni OCR a runtime: meglio dichiararsi non disponibili
    subito (e con PII_OCR_LANGS=eng una tessdata solo-inglese torna valida)."""
    return all(os.path.isfile(os.path.join(d, lang + ".traineddata"))
               for lang in OCR_LANGS.split("+") if lang)


def tessdata_dir():
    """Cartella dei .traineddata (con le lingue configurate presenti), o None.
    Precedenza: PII_TESSDATA > TESSDATA_PREFIX > ricerca di PyMuPDF
    (fitz.get_tessdata).

    ⚠️ La libreria Tesseract dentro MuPDF legge ANCHE l'env TESSDATA_PREFIX,
    e puo' vincere sul parametro `tessdata=` passato a get_textpage_ocr: un
    env sbagliato rompeva l'OCR anche col percorso giusto in mano (misurato:
    'Error opening data file /nonexistent/ita.traineddata' con tessdata=
    valido). Qui l'env si RIALLINEA alla cartella scelta, una volta sola."""
    global _TESSDATA
    if _TESSDATA != "?":
        return _TESSDATA
    found = None
    for cand in (os.environ.get("PII_TESSDATA"), os.environ.get("TESSDATA_PREFIX")):
        if cand and os.path.isdir(cand) and _has_langs(cand):
            found = cand
            break
    if found is None:
        try:
            auto = fitz.get_tessdata() or None
        except Exception:
            auto = None
        if auto and os.path.isdir(auto) and _has_langs(auto):
            found = auto
    if found is not None:
        os.environ["TESSDATA_PREFIX"] = found
    _TESSDATA = found
    return _TESSDATA


def ocr_available():
    return tessdata_dir() is not None


def page_textpage(page):
    """(textpage, mode) per leggere la pagina, immagini comprese.

    mode: 'native'    -> textpage None, si usano i metodi normali (nessuna
                         immagine rilevante, o tessdata assente, o OCR fallito);
          'ocr-full'  -> scansione: OCR dell'intera pagina rasterizzata;
          'ocr-mixed' -> pagina normale con immagini (carta intestata, loghi):
                         OCR delle sole immagini, fuso col testo nativo (full=False).

    Il criterio e' la NATURA (c'e' un'immagine abbastanza grande da poter
    contenere testo), non la posizione: header e footer non sono casi speciali.
    """
    tess = tessdata_dir()
    if tess is None:
        return None, "native"
    try:
        # ponytail: soglia fissa sui pt del bbox; se un giorno servisse finezza,
        # il posto per pesare le immagini e' qui.
        infos = page.get_image_info()
    except Exception:
        infos = []
    big = any(fitz.Rect(i["bbox"]).width >= _MIN_IMG_SIDE
              and fitz.Rect(i["bbox"]).height >= _MIN_IMG_SIDE for i in infos)
    if not big:
        return None, "native"
    native = len((page.get_text() or "").strip())
    full = native < _MIN_NATIVE_CHARS
    try:
        tp = page.get_textpage_ocr(language=OCR_LANGS, dpi=OCR_DPI,
                                   full=full, tessdata=tess)
    except Exception:
        return None, "native"
    return tp, ("ocr-full" if full else "ocr-mixed")


def extract_page_text(page):
    """Testo della pagina, immagini comprese quando l'OCR e' disponibile.
    E' quello che l'app manda al modello: la stessa lente della redazione."""
    tp, _ = page_textpage(page)
    return page.get_text(textpage=tp) if tp is not None else page.get_text()


# DPI ammessi per l'anteprima a video: LISTA CHIUSA, non un numero libero.
# Il client chiede la risoluzione con cui vuole le pagine (serve allo zoom: oltre
# il dettaglio nativo l'immagine sgrana), ma un dpi arbitrario sarebbe la leva per
# far renderizzare un A4 a 2000 dpi — gigabyte di pixel per pagina, dentro un
# processo che tiene tutto in RAM.
PREVIEW_DPI_ALLOWED = (110, 220)


def parse_preview_dpi(raw, default=PREVIEW_DPI_ALLOWED[0]):
    """DPI richiesto dal client -> uno dei valori ammessi, altrimenti il default.
    Non solleva: una query string sbagliata non e' un errore d'uso, e' rumore."""
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return default
    return v if v in PREVIEW_DPI_ALLOWED else default


def parse_manual_boxes(raw):
    """Riquadri manuali dal client: lista di {page, x0, y0, x1, y1} in FRAZIONI
    0-1 della pagina come mostrata (indipendenti dal DPI dell'anteprima).
    Valida e clampa: e' input di frontiera. Ritorna la lista pulita."""
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raise PdfError("manual_boxes non e' JSON valido.")
    if not isinstance(raw, list):
        raise PdfError("manual_boxes deve essere una lista di riquadri.")
    if len(raw) > 500:
        raise PdfError("Troppi riquadri manuali (max 500).")
    out = []
    for b in raw:
        try:
            page = int(b["page"])
            x0, y0, x1, y1 = (min(max(float(b[k]), 0.0), 1.0)
                              for k in ("x0", "y0", "x1", "y1"))
        except (TypeError, KeyError, ValueError):
            raise PdfError("Riquadro non valido in manual_boxes.")
        # degeneri (click senza drag, o tutto fuori pagina): si scartano zitti
        if page < 0 or x1 - x0 < 0.003 or y1 - y0 < 0.003:
            continue
        out.append({"page": page, "x0": x0, "y0": y0, "x1": x1, "y1": y1})
    return out


# --------------------------------------------------------------------------- #
# Utility comuni
# --------------------------------------------------------------------------- #
# caratteri tipografici frequenti nei PDF estratti -> equivalenti Latin-1
# (il font base "helv" copre Latin-1: cosi' la sostituzione e' deterministica)
_TRANSLATE = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...", "€": "EUR",
    " ": " ", "•": "-", "ﬁ": "fi", "ﬂ": "fl",
})


def _norm(s):
    """Spazi compressi + casefold: stessa normalizzazione usata in app.py."""
    return re.sub(r"\s+", " ", (s or "").strip()).casefold()


def _fit_fontsize(text, rect, max_fs=10.0, min_fs=4.0):
    """Corpo del testo per far stare `text` dentro `rect` (0 = non ci sta:
    meglio nessuna etichetta che un'etichetta illeggibile o troncata)."""
    try:
        w10 = fitz.get_text_length(text, fontname="helv", fontsize=10.0)
    except Exception:
        return 0
    if w10 <= 0:
        return 0
    fs = min(max_fs, rect.height * 0.82, 10.0 * max(rect.width - 2.0, 0.0) / w10)
    return round(fs, 1) if fs >= min_fs else 0


def _covered(rect, taken, thr=0.85):
    """True se `rect` e' gia' (quasi) tutto dentro una redazione precedente:
    evita doppioni quando un valore e' contenuto in un altro (es. "Rossi"
    dentro "Mario Rossi", redatto prima perche' piu' lungo)."""
    area = rect.get_area()
    if area <= 0:
        return True
    for t in taken:
        inter = fitz.Rect(rect)
        inter.intersect(t)
        if not inter.is_empty and inter.get_area() / area >= thr:
            return True
    return False


# --------------------------------------------------------------------------- #
# Indice char-preciso della pagina + ricerca con confini di parola
# --------------------------------------------------------------------------- #
def _page_char_index(page, textpage=None):
    """(testo, [bbox per carattere]) dalla pagina: ogni carattere del layer
    testuale con il suo rettangolo (None per i newline di fine riga).
    Con un textpage OCR l'indice copre anche il testo dentro le immagini:
    tutta la catena a valle (pattern, rect, redazione) resta identica."""
    raw = page.get_text("rawdict", textpage=textpage)
    chars, boxes = [], []
    for block in raw.get("blocks", []):
        if block.get("type") != 0:          # solo blocchi di testo
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                for ch in span.get("chars", []):
                    c = ch.get("c") or ""
                    for cc in c:            # ligature -> piu' caratteri, stesso bbox
                        chars.append(cc)
                        boxes.append(fitz.Rect(ch["bbox"]))
            chars.append("\n")
            boxes.append(None)
    return "".join(chars), boxes


# Sillabazione a fine riga: "Fran-\ncesco", "Fran­\ncesco" o anche solo un
# a-capo dentro la parola. Ammesso TRA due caratteri qualsiasi del valore, ma solo
# se c'e' davvero un newline: senza, il gruppo non consuma nulla e il matching
# resta char-per-char (niente tolleranza allo spacing, che aprirebbe a
# sovra-redazioni tipo "MI" dentro "M I L A N O").
_HYPHEN_BREAK = r"(?:[­‐-]?[ \t]*\n[ \t]*)?"


# Sotto questa soglia di caratteri alfanumerici un frammento NON puo' rinunciare
# ai confini di parola: ".it" senza ancore matcherebbe "it" dentro ogni parola.
_UNANCHORED_MIN_ALNUM = 4


def _value_pattern(value):
    """Regex del valore: caratteri esatti con CONFINI DI PAROLA agli estremi,
    sillabazione a fine riga tollerata, whitespace flessibile tra i token.
    Niente match di sottostringhe dentro altre parole.

    Eccezione: quando il valore ha punteggiatura ai bordi il modello ha tagliato
    a meta' una parola spezzata a fine riga (tipico: "Fran-\\ncesco Cordella" ->
    il modello etichetta "-\\ncesco Cordella"). Li' il confine di parola su quel
    lato e' proprio cio' che impedisce di trovare il valore, che resterebbe in
    chiaro: si toglie la punteggiatura e con essa l'ancora, ma solo se quel che
    resta e' abbastanza lungo da non trasformarsi in una sottostringa qualunque."""
    v = _norm(value)
    core = re.sub(r"^[^\w]+", "", v)
    core = re.sub(r"[^\w]+$", "", core)
    toks = [t for t in core.split(" ") if t]
    if not toks:
        return None
    if len(re.sub(r"[\W_]+", "", core)) >= _UNANCHORED_MIN_ALNUM:
        left = "" if re.match(r"^[^\w]", v) else r"(?<!\w)"
        right = "" if re.search(r"[^\w]$", v) else r"(?!\w)"
    else:                                  # troppo corto: ancore obbligatorie
        toks = [t for t in v.split(" ") if t]
        left, right = r"(?<!\w)", r"(?!\w)"
    body = r"\s*".join(_HYPHEN_BREAK.join(re.escape(c) for c in tok) for tok in toks)
    return re.compile(left + body + right, re.IGNORECASE)


def _match_rects(boxes, m):
    """Bbox dei caratteri del match, uniti per riga (overlap verticale)."""
    rects, cur = [], None
    for i in range(m.start(), m.end()):
        b = boxes[i]
        if b is None or b.is_empty:
            continue
        if cur is None:
            cur = fitz.Rect(b)
        elif b.y0 < cur.y1 and b.y1 > cur.y0:      # stessa riga
            cur |= b
        else:                                       # riga nuova
            rects.append(cur)
            cur = fitz.Rect(b)
    if cur is not None and not cur.is_empty:
        rects.append(cur)
    return rects


def _too_noisy(value):
    """Valori non localizzabili in modo sicuro in un PDF: frammenti con meno di 2
    caratteri alfanumerici, o di 2 sole cifre (es. "1", "C", "05", prodotti a
    volte dal modello su testi tabellari). Cercarli ovunque cancellerebbe pezzi di
    documento non-PII: si saltano, MA il chiamante deve avvisare l'utente (restano
    in chiaro)."""
    alnum = re.sub(r"[\W_]+", "", _norm(value))
    return len(alnum) < 2 or (len(alnum) == 2 and alnum.isdigit())


# --------------------------------------------------------------------------- #
# Pulizia di tutto cio' che apply_redactions() non tocca
# --------------------------------------------------------------------------- #
def _scrub_metadata(doc):
    """Azzera i metadati classici e l'XMP: possono contenere PII (autore...)."""
    try:
        # set_metadata aggiorna SOLO le chiavi passate: vanno azzerate tutte
        # esplicitamente, altrimenti autore/titolo originali restano nel file
        doc.set_metadata({
            "title": "", "author": "", "subject": "", "keywords": "",
            "creationDate": "", "modDate": "", "trapped": "",
            "creator": "AnonimAI", "producer": "AnonimAI",
        })
    except Exception:
        pass
    f = getattr(doc, "del_xml_metadata", None) or getattr(doc, "delXmlMetadata", None)
    if f:
        try:
            f()
        except Exception:
            pass


def _sub_all(patterns, s):
    """Applica tutte le (regex, placeholder) alla stringa. Ritorna (nuova, n)."""
    n = 0
    for pat, ph in patterns:
        s, k = pat.subn(ph, s)
        n += k
    return s, n


def _scrub_annots(page, patterns):
    """Contenuto e titolo delle annotazioni (commenti, FreeText, note adesive):
    testo vero e proprio, invisibile a get_text() e non toccato dalle redazioni."""
    done = 0
    try:
        annots = list(page.annots())
    except Exception:
        return 0
    for a in annots:
        try:
            if a.type[0] == fitz.PDF_ANNOT_REDACT:      # le nostre, gia' gestite
                continue
            info = a.info
            new = dict(info)
            hit = 0
            for k in ("content", "subject", "title"):
                if info.get(k):
                    new[k], k_hit = _sub_all(patterns, info[k])
                    hit += k_hit
            if hit:
                a.set_info(new)
                a.update()
                done += hit
        except Exception:
            continue
    return done


def _scrub_widgets(page, patterns):
    """Valore dei campi modulo AcroForm: sopravvive a qualsiasi redazione del
    content stream ed e' leggibile aprendo il PDF."""
    done = 0
    try:
        widgets = list(page.widgets())
    except Exception:
        return 0
    for w in widgets:
        try:
            val = w.field_value
            if not isinstance(val, str) or not val:
                continue
            new, hit = _sub_all(patterns, val)
            if hit:
                w.field_value = new
                w.update()
                done += hit
        except Exception:
            continue
    return done


def _scrub_toc(doc, patterns):
    """Titoli dei segnalibri: spesso ricalcano intestazioni con nomi e numeri."""
    try:
        toc = doc.get_toc(simple=True)
    except Exception:
        return 0
    if not toc:
        return 0
    done, new_toc = 0, []
    for entry in toc:
        lvl, title, pg = entry[0], entry[1], entry[2]
        title, hit = _sub_all(patterns, title or "")
        done += hit
        new_toc.append([lvl, title, pg])
    if done:
        try:
            doc.set_toc(new_toc)
        except Exception:
            return 0
    return done


def _strip_embedded(doc):
    """Allegati incorporati: non ispezionabili in modo affidabile (possono essere
    di qualunque formato), quindi si rimuovono tutti."""
    removed = 0
    try:
        names = list(doc.embfile_names())
    except Exception:
        return 0
    for name in names:
        try:
            doc.embfile_del(name)
            removed += 1
        except Exception:
            continue
    return removed


def _readable_text(doc, ocr_pages=frozenset()):
    """TUTTO il testo leggibile del documento: pagine + annotazioni + campi
    modulo + segnalibri. E' la base della verifica dei residui: se un valore
    compare qui, l'anonimizzazione NON e' completa.
    Le pagine in `ocr_pages` (quelle redatte via OCR) vengono RI-OCRIZZATE:
    senza, su una scansione la verifica direbbe "0 residui" sempre, anche con
    una PII ancora visibile nei pixel — il falso-anonimizzato che questo
    modulo esiste per impedire. Il costo (un secondo passaggio OCR sulle sole
    pagine toccate) e' il prezzo dell'onesta'."""
    parts = []
    for page in doc:
        if page.number in ocr_pages:
            parts.append(extract_page_text(page))
        else:
            parts.append(page.get_text())
        try:
            for a in page.annots():
                if a.type[0] == fitz.PDF_ANNOT_REDACT:
                    continue
                info = a.info
                parts.extend(str(info.get(k) or "") for k in ("content", "subject", "title"))
        except Exception:
            pass
        try:
            for w in page.widgets():
                if isinstance(w.field_value, str):
                    parts.append(w.field_value)
        except Exception:
            pass
    try:
        parts.extend(str(e[1] or "") for e in doc.get_toc(simple=True))
    except Exception:
        pass
    return "\n".join(parts)


def _verify_residuals(pdf_bytes, items, ocr_pages=frozenset()):
    """Placeholder il cui valore e' ANCORA leggibile nell'output. Usa lo STESSO
    pattern della redazione (sillabazione inclusa), altrimenti dichiarerebbe
    "0 residui" proprio nei casi che il matcher non sa gestire."""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        text = _readable_text(doc, ocr_pages)
    residual = []
    for ph, val in items:
        pat = _value_pattern(val)
        if pat and pat.search(text):
            residual.append(ph)
    return residual


def _apply_redactions(page):
    """apply_redactions con i pixel delle IMMAGINI cancellati sotto i rect
    (esplicito, non affidato al default che cambia tra versioni) e la grafica
    vettoriale INTATTA dove il binding lo permette: una redazione dentro una
    cella non deve portarsi via i filetti della tabella."""
    kw = {"images": getattr(fitz, "PDF_REDACT_IMAGE_PIXELS", 2)}
    if hasattr(fitz, "PDF_REDACT_LINE_ART_NONE"):
        kw["graphics"] = fitz.PDF_REDACT_LINE_ART_NONE
    try:
        page.apply_redactions(**kw)
    except TypeError:                       # binding vecchio senza i keyword
        page.apply_redactions()


def _insert_text_layer(page, words, redacted, value_tokens):
    """Layer di testo INVISIBILE (render_mode=3) sulla pagina-scansione redatta:
    l'output diventa ricercabile/copiabile e leggibile da un LLM. Non si scrive:
      - dentro le zone redatte (li' c'e' gia' il placeholder visibile);
      - nessuna parola che coincide con un valore del dizionario — un valore
        "saltato" dalla redazione diventerebbe altrimenti testo estraibile,
        che e' peggio dei soli pixel.
    ponytail: niente metriche/Tz alla StudIA — qui serve la ricerca, non la
    selezione pixel-perfect; e solo pagine con rotation 0 (le foto-PDF tipiche),
    per non aprire la danza delle quattro rotazioni per un extra sganciabile."""
    if page.rotation != 0:
        return 0
    written = 0
    for w in words:
        word = (w[4] or "").strip()
        if not word or _norm(word) in value_tokens:
            continue
        r = fitz.Rect(w[0], w[1], w[2], w[3])
        if r.is_empty or any(r.intersects(t) for t in redacted):
            continue
        clean = unicodedata.normalize("NFKC", word).translate(_TRANSLATE)
        clean = clean.encode("latin-1", "replace").decode("latin-1").strip()
        if not clean:
            continue
        fs = max(4.0, min(r.height, 24.0))
        try:
            if page.insert_text((r.x0, r.y1 - fs * 0.18), clean, fontname="helv",
                                fontsize=fs, render_mode=3) > 0:
                written += 1
        except Exception:
            continue
    return written


# --------------------------------------------------------------------------- #
# API pubblica
# --------------------------------------------------------------------------- #
# Colore della casella di redazione: il viola del brand (#7c3a9e) pieno, con il
# placeholder in bianco sopra. Deve SALTARE ALL'OCCHIO scorrendo il documento —
# una casella tenue si confonde con un'evidenziazione qualsiasi, e chi rilegge il
# PDF prima di mandarlo fuori deve vedere subito cosa e' stato coperto.
REDACT_FILL = (0.486, 0.227, 0.620)
REDACT_TEXT = (1.0, 1.0, 1.0)


def redact_pdf(pdf_bytes, mapping, fill=REDACT_FILL, text_color=REDACT_TEXT,
               manual_boxes=None):
    """PDF originale -> PDF con redazione vera + placeholder al posto delle PII.

    mapping: {"[FULLNAME_1]": "Mario Rossi", ...} (il dizionario di analyze()).
    Puo' essere vuoto SOLO se manual_boxes non lo e' (documento con la sola
    firma da coprire).
    manual_boxes: riquadri {page, x0..y1} in frazioni 0-1 della pagina come
    mostrata (gia' validati da parse_manual_boxes); i pixel sotto vengono
    cancellati, senza etichetta (una firma non ha un valore da mappare).

    Le pagine con immagini passano dall'OCR (vedi page_textpage): il testo di
    scansioni e carte intestate entra nello stesso indice char-preciso del
    testo nativo. Sulle pagine-scansione redatte si aggiunge il layer di testo
    invisibile (_insert_text_layer).

    Ritorna (bytes, report) con report = {
        "occurrences":    occorrenze redatte nel testo di pagina,
        "by_placeholder": {placeholder: n_occorrenze},
        "not_found":      placeholder cercati ma senza occorrenze di pagina,
        "skipped":        placeholder NON cercati perche' troppo corti/ambigui
                          (restano in chiaro: va segnalato all'utente),
        "residual":       placeholder ancora leggibili nell'output (deve essere
                          []; le pagine OCR vengono RI-OCRIZZATE per il check),
        "manual_boxes":   riquadri manuali applicati,
        "ocr_pages":      pagine lette via OCR,
        "annots":         sostituzioni nelle annotazioni,
        "widgets":        sostituzioni nei campi modulo,
        "toc":            sostituzioni nei segnalibri,
        "embedded":       allegati rimossi,
    }
    """
    mboxes = list(manual_boxes or [])
    if not isinstance(mapping, dict):
        raise PdfError("Dizionario non valido.")
    items = [(ph, v) for ph, v in mapping.items()
             if isinstance(ph, str) and isinstance(v, str) and v.strip()]
    if not items and not mboxes:
        raise PdfError("Niente da redigere: anonimizza prima il documento "
                       "o disegna almeno un riquadro.")

    boxes_by_page = {}
    for b in mboxes:
        boxes_by_page.setdefault(b["page"], []).append(b)

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        raise PdfError("File PDF non valido o danneggiato.")
    if doc.needs_pass:
        doc.close()
        raise PdfError("PDF protetto da password: rimuovi la protezione e riprova.")

    # valori lunghi per primi: cosi' "Rossi" non spezza la redazione di
    # "Mario Rossi" (i rect gia' coperti vengono saltati da _covered)
    items.sort(key=lambda kv: -len(kv[1]))

    skipped, usable = [], []
    for ph, val in items:
        if _too_noisy(val):
            skipped.append(ph)
            continue
        pat = _value_pattern(val)
        if pat:
            usable.append((ph, val, pat))
        else:
            skipped.append(ph)

    by_ph = {ph: 0 for ph, _, _ in usable}
    patterns = [(pat, ph) for ph, _, pat in usable]   # per annot/widget/TOC
    total = n_annots = n_widgets = n_boxes = 0
    ocr_pages = set()
    # parole che NON possono finire nel layer invisibile: qualunque token di
    # qualunque valore del dizionario (anche i saltati — soprattutto loro)
    value_tokens = {t for _, v in items for t in _norm(v).split()}

    for page in doc:
        tp, mode = page_textpage(page)
        if mode != "native":
            ocr_pages.add(page.number)
        layer_words = None
        if mode == "ocr-full":
            layer_words = page.get_text("words", textpage=tp)
        taken = []
        if usable:
            text, boxes = _page_char_index(page, tp)
            if text.strip():
                for ph, val, pat in usable:
                    for m in pat.finditer(text):
                        rects = _match_rects(boxes, m)
                        placed_any, labeled = False, False
                        for r in rects:
                            if _covered(r, taken):
                                continue
                            fs = 0 if labeled else _fit_fontsize(ph, r)
                            _add_redact_annot(page, r, ph if fs else None,
                                              fs or 6, fill, text_color)
                            taken.append(fitz.Rect(r))
                            placed_any = True
                            labeled = labeled or bool(fs)
                        if placed_any:
                            by_ph[ph] += 1
                            total += 1
        # riquadri manuali: frazioni della pagina come mostrata -> pt. page.rect
        # E' gia' lo spazio "visto" (rotazione inclusa), lo stesso del PNG di
        # anteprima e di add_redact_annot: nessuna matrice da applicare.
        pw, ph_ = page.rect.width, page.rect.height
        for b in boxes_by_page.get(page.number, []):
            r = fitz.Rect(b["x0"] * pw, b["y0"] * ph_, b["x1"] * pw, b["y1"] * ph_)
            if r.is_empty:
                continue
            _add_redact_annot(page, r, None, 6, fill, text_color)
            taken.append(fitz.Rect(r))
            n_boxes += 1
        if taken:
            _apply_redactions(page)   # rimozione VERA: content stream + pixel immagine
        if layer_words:
            _insert_text_layer(page, layer_words, taken, value_tokens)
        # dopo le redazioni: annotazioni e campi modulo non sono content stream
        n_annots += _scrub_annots(page, patterns)
        n_widgets += _scrub_widgets(page, patterns)

    n_toc = _scrub_toc(doc, patterns)
    n_emb = _strip_embedded(doc)
    _scrub_metadata(doc)
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()

    checked = [(ph, v) for ph, v in items if ph in by_ph]
    return out, {
        "occurrences": total,
        "by_placeholder": by_ph,
        "not_found": [ph for ph, n in by_ph.items() if n == 0],
        "skipped": skipped,
        "residual": _verify_residuals(out, checked, ocr_pages),
        "manual_boxes": n_boxes,
        "ocr_pages": len(ocr_pages),
        "annots": n_annots,
        "widgets": n_widgets,
        "toc": n_toc,
        "embedded": n_emb,
    }


def _add_redact_annot(page, rect, text, fontsize, fill, text_color):
    """add_redact_annot con cross_out disattivato dove il binding lo supporta
    (le X diagonali sporcano il placeholder); fallback per le versioni vecchie."""
    kw = dict(text=text, fontname="helv", fontsize=fontsize,
              align=fitz.TEXT_ALIGN_CENTER, fill=fill, text_color=text_color)
    try:
        return page.add_redact_annot(rect, cross_out=False, **kw)
    except TypeError:
        return page.add_redact_annot(rect, **kw)


def text_to_pdf(text, margin=56.0, fontsize=10.5, leading=15.5):
    """Testo (gia' anonimizzato) -> PDF A4 solo testo, impaginato da zero.
    Nessun contenuto del documento originale finisce nell'output."""
    text = unicodedata.normalize("NFKC", text or "").translate(_TRANSLATE)
    # helv copre Latin-1: sostituzione esplicita dei caratteri fuori codifica
    text = text.encode("latin-1", "replace").decode("latin-1")
    if not text.strip():
        raise PdfError("Nessun testo da impaginare.")

    a4 = fitz.paper_rect("a4")
    width = a4.width - 2 * margin

    def tl(s):
        return fitz.get_text_length(s, fontname="helv", fontsize=fontsize)

    def hard_split(line):
        """Spezza le 'parole' piu' larghe della riga (IBAN, URL...)."""
        out = []
        while tl(line) > width and len(line) > 1:
            k = max(1, int(len(line) * width / tl(line)))
            while k > 1 and tl(line[:k]) > width:
                k -= 1
            while k < len(line) and tl(line[:k + 1]) <= width:
                k += 1
            out.append(line[:k])
            line = line[k:]
        out.append(line)
        return out

    def wrap(par):
        if not par:
            return [""]
        lines, cur = [], ""
        for w in par.split(" "):
            cand = (cur + " " + w) if cur else w
            if not cur or tl(cand) <= width:
                cur = cand
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        out = []
        for ln in lines:
            out.extend(hard_split(ln))
        return out

    doc = fitz.open()
    page = doc.new_page(width=a4.width, height=a4.height)
    y = margin + fontsize
    for par in text.split("\n"):
        for ln in wrap(par.rstrip()):
            if y > a4.height - margin:
                page = doc.new_page(width=a4.width, height=a4.height)
                y = margin + fontsize
            if ln:
                page.insert_text((margin, y), ln, fontname="helv",
                                 fontsize=fontsize)
            y += leading

    _scrub_metadata(doc)
    out = doc.tobytes(deflate=True)
    doc.close()
    return out
