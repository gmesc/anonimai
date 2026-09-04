# -*- coding: utf-8 -*-
"""Estensioni LOCALI del fork gmesc/anonimai: profilo Svizzera + Termini personali.

Questo file NON esiste nel repo upstream (Rizzo-AI-Academy/rizzo-pii): tutto il
codice del fork vive qui apposta, cosi' i merge/cherry-pick da upstream non lo
toccano mai. Gli agganci dentro i file di upstream sono ridotti a singole righe
(vedi app.py: install(), swissify_tags(), load_custom_terms(),
match_custom_terms(), save_custom_terms()).

Come detectors.py: solo stringhe, zero torch/transformers/fitz -> testabile in
isolamento (tests/test_svizzera.py).
"""

import json
import re

import detectors
import server_config


# --------------------------------------------------------------------------- #
# Profilo Svizzera/Ticino — identificativi CH nei tag esistenti.
# La casella per il numero AVS e' ID_DOC (la tassonomia manda li' ogni numero
# previdenziale personale), il Cantone e' PROVINCE, il NAP e' ZIPCODE.
# Sempre attivi: un formato AVS in un documento italiano non esiste, un cantone
# citato E' una PII geografica.
# --------------------------------------------------------------------------- #
def avs_ok(s):
    """Numero AVS svizzero (756.xxxx.xxxx.xx): 13 cifre che iniziano per 756,
    ultima cifra = checksum EAN-13 (pesi 1/3 alternati sulle prime 12)."""
    d = re.sub(r"\D", "", s)
    if len(d) != 13 or not d.startswith("756"):
        return False
    tot = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(d[:12]))
    return (10 - tot % 10) % 10 == int(d[12])


SWISS_DETECTORS = [
    ("ID_DOC",
     re.compile(r"(?<!\d)756[.\s]?\d{4}[.\s]?\d{4}[.\s]?\d{2}(?!\d)"),
     avs_ok, True),
    # Cantoni per nome: solo quelli che non sono omonimi di citta' (Zurigo, Berna,
    # Ginevra... li etichetta gia' il modello come CITY) ne' parole comuni
    # ("Giura" e' anche un verbo, "Uri" troppo corto: passano solo da "Canton X").
    ("PROVINCE",
     re.compile(r"\b(?:Ticino|Grigioni|Graub(?:u|ü)nden|Vallese|Wallis|Argovia"
                r"|Turgovia|Sciaffusa|Obvaldo|Nidvaldo|Glarona|Soletta|Svitto"
                r"|Appenzello(?:\s+(?:Esterno|Interno))?|Vaud|Neuch(?:a|â)tel)\b"),
     None, True),
    # "Canton(e) <Nome>" o "Canton <SIGLA>": copre anche Uri, Giura, Berna...
    ("PROVINCE",
     re.compile(r"\bCanton(?:e)?\s+(?:[A-ZÀ-Ü][A-Za-zà-üÀ-Ü'\-]+|[A-Z]{2})\b"),
     None, True),
    # NAP: CH-#### sempre; il 4-cifre nudo solo seguito da una localita'
    # capitalizzata ("6600 Locarno").
    # ponytail: si escludono 19xx/20xx (anni: "dal 2019 Marco..." matcherebbe),
    # al prezzo dei NAP romandi 19xx/20xx (1950 Sion) scritti senza CH-.
    # I NAP ticinesi (65xx-69xx) passano tutti. Se servisse il Vallese: contesto.
    ("ZIPCODE",
     re.compile(r"\bCH-\d{4}\b"),
     None, True),
    ("ZIPCODE",
     re.compile(r"(?<![\dA-Za-z-])(?!(?:19|20)\d{2})[1-9]\d{3}"
                r"(?=\s[A-ZÀ-Ü][a-zà-üé]{2,})"),
     None, True),
    # Targa svizzera: sigla cantonale MAIUSCOLA + 3-6 cifre ("TI 123456").
    # Niente IGNORECASE ("ti 1234" e' prosa) e almeno 3 cifre (sotto, troppe
    # collisioni con elenchi tipo "SO 12").
    ("TARGA",
     re.compile(r"\b(?:AG|AI|AR|BE|BL|BS|FR|GE|GL|GR|JU|LU|NE|NW|OW|SG|SH|SO"
                r"|SZ|TG|TI|UR|VD|VS|ZG|ZH)[ \-]\d{3,6}\b"),
     None, True),
]

_installed = False


def install():
    """Appende i detector CH a detectors.DETECTORS (idempotente): detect_regex
    li usa da subito, senza modificare il file di upstream."""
    global _installed
    if not _installed:
        detectors.DETECTORS.extend(SWISS_DETECTORS)
        _installed = True


