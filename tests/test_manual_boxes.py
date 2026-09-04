# -*- coding: utf-8 -*-
"""Riquadri manuali (issue #98 punto 2): rettangoli disegnati dall'utente su
firme e timbri, in FRAZIONI 0-1 della pagina come mostrata.

Gira SENZA Tesseract e senza modello: solo PyMuPDF. Verifica le tre promesse:
il contenuto sotto il riquadro sparisce davvero (testo e pixel), le frazioni
mappano dritte anche su pagine ruotate, e il dizionario vuoto e' ammesso solo
in presenza di riquadri.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "app"))

try:
    import fitz  # noqa: E402
except ImportError:  # CI stdlib-only: senza PyMuPDF l'intero modulo si salta
    raise unittest.SkipTest("PyMuPDF non installato") from None

import pdf_export as px  # noqa: E402


def _word_box(doc_bytes, word):
    """(page_number, riquadro-frazioni) della prima occorrenza di `word`,
    misurata nello stesso spazio 'visto' usato dall'anteprima."""
    with fitz.open(stream=doc_bytes, filetype="pdf") as doc:
        for page in doc:
            for w in page.get_text("words"):
                if w[4] == word:
                    W, H = page.rect.width, page.rect.height
                    pad = 2.0
                    return page.number, {
                        "page": page.number,
                        "x0": max(0.0, (w[0] - pad) / W),
                        "y0": max(0.0, (w[1] - pad) / H),
                        "x1": min(1.0, (w[2] + pad) / W),
                        "y1": min(1.0, (w[3] + pad) / H),
                    }
    raise AssertionError(f"parola {word!r} non trovata")


def _text_of(doc_bytes):
    with fitz.open(stream=doc_bytes, filetype="pdf") as doc:
        return "\n".join(p.get_text() for p in doc)


class TestManualBoxes(unittest.TestCase):

    def _make(self, rotation=0):
        doc = fitz.open()
        page = doc.new_page(width=500, height=700)
        page.insert_text((90, 200), "Contratto tra le parti in essere.", fontsize=12)
        page.insert_text((90, 400), "RISERVATO", fontsize=16)
        if rotation:
            page.set_rotation(rotation)
        out = doc.tobytes()
        doc.close()
        return out

    def test_box_removes_text(self):
        pdf = self._make()
        _, box = _word_box(pdf, "RISERVATO")
        out, report = px.redact_pdf(pdf, {}, manual_boxes=[box])
        self.assertEqual(report["manual_boxes"], 1)
        self.assertEqual(report["occurrences"], 0)
        self.assertNotIn("RISERVATO", _text_of(out))
        self.assertIn("Contratto", _text_of(out))       # il resto resta

    def test_box_on_rotated_page(self):
        # le frazioni sono della pagina COME MOSTRATA: con la rotazione devono
        # mappare dritte, senza matrici lato client
        for rot in (90, 180, 270):
            pdf = self._make(rotation=rot)
            _, box = _word_box(pdf, "RISERVATO")
            out, report = px.redact_pdf(pdf, {}, manual_boxes=[box])
            self.assertEqual(report["manual_boxes"], 1, f"rot={rot}")
            self.assertNotIn("RISERVATO", _text_of(out), f"rot={rot}")

    def test_box_erases_image_pixels(self):
        # una "firma" raster: il riquadro deve cancellare i PIXEL, non coprirli
        src = fitz.open()
        sp = src.new_page(width=400, height=300)
        sp.insert_text((150, 150), "FirmaXY", fontsize=20)
        pix = sp.get_pixmap(dpi=150)
        doc = fitz.open()
        page = doc.new_page(width=400, height=300)
        page.insert_image(page.rect, pixmap=pix)
        pdf = doc.tobytes()
        doc.close()
        src.close()

        box = {"page": 0, "x0": 140 / 400, "y0": 120 / 300,
               "x1": 260 / 400, "y1": 165 / 300}
        clip = fitz.Rect(box["x0"] * 400, box["y0"] * 300,
                         box["x1"] * 400, box["y1"] * 300)
        with fitz.open(stream=pdf, filetype="pdf") as d:
            before = d[0].get_pixmap(clip=clip, dpi=150).samples
        out, report = px.redact_pdf(pdf, {}, manual_boxes=[box])
        self.assertEqual(report["manual_boxes"], 1)
        with fitz.open(stream=out, filetype="pdf") as d:
            after = d[0].get_pixmap(clip=clip, dpi=150).samples
        self.assertNotEqual(before, after)

    def test_empty_mapping_without_boxes_fails(self):
        pdf = self._make()
        with self.assertRaises(px.PdfError):
            px.redact_pdf(pdf, {})

    def test_boxes_and_mapping_together(self):
        pdf = self._make()
        _, box = _word_box(pdf, "RISERVATO")
        out, report = px.redact_pdf(pdf, {"[ORG_1]": "parti"}, manual_boxes=[box])
        self.assertEqual(report["manual_boxes"], 1)
        self.assertGreaterEqual(report["occurrences"], 1)
        txt = _text_of(out)
        self.assertNotIn("RISERVATO", txt)
        self.assertNotIn("parti", txt.replace("[ORG_1]", ""))

    def test_box_removes_overlapping_widget(self):
        # l'aspetto di un widget (es. firma digitale, "Digitally signed by...")
        # NON e' content stream: apply_redactions lo lascia e si ridisegna
        # sopra la redazione. Un riquadro che lo copre deve eliminare il campo.
        doc = fitz.open()
        page = doc.new_page(width=500, height=700)
        page.insert_text((90, 100), "Documento con firma.", fontsize=12)
        w = fitz.Widget()
        w.field_name = "Signature1"
        w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        w.field_value = "Digitally signed by MARIO ROSSI"
        w.rect = fitz.Rect(100, 500, 400, 560)
        page.add_widget(w)
        pdf = doc.tobytes()
        doc.close()

        box = {"page": 0, "x0": 90 / 500, "y0": 490 / 700,
               "x1": 410 / 500, "y1": 570 / 700}
        out, report = px.redact_pdf(pdf, {}, manual_boxes=[box])
        self.assertEqual(report["annots_removed"], 1)
        with fitz.open(stream=out, filetype="pdf") as d:
            self.assertEqual(list(d[0].widgets() or []), [])
        self.assertNotIn("MARIO ROSSI", _text_of(out))
        self.assertIn("Documento", _text_of(out))       # il resto resta

    def test_parse_manual_boxes(self):
        # clamp fuori range + scarto dei degeneri (click senza drag)
        raw = ('[{"page":0,"x0":-0.2,"y0":0.1,"x1":0.5,"y1":1.7},'
               ' {"page":1,"x0":0.4,"y0":0.4,"x1":0.401,"y1":0.401}]')
        boxes = px.parse_manual_boxes(raw)
        self.assertEqual(len(boxes), 1)
        self.assertEqual(boxes[0]["x0"], 0.0)
        self.assertEqual(boxes[0]["y1"], 1.0)
        self.assertEqual(px.parse_manual_boxes(None), [])
        self.assertEqual(px.parse_manual_boxes(""), [])
        with self.assertRaises(px.PdfError):
            px.parse_manual_boxes("non-json")
        with self.assertRaises(px.PdfError):
            px.parse_manual_boxes('{"page":0}')          # non e' una lista
        with self.assertRaises(px.PdfError):
            px.parse_manual_boxes('[{"page":0,"x0":"a","y0":0,"x1":1,"y1":1}]')


if __name__ == "__main__":
    unittest.main(verbosity=2)
