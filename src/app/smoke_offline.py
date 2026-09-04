# -*- coding: utf-8 -*-
"""Prova DINAMICA dell'invariante 1: si esercita l'app intera — modello, OCR,
redazione PDF, anteprime — con la rete verso l'esterno **fisicamente impedita**.

Come funziona: prima di importare `app` si sostituisce `socket.socket.connect`
(e `connect_ex`, e `create_connection`) con una versione che LANCIA se
l'indirizzo non e' loopback. Se una qualunque riga di codice — nostra, di
transformers, di huggingface_hub, di PyMuPDF — tentasse una connessione, questo
script morirebbe con lo stack che dice esattamente chi. Poi si chiamano tutti gli
endpoint con il test client di Flask e si controllano le intestazioni di sicurezza
su ogni risposta.

Non sostituisce la prova a livello di sistema (sandbox / `--network none`,
vedi docs/VERIFICA-OFFLINE.md): un blocco in-process non vedrebbe una connessione
aperta da una libreria nativa. Le due prove insieme coprono i due piani.

    python src/app/smoke_offline.py            # richiede il modello
"""

import io
import json
import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

VIOLAZIONI = []
_orig_connect = socket.socket.connect
_orig_connect_ex = socket.socket.connect_ex
_orig_create = socket.create_connection


def _loopback(addr):
    try:
        host = addr[0] if isinstance(addr, (tuple, list)) else str(addr)
    except Exception:
        return False
    return str(host) in ("127.0.0.1", "::1", "localhost", "", "0.0.0.0")


def _guard(fn, nome):
    def wrapper(*a, **k):
        addr = a[1] if nome == "socket.connect" else (a[0] if a else None)
        if not _loopback(addr):
            VIOLAZIONI.append((nome, addr))
            raise OSError(f"EGRESS BLOCCATO da smoke_offline: {nome} -> {addr!r}")
        return fn(*a, **k)
    return wrapper


socket.socket.connect = _guard(_orig_connect, "socket.connect")
socket.socket.connect_ex = _guard(_orig_connect_ex, "socket.connect_ex")
socket.create_connection = _guard(_orig_create, "socket.create_connection")

# L'import carica il modello: da qui in poi ogni tentativo di rete e' un'eccezione.
import app as A  # noqa: E402
import pdf_export  # noqa: E402

OK, KO = [], []
ATTESI = {"Content-Security-Policy", "Cache-Control", "X-Content-Type-Options",
          "Referrer-Policy", "X-Frame-Options"}


def controlla(nome, resp, atteso=200, corpo=None):
    problemi = []
    if resp.status_code != atteso:
        problemi.append(f"status {resp.status_code} invece di {atteso}")
    mancanti = ATTESI - set(resp.headers.keys())
    if mancanti:
        problemi.append("intestazioni mancanti: " + ", ".join(sorted(mancanti)))
    csp = resp.headers.get("Content-Security-Policy", "")
    if "connect-src 'self'" not in csp:
        problemi.append("CSP senza connect-src 'self'")
    if "no-store" not in resp.headers.get("Cache-Control", ""):
        problemi.append("Cache-Control senza no-store")
    if corpo:
        problemi += corpo(resp) or []
    (KO if problemi else OK).append((nome, problemi))
    print(("  KO  " if problemi else "  ok  ") + nome + ("  <- " + "; ".join(problemi) if problemi else ""))


TESTO = ("Il paziente Mario Bernasconi, n. AVS 756.9217.0769.85, 6900 Lugano, "
         "Canton Ticino, tel. 091 123 45 67. Ditta Alfa SA, IDI CHE-123.456.788 IVA, "
         "IBAN CH93 0076 2011 6238 5295 7, CHF 1'250.00, mappale n. 1234 RFD Lugano, "
         "targa TI 123456, mario@studio.ch")