# Legenda con doppio identificativo IT <-> CH. Esempi che passano il proprio
# checksum (lezione della issue #99: 756.1234.5678.97 e' un AVS valido).
_TAG_OVERRIDES = {
    "ZIPCODE": ("CAP / NAP svizzero", "ZIP / Swiss postal code (NAP)", "00185 · CH-6600"),
    "PROVINCE": ("Provincia / Cantone svizzero", "Province / Swiss canton", "MI · Canton Ticino"),
    "ID_DOC": ("Numero di documento d'identità (carta, passaporto, patente, n. AVS)",
               "Identity document number (ID card, passport, driving licence, Swiss AVS number)",
               "CA12345AB · 756.1234.5678.97"),
    "TARGA": ("Targa di veicolo (anche svizzera)", "Vehicle plate (Swiss included)",
              "AB 123 CD · TI 123456"),
}


def swissify_tags(tags):
    """Riscrive le voci di legenda dei tag che hanno un doppio identificativo CH."""
    return [(t,) + _TAG_OVERRIDES.get(t, (it, en, ex)) for t, it, en, ex in tags]


# --------------------------------------------------------------------------- #
# Termini personali — lista {value, tag} salvata in prefs.json (chiave
# "custom_terms", che save_prefs() di upstream preserva perche' riscrive il file
# unendo le chiavi). ATTENZIONE: contiene stringhe sensibili scelte dall'utente
# e vive su disco per scelta esplicita (la scheda Sicurezza lo dichiara).
# --------------------------------------------------------------------------- #
CUSTOM_TERMS_MAX = 200            # voci; oltre, le prime vincono
CUSTOM_TERM_MAXLEN = 300          # caratteri per valore
_TAG_RX = re.compile(r"^[A-Z0-9_]{2,20}$")


def parse_custom_terms(value) -> list:
    """Normalizza i Termini personali: lista di {"value", "tag"}.
    Scarta (mai errore: prefs.json puo' essere vecchio o toccato a mano) le voci
    senza >= 3 caratteri alfanumerici — sotto, il match devasterebbe il documento
    (stessa trappola dei valori corti del PDF) — e i tag fuori da [A-Z0-9_]{2,20}.
    Dedup su (valore lowercase, tag); tetto CUSTOM_TERMS_MAX."""
    if not isinstance(value, (list, tuple)):
        return []
    out, seen = [], set()
    for it in value:
        if not isinstance(it, dict):
            continue
        val = str(it.get("value") or "").strip()[:CUSTOM_TERM_MAXLEN]
        tag = str(it.get("tag") or "").strip().upper()
        if sum(c.isalnum() for c in val) < 3 or not _TAG_RX.match(tag):
            continue
        key = (val.lower(), tag)
        if key in seen:
            continue
        seen.add(key)
        out.append({"value": val, "tag": tag})
        if len(out) >= CUSTOM_TERMS_MAX:
            break
    return out


def match_custom_terms(text, terms):
    """Entita' dai Termini personali: match letterale case-insensitive con
    confini di parola (stessa disciplina del matching PDF: niente "DE" dentro
    "CORDELLA"); gli spazi del termine valgono qualsiasi spaziatura (a-capo dei
    PDF inclusi). source="utente": in fusione vince su tutto — un termine
    inserito a mano e' la dichiarazione piu' esplicita possibile."""
    ents = []
    for t in terms or ():
        val = (t.get("value") or "").strip()
        tag = (t.get("tag") or "").strip().upper()
        if not val or not tag:
            continue
        pat = r"(?<!\w)" + r"\s+".join(re.escape(w) for w in val.split()) + r"(?!\w)"
        for m in re.finditer(pat, text, re.IGNORECASE):
            ents.append({"label": tag, "start": m.start(), "end": m.end(),
                         "score": 1.0, "validated": True, "source": "utente"})
    return ents


def _read_prefs_raw() -> dict:
    try:
        data = json.loads(server_config.prefs_path().read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def load_custom_terms() -> list:
    return parse_custom_terms(_read_prefs_raw().get("custom_terms"))


def save_custom_terms(terms) -> list:
    """Scrive SOLO la chiave custom_terms in prefs.json, lasciando intatte le
    chiavi di upstream (excluded_tags, mapping_enabled)."""
    data = _read_prefs_raw()
    data["custom_terms"] = parse_custom_terms(terms)
    d = server_config.config_dir()
    d.mkdir(parents=True, exist_ok=True)
    server_config.prefs_path().write_text(json.dumps(data, indent=2), "utf-8")
    return data["custom_terms"]
