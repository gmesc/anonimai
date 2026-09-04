# -*- coding: utf-8 -*-
"""Profilo Svizzera/Ticino + Termini personali.

Gli identificativi CH entrano nei tag esistenti: numero AVS -> ID_DOC (checksum
EAN-13), Cantone -> PROVINCE, NAP -> ZIPCODE, targa TI 123456 -> TARGA. I
Termini personali sono la lista {value, tag} salvata in prefs.json: match
letterale case-insensitive con confini di parola, priorita' massima in fusione.

Tutto il codice del fork vive in detectors_local.py (upstream non lo ha):
install() appende i detector CH a detectors.DETECTORS. Senza modello.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "app"))

import detectors as dt  # noqa: E402
import detectors_local as dl  # noqa: E402

dl.install()


def labels(text):
    return {(e["label"], text[e["start"]:e["end"]]) for e in dt.detect_regex(text)}


class TestAvs(unittest.TestCase):

    def test_checksum(self):
        self.assertTrue(dl.avs_ok("756.1234.5678.97"))       # esempio della legenda
        self.assertTrue(dl.avs_ok("7561234567897"))
        self.assertFalse(dl.avs_ok("756.1234.5678.90"))      # cifra di controllo errata
        self.assertFalse(dl.avs_ok("755.1234.5678.97"))      # non inizia per 756
        self.assertFalse(dl.avs_ok("756.1234.5678"))         # troppo corto

    def test_detected_as_id_doc(self):
        found = labels("Numero AVS: 756.1234.5678.97 del paziente.")
        self.assertIn(("ID_DOC", "756.1234.5678.97"), found)

    def test_invalid_stays_clear(self):
        found = labels("Numero AVS: 756.1234.5678.90 del paziente.")
        self.assertNotIn(("ID_DOC", "756.1234.5678.90"), found)

    def test_not_inside_longer_number(self):
        found = {v for _, v in labels("codice 97561234567897 lungo")}
        self.assertFalse(any("756.1234" in v or "7561234567897" == v for v in found))


class TestCantoni(unittest.TestCase):

    def test_nome_da_solo(self):
        self.assertIn(("PROVINCE", "Ticino"), labels("residente in Ticino da anni"))
        self.assertIn(("PROVINCE", "Grigioni"), labels("nei Grigioni nevica"))

    def test_canton_prefisso(self):
        found = labels("l'Ufficio del Canton Ticino e del Cantone Uri")
        vals = {v for l, v in found if l == "PROVINCE"}
        self.assertTrue(any("Canton Ticino" in v for v in vals))
        self.assertTrue(any("Uri" in v for v in vals))

    def test_ti_minuscolo_non_matcha(self):
        found = labels("ti scrivo domani, come ti dissi")
        self.assertFalse(any(l == "PROVINCE" for l, _ in found))


class TestNap(unittest.TestCase):

    def test_ch_prefisso(self):
        self.assertIn(("ZIPCODE", "CH-6600"), labels("indirizzo: CH-6600 Locarno"))

    def test_nap_con_localita(self):
        self.assertIn(("ZIPCODE", "6600"), labels("6600 Locarno, Svizzera"))
        self.assertIn(("ZIPCODE", "6900"), labels("6900 Lugano"))

    def test_anno_non_matcha(self):
        # ponytail: 19xx/20xx esclusi apposta (anni), anche davanti a nome proprio
        found = labels("dal 2019 Marco lavora qui; nel 1998 Anna no")
        self.assertFalse(any(l == "ZIPCODE" for l, _ in found))

    def test_quattro_cifre_senza_localita_non_matcha(self):
        found = labels("il totale fa 6600 franchi")
        self.assertFalse(any(l == "ZIPCODE" for l, _ in found))


class TestTargaSvizzera(unittest.TestCase):

    def test_targa_ti(self):
        self.assertIn(("TARGA", "TI 123456"), labels("auto targata TI 123456 ferma"))

    def test_minuscolo_e_poche_cifre_non_matchano(self):
        found = {v for l, v in labels("ti 123456 e SO 12") if l == "TARGA"}
        self.assertEqual(found, set())


class TestAvsNonDiventaCarta(unittest.TestCase):

    def test_avs_che_supera_luhn_resta_id_doc(self):
        # 756.1000.0000.61 passa EAN-13 e per caso anche Luhn: la regex della carta
        # lo vede. I detector CH stanno in testa, quindi in _merge (sort stabile)
        # ID_DOC vince il pareggio. Qui si verifica il presupposto: ordine in DETECTORS.
        self.assertTrue(dl.avs_ok("756.1000.0000.61"))
        self.assertTrue(dt.luhn_ok("756.1000.0000.61"))
        found = [e["label"] for e in dt.detect_regex("AVS 756.1000.0000.61")
                 if e["start"] == 4]
        self.assertEqual(found[0], "ID_DOC")
        self.assertIs(dt.DETECTORS[0], dl.SWISS_DETECTORS[0])


class TestIdi(unittest.TestCase):

    def test_checksum(self):
        self.assertTrue(dl.idi_ok("CHE-105.805.649"))       # IDI pubblico
        self.assertFalse(dl.idi_ok("CHE-105.805.640"))
        self.assertFalse(dl.idi_ok("CHE-105.805"))

    def test_piva_con_suffisso_iva(self):
        found = labels("IDI CHE-105.805.649 IVA della ditta")
        self.assertIn(("PIVA", "CHE-105.805.649 IVA"), found)

    def test_checksum_errato_redatto_senza_spunta(self):
        ents = [e for e in dt.detect_regex("CHE-105.805.640") if e["label"] == "PIVA"]
        self.assertEqual(len(ents), 1)
        self.assertFalse(ents[0]["validated"])


class TestTelefonoSvizzero(unittest.TestCase):

    def test_forme(self):
        for tel in ("+41 91 123 45 67", "091 123 45 67", "079 123 45 67",
                    "+41 (0)91 234 56 78", "0041 79 123 45 67"):
            self.assertIn(("TELEPHONENUM", tel), labels(f"tel. {tel} ok"), tel)

    def test_numero_italiano_ancora_visto(self):
        self.assertIn(("TELEPHONENUM", "010-2471234"), labels("tel 010-2471234"))


class TestImportiChf(unittest.TestCase):

    def test_forme(self):
        for amt in ("CHF 1'250.00", "Fr. 12'500.–", "3'000 franchi", "250.00 CHF", "CHF 500"):
            self.assertIn(("AMOUNT", amt), labels(f"importo {amt} pagato"), amt)

    def test_euro_intatto(self):
        self.assertIn(("AMOUNT", "€ 12.500,00"), labels("costo € 12.500,00 iva"))


class TestCatastoTicinese(unittest.TestCase):

    def test_mappale_rfd(self):
        found = labels("mappale n. 1234 RFD Lugano; fondo n. 567 RFD di Bellinzona")
        self.assertIn(("CATASTO", "mappale n. 1234 RFD Lugano"), found)
        self.assertIn(("CATASTO", "fondo n. 567 RFD di Bellinzona"), found)

    def test_fondo_parola_comune_non_matcha(self):
        found = labels("in fondo alla via 3, il fondo 12 e' vuoto")
        self.assertFalse(any(l == "CATASTO" for l, _ in found))


class TestTesseraAssicurato(unittest.TestCase):

    def test_20_cifre_prefisso_80756(self):
        ents = [e for e in dt.detect_regex("tessera 80756123456789012345 cassa")
                if e["label"] == "ID_DOC"]
        self.assertEqual(len(ents), 1)
        self.assertFalse(ents[0]["validated"])     # solo forma, niente spunta

    def test_non_dentro_numero_piu_lungo(self):
        found = labels("n. 980756123456789012345")
        self.assertFalse(any(l == "ID_DOC" for l, _ in found))


class TestTerminiPersonali(unittest.TestCase):

    TERMS = [{"value": "Istituto Elvetico", "tag": "ORG"},
             {"value": "Progetto Aurora", "tag": "PROGETTO"}]

    def test_match_case_insensitive_confini(self):
        ents = dl.match_custom_terms(
            "L'ISTITUTO ELVETICO di Lugano segue il progetto aurora.", self.TERMS)
        got = {(e["label"], e["source"]) for e in ents}
        self.assertEqual(got, {("ORG", "utente"), ("PROGETTO", "utente")})

    def test_niente_match_dentro_parola(self):
        ents = dl.match_custom_terms("il Superistituto Elvetico", self.TERMS)
        self.assertEqual(ents, [])

    def test_spazi_flessibili(self):
        ents = dl.match_custom_terms("Istituto\n  Elvetico", self.TERMS)
        self.assertEqual(len(ents), 1)

    def test_parse_scarta_corti_e_tag_invalidi(self):
        raw = [{"value": "ok termine", "tag": "org"},
               {"value": "ab", "tag": "ORG"},              # < 3 alfanumerici
               {"value": "valido", "tag": "un tag no"},    # tag fuori grammatica
               {"value": "ok termine", "tag": "ORG"},      # duplicato (case-insensitive)
               "spazzatura"]
        out = dl.parse_custom_terms(raw)
        self.assertEqual(out, [{"value": "ok termine", "tag": "ORG"}])

    def test_parse_tetto(self):
        raw = [{"value": f"termine numero {i}", "tag": "ORG"} for i in range(300)]
        self.assertEqual(len(dl.parse_custom_terms(raw)), dl.CUSTOM_TERMS_MAX)


if __name__ == "__main__":
    unittest.main(verbosity=2)
