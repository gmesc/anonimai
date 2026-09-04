# -*- coding: utf-8 -*-
"""Le dichiarazioni pubbliche non possono promettere piu' di quanto il software regge.

Il rischio non e' tecnico ma di parola: «conforme», «certificato», «garantisce»,
«100% anonimo» sono giudizi su un trattamento, non proprieta' di un programma —
e in Svizzera un claim ingannevole cade sotto la LCSl a prescindere dal danno.
Questo test li vieta nei testi che l'utente legge (UI, README, sito, splash,
condizioni). Le NEGAZIONI restano ammesse, anzi sono il modo giusto di dirlo:
«non certifica la conformita' di alcun trattamento» deve poter esistere.

Gira senza modello e senza dipendenze (invariante 4)."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TESTI = ["src/app/app.py", "README.md", "docs/index.html", "tauri/ui/index.html",
         "TERMS.md", "SECURITY.md", "docs/CONFORMITA-CH.md", "docs/guida/index.html"]

# (etichetta, regex). Cercano l'AFFERMAZIONE, non la parola.
VIETATI = [
    ("conformita' dichiarata del prodotto",
     r"\b(?:gdpr|nlpd|lpd|lpdp)[\s-]*compliant\b|\bcompliant\s+(?:with|con)\b"),
    ("conformita' affermata",
     r"\b(?:e'|è|is|sono|are)\s+(?:pienamente\s+|fully\s+)?conform[ei]\b"),
    # "posta elettronica certificata" / "certified mail" e' il nome di un servizio,
    # non una dichiarazione di conformita': si esclude quel contesto.
    ("certificazione",
     r"\bcertificat[oiae]\b(?!\s+(?:mail|posta))|\bcertified\b(?!\s+mail)"
     r"|\bcertifica\s+la\s+conformit"),
    ("garanzia di risultato",
     r"\bgarantis(?:ce|cono)\b|\bgaranzia\s+di\s+(?:anonim|conformit|risultat)"
     r"|\bguarantees?\s+(?:that|anonym|complian)"),
    ("assolutismo",
     r"\b100\s*%\s*(?:anonim|sicur|safe|secure|accurat)"
     r"|\bnessun\s+rischio\b|\bzero\s+risk\b|\bnessun\s+errore\b"
     r"|\bsempre\s+accurat|\bnever\s+wrong\b|\binfallibil"),
]

# Se una di queste compare poco prima del match, e' una negazione: ammessa.
NEGAZIONI = re.compile(
    r"\b(?:non|no|nessun[ao]?|senza|mai|not|never|without|does\s+not|do\s+not|"
    r"n[eè]|nor|escluso|salvo)\b[^.;:!?]{0,60}$", re.IGNORECASE)


class TestDichiarazioni(unittest.TestCase):

    def test_nessun_claim_di_conformita(self):
        problemi = []
        for rel in TESTI:
            f = ROOT / rel
            if not f.exists():
                continue
            testo = f.read_text("utf-8", errors="replace")
            for etichetta, pattern in VIETATI:
                for m in re.finditer(pattern, testo, re.IGNORECASE):
                    prima = testo[max(0, m.start() - 90):m.start()]
                    if NEGAZIONI.search(prima):
                        continue                      # «non certifica», «senza garanzia»
                    riga = testo[:m.start()].count("\n") + 1
                    problemi.append(f"{rel}:{riga}: {etichetta} -> "
                                    f"{testo[m.start():m.end() + 40]!r}")
        self.assertEqual(problemi, [], "claim non sostenibili:\n" + "\n".join(problemi))

    def test_i_limiti_sono_dichiarati(self):
        """Il rovescio: i testi DEVONO dire i limiti. Se qualcuno li togliesse per
        «semplificare la comunicazione», questo test se ne accorge."""
        app = (ROOT / "src" / "app" / "app.py").read_text("utf-8")
        for atteso in ("pseudonimizzazione", "può sbagliare", "Rileggi sempre l'output",
                       "titolare del trattamento", "senza garanzia"):
            self.assertIn(atteso, app, f"la UI non dichiara piu': {atteso}")
        for rel in ("TERMS.md", "SECURITY.md"):
            self.assertTrue((ROOT / rel).exists(), f"manca {rel}")

    def test_le_metriche_sono_attribuite(self):
        """0.989 e' il benchmark ITALIANO del modello upstream: ovunque compaia deve
        esserci l'attribuzione, o diventa una promessa sul profilo svizzero."""
        chiavi = ("italian benchmark", "benchmark italiano", "real it validation",
                  "validation italiana", "italian** benchmark", "benchmark **italian",
                  "val. reale it", "italian validation", "real italian** benchmark",
                  "italian benchmark of the upstream")
        problemi = []
        for rel in ("README.md", "docs/index.html"):
            f = ROOT / rel
            if not f.exists():
                continue
            testo = f.read_text("utf-8", errors="replace").lower()
            for m in re.finditer(r"0\.989", testo):
                # l'attribuzione deve stare ACCANTO al numero, non da qualche parte
                # nel file: un test che cercava in tutto il documento restava verde
                # anche togliendo la nota (guasto pagato in mutation testing).
                finestra = testo[max(0, m.start() - 300):m.start() + 400]
                if not any(k in finestra for k in chiavi):
                    riga = testo[:m.start()].count("\n") + 1
                    problemi.append(f"{rel}:{riga}: 0.989 senza attribuzione vicina")
        self.assertEqual(problemi, [], "\n".join(problemi))


if __name__ == "__main__":
    unittest.main(verbosity=2)
