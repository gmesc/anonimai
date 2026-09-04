# -*- coding: utf-8 -*-
"""DPI dell'anteprima (issue #92, zoom): il client puo' chiedere la risoluzione
delle pagine, ma solo su una LISTA CHIUSA.

E' input di frontiera come i riquadri manuali: un dpi libero sarebbe la leva per
far renderizzare un A4 a migliaia di dpi dentro un processo che tiene le pagine
in RAM. Gira senza modello e senza Tesseract.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "app"))

try:
    import fitz  # noqa: F401,E402
except ImportError:  # CI stdlib-only: senza PyMuPDF il modulo si salta
    raise unittest.SkipTest("PyMuPDF non installato") from None

import pdf_export as px  # noqa: E402


class TestPreviewDpi(unittest.TestCase):

    def test_valori_ammessi(self):
        for v in px.PREVIEW_DPI_ALLOWED:
            self.assertEqual(px.parse_preview_dpi(v), v)
            self.assertEqual(px.parse_preview_dpi(str(v)), v)   # arriva dalla query string

    def test_default_quando_manca_o_non_e_un_numero(self):
        for raw in (None, "", "abc", "220; DROP", [], {}):
            self.assertEqual(px.parse_preview_dpi(raw), px.PREVIEW_DPI_ALLOWED[0])

    def test_fuori_lista_non_passa(self):
        # il caso che conta: nessun valore inventato raggiunge il renderer
        for raw in (0, -1, 1, 111, 300, 1200, 99999, "2000"):
            self.assertIn(px.parse_preview_dpi(raw), px.PREVIEW_DPI_ALLOWED)

    def test_default_esplicito_rispettato(self):
        # il default viene dal server (di cui ci si fida), non dal client
        self.assertEqual(px.parse_preview_dpi("nonsenso", default=130), 130)


if __name__ == "__main__":
    unittest.main(verbosity=2)