def main():
    c = A.app.test_client()
    print(f"\nAnonimAI {A.APP_VERSION} · modello {os.path.basename(str(A.MODEL_DIR))} · "
          f"OCR {'attivo' if pdf_export.ocr_available() else 'assente'}")
    print("Rete verso l'esterno: BLOCCATA in-process\n")

    controlla("GET /", c.get("/"))
    controlla("GET /health", c.get("/health"),
              corpo=lambda r: [] if r.get_json().get("model_loaded") else ["modello non pronto"])
    controlla("GET /settings", c.get("/settings"))
    controlla("GET /config", c.get("/config"))
    controlla("GET /assets/tokens.css", c.get("/assets/tokens.css"))

    def verifica_analyze(r):
        d = r.get_json()
        att = {"ID_DOC", "PIVA", "IBAN", "AMOUNT", "CATASTO", "TARGA",
               "TELEPHONENUM", "ZIPCODE", "PROVINCE", "EMAIL"}
        manc = att - set(d.get("by_label", {}))
        out = []
        if manc:
            out.append("tag non rilevati: " + ", ".join(sorted(manc)))
        for valore in ("756.9217.0769.85", "CHE-123.456.788", "CH93 0076",
                       "1'250.00", "TI 123456", "mario@studio.ch"):
            if valore in d["anonymized_text"]:
                out.append(f"VALORE IN CHIARO nell'output: {valore}")
        return out

    controlla("POST /analyze (testo ticinese)",
              c.post("/analyze", json={"text": TESTO}), corpo=verifica_analyze)

    controlla("POST /analyze (dizionario spento)",
              c.post("/analyze", json={"text": TESTO, "include_mapping": False}),
              corpo=lambda r: ([] if not r.get_json().get("mapping")
                               else ["mapping presente a dizionario spento"])
              + ([] if all("t" not in s for s in r.get_json()["segments"] if s.get("label"))
                 else ["i segmenti-entita' portano ancora il testo originale"]))

    fx = ROOT / "docs" / "guida" / "tools" / "fixtures"
    for nome_pdf, etichetta in (("atto_esempio.pdf", "PDF nativo"),
                                ("scansione_esempio.pdf", "PDF scansione (OCR)")):
        f = fx / nome_pdf
        if not f.exists():
            print(f"  --  {etichetta}: fixture assente, saltato")
            continue
        dati = f.read_bytes()
        controlla(f"POST /analyze ({etichetta})",
                  c.post("/analyze", data={"pdf": (io.BytesIO(dati), nome_pdf)},
                         content_type="multipart/form-data"))
        r = c.post("/pdf/preview", data={"pdf": (io.BytesIO(dati), nome_pdf)},
                   content_type="multipart/form-data")
        controlla(f"POST /pdf/preview ({etichetta})", r)
        if r.status_code == 200:
            doc_id = r.get_json()["doc_id"]
            controlla(f"GET /doc/<id>/page/0.png ({etichetta})",
                      c.get(f"/doc/{doc_id}/page/0.png"))
            controlla(f"GET /doc/<id>/page/0.png?dpi=220 ({etichetta})",
                      c.get(f"/doc/{doc_id}/page/0.png?dpi=220"))
            controlla(f"GET /doc/<id>/file.pdf ({etichetta})",
                      c.get(f"/doc/{doc_id}/file.pdf"))
        controlla(f"POST /pdf ({etichetta})",
                  c.post("/pdf", data={"pdf": (io.BytesIO(dati), nome_pdf)},
                         content_type="multipart/form-data"))
        controlla(f"POST /pdf + riquadro manuale ({etichetta})",
                  c.post("/pdf", data={"pdf": (io.BytesIO(dati), nome_pdf),
                                       "manual_boxes": json.dumps(
                                           [{"page": 0, "x0": .1, "y0": .1,
                                             "x1": .5, "y1": .2}])},
                         content_type="multipart/form-data"))

    controlla("POST /preview (testo)", c.post("/preview", json={"text": TESTO}), atteso=400)

    print(f"\n{'='*66}\nendpoint provati: {len(OK)+len(KO)} · ok: {len(OK)} · problemi: {len(KO)}")
    print(f"tentativi di connessione verso l'esterno: {len(VIOLAZIONI)}")
    for v in VIOLAZIONI:
        print("   !!", v)
    if KO:
        print("\nPROBLEMI:")
        for nome, p in KO:
            print(f" - {nome}: {'; '.join(p)}")
    print("=" * 66)
    return 1 if (KO or VIOLAZIONI) else 0


if __name__ == "__main__":
    sys.exit(main())
