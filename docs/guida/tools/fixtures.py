# -*- coding: utf-8 -*-
"""Documenti finti per la campagna di screenshot: PII inventate, nessun dato vero."""
import math
from pathlib import Path
import fitz

OUT = Path(__file__).resolve().parent / "fixtures"
OUT.mkdir(exist_ok=True)

def piva_ck(base10):
    s = 0
    for i, c in enumerate(base10):
        d = int(c)
        if i % 2:
            d *= 2
            if d > 9: d -= 9
        s += d
    return base10 + str((10 - s % 10) % 10)

PIVA = piva_ck("1234567890")

BODY = f"""TRIBUNALE ORDINARIO DI MILANO
Sezione Seconda Civile — R.G. 4821/2026

ATTO DI CITAZIONE

Per: Mario Rossi, nato a Milano il 12/06/1985, codice fiscale RSSMRA85H12F205Z,
residente in Via Garibaldi 24, 20121 Milano (MI), rappresentato e difeso
dall'avv. Chiara Bianchi (PEC c.bianchi@pec-studiobianchi.it, tel. +39 02 8765432)
dello Studio Legale Bianchi & Partners S.r.l., partita IVA {PIVA},
con sede in Corso Venezia 8, Milano — www.studiobianchi.it

Contro: Edilnord Costruzioni S.r.l., in persona del legale rappresentante
Giuseppe Verdi, nato il 03/11/1972, con sede in Via Lugano 15, CH-6900 Lugano,
Canton Ticino, n. AVS 756.1234.5678.97.

FATTO

1. In data 14/03/2025, alle ore 15:30, le parti sottoscrivevano il contratto
   d'appalto rep. n. 1234/2025 avente ad oggetto l'immobile sito in Milano,
   identificato al catasto al Foglio 12, particella 345, subalterno 6.

2. Il corrispettivo pattuito ammontava a EUR 128.500,00, da versarsi sul conto
   corrente IBAN IT60X0542811101000000123456 intestato all'appaltatore.

3. A garanzia veniva rilasciata carta di credito n. 4111 1111 1111 1111 e
   indicato quale recapito l'indirizzo m.rossi@studiorossi.it, tel. 333 1234567.

4. Il veicolo aziendale targato AB 123 CD, di proprieta' della convenuta, veniva
   utilizzato per il trasporto dei materiali sul cantiere di Via Roma 7, Monza.
"""

BODY2 = """DIRITTO

5. L'inadempimento della convenuta e' documentato dal verbale di protocollo
   n. 9987/2025 del 02/09/2025, sottoscritto dal geom. Luca Ferrari, teste
   informato dei fatti, residente in Via Dante 3, 20900 Monza (MB).

P.Q.M.

Voglia l'Ill.mo Tribunale adito, disattesa ogni contraria istanza, condannare la
convenuta al pagamento della somma di EUR 128.500,00, oltre interessi e spese.

Milano, 04/09/2026
"""

def firma(page, x, y):
    """Ghirigoro a mano libera + timbro tondo: cio' che nessun modello legge."""
    sh = page.new_shape()
    p = fitz.Point(x, y)
    for i in range(7):
        c1 = fitz.Point(p.x + 12, p.y - 26 + (i % 3) * 6)
        c2 = fitz.Point(p.x + 24, p.y + 20 - (i % 2) * 14)
        q = fitz.Point(p.x + 26, p.y - (4 if i % 2 else -4))
        sh.draw_bezier(p, c1, c2, q)
        p = q
    sh.finish(color=(0.05, 0.05, 0.35), width=1.4)
    sh.commit()
    cx, cy = x + 230, y - 6
    sh2 = page.new_shape()
    sh2.draw_circle(fitz.Point(cx, cy), 34)
    sh2.draw_circle(fitz.Point(cx, cy), 29)
    sh2.finish(color=(0.6, 0.1, 0.1), width=1.2)
    sh2.commit()
    page.insert_text((cx - 26, cy - 4), "STUDIO LEGALE", fontsize=6, color=(0.6, 0.1, 0.1))
    page.insert_text((cx - 24, cy + 5), "BIANCHI & C.", fontsize=6, color=(0.6, 0.1, 0.1))

def testata(page):
    page.draw_rect(fitz.Rect(50, 40, 545, 92), color=(0.45, 0.28, 0.75), width=1.1)
    page.insert_text((62, 62), "STUDIO LEGALE BIANCHI & PARTNERS",
                     fontsize=13, fontname="hebo", color=(0.35, 0.2, 0.6))
    page.insert_text((62, 78), "Corso Venezia 8 — 20121 Milano — c.bianchi@pec-studiobianchi.it",
                     fontsize=8, color=(0.35, 0.35, 0.4))

def scrivi(page, testo, y0=118):
    page.insert_textbox(fitz.Rect(50, y0, 545, 720), testo, fontsize=10.2,
                        fontname="helv", lineheight=1.45)

doc = fitz.open()
p1 = doc.new_page(); testata(p1); scrivi(p1, BODY)
p2 = doc.new_page(); testata(p2); scrivi(p2, BODY2); firma(p2, 90, 400)
doc.save(OUT / "atto_esempio.pdf"); doc.close()

# scansione: la stessa pagina 1 fotografata (solo pixel: serve l'OCR)
src = fitz.open(OUT / "atto_esempio.pdf")
scan = fitz.open()
for i in range(src.page_count):
    pix = src[i].get_pixmap(dpi=120)
    pg = scan.new_page(width=src[i].rect.width, height=src[i].rect.height)
    pg.insert_image(pg.rect, stream=pix.tobytes("jpg", jpg_quality=72))
scan.save(OUT / "scansione_esempio.pdf", deflate=True); scan.close(); src.close()
print("PIVA", PIVA, "->", OUT)
