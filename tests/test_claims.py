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
    # «garantisce» e «guarantees» con qualunque cosa in mezzo: la prima versione
    # pretendeva la parola subito dopo, e «guarantees FULL anonymization» passava
    # (buco trovato provando otto claim falsi, non leggendo la regex).
    ("garanzia di risultato",
     r"\bgarantis(?:ce|cono|ce\s+che)\b|\bgaranzia\s+di\s+\w+"
     r"|\bguarantee[sd]?\b(?![^.;!?\n]{0,40}\bno\b)"
     r"|\bassicura\s+(?:che\s+)?(?:l[ao']|il|tutt|ogni|la\s+conformit)"
     r"|\bensures?\s+(?:that\s+)?(?:all|every|complete|full|no\s+\w+\s+(?:is|are)\s+left)"),
    # Assolutismi: la forma piu' pericolosa non e' «compliant», e' «tutti», «sempre»,
    # «mai», «nessun», «perfetto» applicati al risultato dell'anonimizzazione.
    ("assolutismo",
     r"\b100\s*%\s*(?:anonim|sicur|safe|secure|accurat|affidabil|reliable|protett|protected)"
     r"|\bnessun\s+rischio\b|\bzero\s+risk\b|\bnessun\s+errore\b|\brischio\s+zero\b"
     r"|\bsempre\s+(?:accurat|corrett|affidabil)|\bnever\s+(?:wrong|fails?|misses)\b"
     r"|\binfallibil|\bfoolproof\b|\bair[\s-]?tight\b"
     r"|\b(?:tutt[ei]|ogni|qualsiasi|qualunque)\s+(?:i\s+)?"
     r"(?:dat[oi]|informazion\w*|PII|element[oi])\s+"
     r"(?:person\w+\s+)?(?:vengono\s+|sono\s+|e'\s+|è\s+)?"
     r"(?:sempre\s+)?(?:rimoss|anonimizzat|elimin|sostituit|protett|nascost)"
     r"|\b(?:all|every|each)\s+(?:single\s+)?"
     r"(?:personal\s+)?(?:data|details?|information|identifiers?|PII)\s+"
     r"(?:is|are|gets?|will\s+be)\s+(?:always\s+)?"
     r"(?:removed|anonymi[sz]ed|stripped|replaced|protected|hidden)"
     r"|\bperfettamente\s+(?:anonim|protett|sicur)|\bperfectly\s+(?:protected|anonymi|safe|secure)"
     r"|\bcompletamente\s+(?:anonim|sicur|protett)\b"
     r"|\bnothing\s+(?:can\s+)?(?:ever\s+)?(?:escapes?|leaks?|gets?\s+out)"
     r"|\bniente\s+(?:puo'|può)\s+(?:mai\s+)?(?:sfuggir|uscir)"),
    # «usalo e sei a posto con la legge»: promette un esito giuridico.
    ("esito giuridico promesso",
     r"\b(?:sei|siete|sarai|sarete|resti|restate)\s+(?:cosi'\s+|così\s+)?"
     r"(?:in\s+regola|a\s+norma|coperto|al\s+sicuro\s+dalla\s+legge)"
     r"|\byou\s+(?:are|will\s+be|stay)\s+(?:then\s+)?"
     r"(?:in\s+line\s+with\s+the\s+law|compliant|covered|legally\s+safe)"
     r"|\b(?:ti\s+)?mette\s+(?:al\s+riparo|in\s+regola)"
     r"|\brende\s+(?:il\s+trattamento\s+)?(?:legittimo|conforme|lecito)\b"),
]

# Se una di queste compare poco prima del match, e' una negazione: ammessa.
NEGAZIONI = re.compile(
    r"\b(?:non|no|nessun[ao]?|senza|mai|not|never|without|does\s+not|do\s+not|"
    r"n[eè]|nor|escluso|salvo)\b[^.;:!?]{0,60}$", re.IGNORECASE)


def trova_claim(testo, origine=""):
    """I claim non sostenibili dentro un testo. Lavora su una STRINGA e non su un
    file apposta: cosi' la batteria di frasi qui sotto si prova senza toccare i
    documenti veri (una prova che modifica il README non puo' girare in CI)."""
    fuori = []
    for etichetta, pattern in VIETATI:
        for m in re.finditer(pattern, testo, re.IGNORECASE):
            prima = testo[max(0, m.start() - 90):m.start()]
            if NEGAZIONI.search(prima):
                continue                              # «non certifica», «senza garanzia»
            riga = testo[:m.start()].count("\n") + 1
            fuori.append(f"{origine}:{riga}: {etichetta} -> "
                         f"{testo[m.start():m.end() + 40]!r}")
    return fuori


# Batteria di controllo: 26 modi di dire il falso e 8 di dirlo bene. Serve a provare
# che il lint NON e' decorativo. Nasce da una prova reale: la prima versione delle
# regex ne bloccava 3 su 8 — «guarantees FULL anonymization» passava perche' il
# pattern pretendeva la parola subito dopo. Chi tocca VIETATI rilancia questa lista.
CLAIM_FALSI = [
    "AnonimAI is GDPR compliant.", "Certified for the Swiss nLPD.",
    "100% secure, zero risk.", "The app guarantees full anonymization.",
    "This guarantees your data is safe.", "Your documents are perfectly protected.",
    "Nothing can ever escape this app.", "Every single personal detail is removed, always.",
    "All personal data is removed.", "Each identifier is anonymised.",
    "Use it and you are in line with the law.", "You are covered.",
    "It ensures that all identifiers are stripped.", "Foolproof redaction.",
    "The tool never misses a name.", "It is 100% reliable.",
    "Garantisce l'anonimizzazione completa.", "Garanzia di conformita' totale.",
    "Tutti i dati personali vengono rimossi.", "Ogni informazione personale e' anonimizzata.",
    "Con AnonimAI sei in regola con la nLPD.", "Rende il trattamento conforme.",
    "I tuoi documenti sono perfettamente protetti.", "Niente puo' mai sfuggire.",
    "Rischio zero per i tuoi dati.", "Assicura che tutti i nomi siano nascosti.",
]

# Il rovescio: dire i limiti deve restare possibile, o il lint spinge a tacere.
FRASI_LECITE = [
    "The model can be wrong: always re-read the output.",
    "It does not certify the compliance of any processing.",
    "No warranty of any kind is given.",
    "Non garantisce alcun risultato: rileggi sempre l'output.",
    "Nessun dato esce dal computer.",
    "Designed for GDPR and nLPD, but you remain the data controller.",
    "Detection is statistical and can miss values.",
    "Il software non certifica la conformita' di alcun trattamento.",
]


class TestDichiarazioni(unittest.TestCase):

    def test_nessun_claim_di_conformita(self):
        problemi = []
        for rel in TESTI:
            f = ROOT / rel
            if not f.exists():
                continue
            problemi += trova_claim(f.read_text("utf-8", errors="replace"), rel)
        self.assertEqual(problemi, [], "claim non sostenibili:\n" + "\n".join(problemi))

    def test_il_lint_riconosce_i_claim_falsi(self):
        sfuggiti = [f for f in CLAIM_FALSI if not trova_claim(f)]
        self.assertEqual(sfuggiti, [], "claim falsi non riconosciuti:\n" + "\n".join(sfuggiti))

    def test_il_lint_non_censura_le_frasi_oneste(self):
        bloccate = [f for f in FRASI_LECITE if trova_claim(f)]
        self.assertEqual(bloccate, [], "frasi lecite bloccate:\n" + "\n".join(bloccate))

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
