# -*- coding: utf-8 -*-
"""OCR sui PDF (issue #98 punto 1): scansioni intere e carta intestata come
immagine dentro pagine normali.

Richiede i language data di Tesseract (cartella tessdata): senza, l'intera
suite viene SALTATA — mai rossa per una feature dichiarata opzionale. Per
eseguirla in locale: PII_TESSDATA=/percorso/tessdata python -m pytest tests/test_pdf_ocr.py
(bastano ita/eng .traineddata; PyMuPDF ha Tesseract compilato dentro la wheel).
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

HAVE_OCR = px.ocr_available()


def _render_to_image_page(texts, w=500, h=700):
    """Pagina-SCANSIONE: il testo viene rasterizzato e reinserito come immagine.
    Nessun layer testuale nativo, come un PDF fotografato."""
    src = fitz.open()
    sp = src.new_page(width=w, height=h)
    for (x, y, s, fs) in texts:
        sp.insert_text((x, y), s, fontsize=fs)
    pix = sp.get_pixmap(dpi=200)
    doc = fitz.open()
    page = doc.new_page(width=w, height=h)
    page.insert_image(page.rect, pixmap=pix)
    out = doc.tobytes()
    doc.close()
    src.close()
    return out


def _hybrid_page(native, img_text, w=500, h=700):
    """Pagina IBRIDA: testo nativo nel corpo + 'carta intestata' come immagine
    in testa (il caso studio medico/istituto scolastico)."""
    src = fitz.open()
    sp = src.new_page(width=400, height=90)
    sp.insert_text((20, 40), img_text, fontsize=16)
    pix = sp.get_pixmap(dpi=200)
    doc = fitz.open()
    page = doc.new_page(width=w, height=h)
    page.insert_image(fitz.Rect(50, 40, 450, 130), pixmap=pix)
    page.insert_text((72, 300), native, fontsize=12)
    out = doc.tobytes()
    doc.close()
    src.close()
    return out


def _text_of(doc_bytes):
    with fitz.open(stream=doc_bytes, filetype="pdf") as doc:
        return "\n".join(p.get_text() for p in doc)


@unittest.skipUnless(HAVE_OCR, "tessdata non disponibile (PII_TESSDATA)")
class TestPageTextpage(unittest.TestCase):

    def test_three_modes(self):
        # nativa: niente immagini -> niente OCR
        doc = fitz.open()
        doc.new_page().insert_text((72, 100), "solo testo nativo", fontsize=12)
        with fitz.open(stream=doc.tobytes(), filetype="pdf") as d:
            tp, mode = px.page_textpage(d[0])
        self.assertEqual(mode, "native")
        self.assertIsNone(tp)
        doc.close()

        # scansione -> ocr-full
        # NB: tenere il riferimento alla pagina — d[0] due volte darebbe due
        # oggetti Page e il textpage terrebbe un weakref al primo, morto
        scan = _render_to_image_page([(72, 100, "Il paziente Mario Rossi", 14)])
        with fitz.open(stream=scan, filetype="pdf") as d:
            page = d[0]
            tp, mode = px.page_textpage(page)
            self.assertEqual(mode, "ocr-full")
            self.assertIn("Mario Rossi", page.get_text(textpage=tp))

        # ibrida -> ocr-mixed: si leggono nativo E immagine insieme
        hyb = _hybrid_page("Il contratto decorre dal mese prossimo.",
                           "Studio Medico Bernasconi")
        with fitz.open(stream=hyb, filetype="pdf") as d:
            page = d[0]
            tp, mode = px.page_textpage(page)
            self.assertEqual(mode, "ocr-mixed")
            txt = page.get_text(textpage=tp)
            self.assertIn("contratto", txt)
            self.assertIn("Bernasconi", txt)

    def test_extract_page_text(self):
        scan = _render_to_image_page([(72, 100, "Riferimento pratica 88/2024", 14)])
        with fitz.open(stream=scan, filetype="pdf") as d:
            self.assertIn("88/2024", px.extract_page_text(d[0]))


@unittest.skipUnless(HAVE_OCR, "tessdata non disponibile (PII_TESSDATA)")
class TestScanRedaction(unittest.TestCase):

    def test_scan_redacted_and_verified(self):
        scan = _render_to_image_page([
            (72, 100, "Il paziente Mario Rossi abita a Lugano.", 14),
            (72, 160, "Diagnosi in fase di accertamento.", 12),
        ])
        out, report = px.redact_pdf(scan, {"[FULLNAME_1]": "Mario Rossi"})
        self.assertGreaterEqual(report["occurrences"], 1)
        self.assertEqual(report["ocr_pages"], 1)
        # la verifica dei residui RI-OCRIZZA l'output: deve essere pulita
        self.assertEqual(report["residual"], [])
        txt = _text_of(out)
        # placeholder visibile al posto del valore + layer invisibile ricercabile
        self.assertIn("FULLNAME", txt)
        self.assertNotIn("Mario Rossi", txt)
        self.assertIn("paziente", txt)                   # layer invisibile
        self.assertIn("Diagnosi", txt)

    def test_hybrid_letterhead_redacted(self):
        # l'intestazione-immagine (ORG) e il testo nativo redatti nello stesso giro
        hyb = _hybrid_page("In fede, Maria Colombo.", "Studio Medico Bernasconi")
        out, report = px.redact_pdf(hyb, {
            "[ORG_1]": "Studio Medico Bernasconi",
            "[FULLNAME_1]": "Maria Colombo",
        })
        self.assertEqual(report["ocr_pages"], 1)
        self.assertEqual(report["residual"], [])
        self.assertEqual(report["not_found"], [])
        txt = _text_of(out)
        self.assertNotIn("Bernasconi", txt)
        self.assertNotIn("Colombo", txt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
