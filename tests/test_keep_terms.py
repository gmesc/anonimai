# -*- coding: utf-8 -*-
"""Termini in chiaro: i valori che l'utente dichiara NON personali.

Lo specchio dei Termini personali. Il caso che li ha fatti nascere: nei referti
neuropsicologici le scale portano il nome di chi le ha scritte (RAADS-R di Ritvo,
Beck, Wechsler, Asperger). Il modello li etichetta come persone — e fa il suo
lavoro — ma non sono il paziente, e coprirli rende il testo illeggibile a chi lo
deve usare.

Questa lista TOGLIE protezione: le prove qui sotto guardano soprattutto che non
ne tolga piu' del dovuto (nessuna scoperta parziale, nessuna scoperta su un tag
diverso da quello dichiarato). Senza modello (invariante 4).
"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "app"))

import detectors_local as dl  # noqa: E402


def ent(testo, sub, label):
    i = testo.index(sub)
    return {"label": label, "start": i, "end": i + len(sub)}


class TestParse(unittest.TestCase):

    def test_forme_accettate(self):
        out = dl.parse_keep_terms(["Ritvo",
                                   {"value": "Beck", "tags": ["FULLNAME"]},
                                   {"value": "Wechsler", "tag": "FULLNAME"}])
        self.assertEqual([o["value"] for o in out], ["Ritvo", "Beck", "Wechsler"])
        self.assertEqual(out[0]["tags"], [])                 # vuoto = qualunque tag
        self.assertEqual(out[1]["tags"], ["FULLNAME"])
        self.assertEqual(out[2]["tags"], ["FULLNAME"])       # "tag" singolare accettato

    def test_valori_troppo_corti_scartati(self):
        # sotto i 3 alfanumerici si scoprirebbero frammenti: la trappola dei valori corti
        for corto in ("ab", "R.", "  ", "x1"):
            with self.subTest(corto=corto):
                self.assertEqual(dl.parse_keep_terms([corto]), [])

    def test_dedup_e_tetto(self):
        self.assertEqual(len(dl.parse_keep_terms(["Beck", "beck", "BECK"])), 1)
        self.assertEqual(len(dl.parse_keep_terms(["nome%03d" % i for i in range(500)])),
                         dl.KEEP_TERMS_MAX)

    def test_input_strano_non_solleva(self):
        # prefs.json puo' essere vecchio o toccato a mano
        for cattivo in (None, "stringa", 42, [None], [{"nessun_valore": 1}], [[]]):
            with self.subTest(cattivo=cattivo):
                self.assertIsInstance(dl.parse_keep_terms(cattivo), list)


class TestFiltro(unittest.TestCase):

    TESTO = ("Il paziente e' seguito dal Dr. Beck; il punteggio RAADS-R di Ritvo e' 148. "
             "Il vicino Beckenbauer e il collega Beck Rossi non c'entrano.")

    def setUp(self):
        self.terms = dl.parse_keep_terms(["Ritvo", {"value": "Beck", "tags": ["FULLNAME"]}])

    def test_lascia_in_chiaro_solo_la_corrispondenza_esatta(self):
        ents = [ent(self.TESTO, "Beck", "FULLNAME"),
                ent(self.TESTO, "Ritvo", "FULLNAME"),
                ent(self.TESTO, "Beckenbauer", "FULLNAME"),
                ent(self.TESTO, "Beck Rossi", "FULLNAME")]
        tenute, scartate = dl.drop_keep_terms(self.TESTO, ents, self.terms)
        rimasti = [self.TESTO[e["start"]:e["end"]] for e in tenute]
        # "Beckenbauer" e "Beck Rossi" CONTENGONO il termine ma non lo sono:
        # restano coperti. Se cadessero, un cognome in lista scoprirebbe mezzo documento
        self.assertEqual(rimasti, ["Beckenbauer", "Beck Rossi"])
        self.assertEqual(scartate, {"FULLNAME": 2})

    def test_il_tag_dichiarato_limita_la_regola(self):
        # "Beck" vale solo su FULLNAME: la stessa parola come ORG resta coperta
        ents = [ent(self.TESTO, "Beck", "ORG")]
        tenute, scartate = dl.drop_keep_terms(self.TESTO, ents, self.terms)
        self.assertEqual(len(tenute), 1)
        self.assertEqual(scartate, {})

    def test_senza_tag_vale_ovunque(self):
        # "Ritvo" e' senza tag: cade qualunque etichetta abbia
        ents = [ent(self.TESTO, "Ritvo", "ORG")]
        tenute, _ = dl.drop_keep_terms(self.TESTO, ents, self.terms)
        self.assertEqual(tenute, [])

    def test_maiuscole_e_spaziatura_flessibili(self):
        testo = "La scala BECK\ndepression e' nota."
        terms = dl.parse_keep_terms(["Beck Depression"])
        e = {"label": "FULLNAME", "start": testo.index("BECK"),
             "end": testo.index("depression") + len("depression")}
        tenute, scartate = dl.drop_keep_terms(testo, [e], terms)
        self.assertEqual(tenute, [], "l'a-capo di un PDF non deve far mancare il confronto")
        self.assertEqual(scartate, {"FULLNAME": 1})

    def test_lista_vuota_non_tocca_niente(self):
        ents = [ent(self.TESTO, "Beck", "FULLNAME")]
        tenute, scartate = dl.drop_keep_terms(self.TESTO, ents, [])
        self.assertEqual(len(tenute), 1)
        self.assertEqual(scartate, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
