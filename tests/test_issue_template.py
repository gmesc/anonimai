# -*- coding: utf-8 -*-
"""I moduli delle issue restano validi, e continuano a chiedere la spunta sui dati veri.

Due ragioni per provarli, e nessuna e' formale.

La prima: un modulo YAML malformato GitHub **non lo segnala** — lo ignora e mostra la
casella vuota di sempre. Il difetto si scopre quando qualcuno ha gia' aperto la issue
sbagliata, cioe' troppo tardi.

La seconda conta di piu': in ogni modulo c'e' una spunta obbligatoria con cui chi
scrive dichiara di non aver incollato dati personali veri. E' l'ultima barriera prima
che un valore reale finisca in una pagina pubblica e indicizzabile per sempre, ed e'
esattamente il genere di riga che sparisce durante un ritocco frettoloso.

Gira senza modello (invariante 4).
"""
import os
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CARTELLA = os.path.join(ROOT, ".github", "ISSUE_TEMPLATE")

try:
    import yaml
except ImportError:                                  # pragma: no cover
    yaml = None

TIPI_AMMESSI = {"markdown", "input", "textarea", "dropdown", "checkboxes"}


def _moduli():
    """I moduli veri, cioe' tutti tranne config.yml (che e' un'altra cosa)."""
    if not os.path.isdir(CARTELLA):
        return []
    return [os.path.join(CARTELLA, f) for f in sorted(os.listdir(CARTELLA))
            if f.endswith((".yml", ".yaml")) and f != "config.yml"]


@unittest.skipIf(yaml is None, "PyYAML non installato")
class TestModuliIssue(unittest.TestCase):

    def test_ci_sono_dei_moduli(self):
        # se la cartella sparisce, il test deve fallire invece di passare a vuoto
        self.assertGreaterEqual(len(_moduli()), 3, "mancano i moduli delle issue")

    def test_yaml_valido_e_campi_che_github_esige(self):
        for f in _moduli():
            with self.subTest(modulo=os.path.basename(f)):
                with open(f, encoding="utf-8") as fh:
                    d = yaml.safe_load(fh)
                self.assertIsInstance(d, dict)
                for chiave in ("name", "description", "body"):
                    self.assertIn(chiave, d, f"manca «{chiave}»: GitHub scarta il modulo")
                self.assertTrue(d["body"], "modulo senza campi")
                for campo in d["body"]:
                    self.assertIn(campo.get("type"), TIPI_AMMESSI,
                                  f"tipo di campo sconosciuto: {campo.get('type')}")

    def test_ogni_modulo_chiede_la_spunta_sui_dati_veri(self):
        """La riga che impedisce a un dato reale di finire su una pagina pubblica."""
        for f in _moduli():
            with self.subTest(modulo=os.path.basename(f)):
                with open(f, encoding="utf-8") as fh:
                    d = yaml.safe_load(fh)
                obbligatorie = [o.get("label", "")
                                for c in d["body"] if c.get("type") == "checkboxes"
                                for o in c.get("attributes", {}).get("options", [])
                                if o.get("required")]
                self.assertTrue(obbligatorie,
                                "nessuna spunta obbligatoria: il modulo lascia passare "
                                "una issue senza la dichiarazione sui dati personali")
                testo = " ".join(obbligatorie).lower()
                self.assertTrue(any(k in testo for k in ("dato personale", "dati personali",
                                                         "inventat", "reale", "veri")),
                                f"la spunta obbligatoria non parla di dati personali: {obbligatorie}")

    def test_le_issue_vuote_sono_spente(self):
        """Senza questo, il modulo si salta con un clic e la spunta non la vede nessuno."""
        cfg = os.path.join(CARTELLA, "config.yml")
        self.assertTrue(os.path.isfile(cfg), "manca config.yml")
        with open(cfg, encoding="utf-8") as fh:
            d = yaml.safe_load(fh)
        self.assertIs(d.get("blank_issues_enabled"), False)

    def test_la_vulnerabilita_ha_un_canale_privato(self):
        """Una falla che lascia dati in chiaro non deve finire in una issue pubblica."""
        cfg = os.path.join(CARTELLA, "config.yml")
        with open(cfg, encoding="utf-8") as fh:
            d = yaml.safe_load(fh)
        testo = str(d.get("contact_links", [])).lower()
        self.assertIn("security", testo,
                      "config.yml non offre un canale privato per le vulnerabilita'")


if __name__ == "__main__":
    unittest.main(verbosity=2)
