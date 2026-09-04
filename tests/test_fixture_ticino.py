# -*- coding: utf-8 -*-
"""Fixture ticinese: frasi sintetiche con i formati CH (AVS, IDI, IBAN CH, NAP,
Cantone, targa, telefono, CHF, mappale RFD, tessera assicurato) passate alla
sola rete regex+checksum. Misura la COPERTURA DEI FORMATI, non la qualita' del
modello su documenti veri: il numero che ne esce ("N casi su N") e' quello
onesto da scrivere accanto al profilo Svizzera, non lo 0,989 del benchmark
italiano. Zero PII reali: valori inventati con checksum ricalcolato.

Ogni riga di tests/fixtures_ticino.jsonl: {"text", "expect": [[tag, valore]],
"absent": [[tag, valore]], "note"}."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "app"))

import detectors as dt  # noqa: E402
import detectors_local as dl  # noqa: E402

dl.install()
FIXTURE = ROOT / "tests" / "fixtures_ticino.jsonl"


def labels(text):
    return {(e["label"], text[e["start"]:e["end"]]) for e in dt.detect_regex(text)}


class TestFixtureTicino(unittest.TestCase):

    def test_fixture(self):
        rows = [json.loads(l) for l in FIXTURE.read_text("utf-8").splitlines() if l.strip()]
        self.assertGreaterEqual(len(rows), 30)
        for r in rows:
            found = labels(r["text"])
            for tag, val in r.get("expect", ()):
                self.assertIn((tag, val), found, f"{r['note']}: {found}")
            for tag, val in r.get("absent", ()):
                self.assertNotIn((tag, val), found, r["note"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
