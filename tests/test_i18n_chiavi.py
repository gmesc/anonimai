# -*- coding: utf-8 -*-
"""Ogni testo dell'UI esiste in ITALIANO e in INGLESE.

L'interfaccia vive dentro app.py e i testi sono due dizionari, `it` e `en`. Quando i
testi crescono (schede nuove, veli, promemoria) il guasto tipico e' una chiave
aggiunta da una parte sola: in quella lingua l'utente vede il vuoto, o il nome della
chiave. Nessuna prova lo pescava — la suite non esegue il JS.

Questo test non interpreta il JavaScript: raccoglie le chiavi DAVVERO usate (data-i18n
nell'HTML, tt('...') e T[L].chiave nel codice) e verifica che ognuna sia definita in
entrambi i blocchi. Gira senza modello e senza browser (invariante 4).
"""
import os
import re
import sys
import unittest

APP = os.path.join(os.path.dirname(__file__), "..", "src", "app", "app.py")


def _page():
    with open(APP, encoding="utf-8") as f:
        src = f.read()
    i = src.index('PAGE = r"""')
    j = src.index('"""', i + 11)
    return src[i + 11:j]


def _blocchi(page):
    """(testo del blocco it, testo del blocco en). Il taglio e' sulle righe ' it:{' / ' en:{'."""
    a = page.index("\n it:{")
    b = page.index("\n en:{")
    fine = page.index("\n};", b)
    return page[a:b], page[b:fine]


def _chiavi_usate(page):
    usate = set()
    for rx in (r'data-i18n(?:-title|-ph)?="([a-z0-9_]+)"',
               r"tt\('([a-z0-9_]+)'\)",
               r"T\[L\]\.([a-z0-9_]+)"):
        usate.update(re.findall(rx, page))
    return usate


def _definita(blocco, chiave):
    # inizio riga oppure dopo una virgola/graffa: evita di trovare "map_on" dentro "map_only"
    return re.search(r"(?:^|[\s,{])" + re.escape(chiave) + r"\s*:", blocco, re.M) is not None


class TestChiaviI18n(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = _page()
        cls.it, cls.en = _blocchi(cls.page)
        cls.usate = _chiavi_usate(cls.page)

    def test_ci_sono_chiavi_da_controllare(self):
        # se il taglio dei blocchi si rompe, il test deve fallire, non passare a vuoto
        self.assertGreater(len(self.usate), 50)
        self.assertGreater(len(self.it), 5000)
        self.assertGreater(len(self.en), 5000)

    def test_ogni_chiave_usata_esiste_in_italiano(self):
        mancanti = sorted(k for k in self.usate if not _definita(self.it, k))
        self.assertEqual(mancanti, [], f"chiavi senza testo italiano: {mancanti}")

    def test_ogni_chiave_usata_esiste_in_inglese(self):
        mancanti = sorted(k for k in self.usate if not _definita(self.en, k))
        self.assertEqual(mancanti, [], f"chiavi senza testo inglese: {mancanti}")

    def test_le_schede_nuove_hanno_entrambe_le_lingue(self):
        # le chiavi introdotte con la scheda Buone abitudini, il promemoria e lo
        # svuotamento per inattivita': quelle che questo test e' nato per proteggere
        for k in ("set_tab_habits", "habits_body", "habits_show_reminder",
                  "lock_title", "lock_body", "lock_never", "lock_ok",
                  "idle_title", "idle_body", "idle_ok", "t_idle_soon",
                  "map_keep_confirm"):
            with self.subTest(chiave=k):
                self.assertTrue(_definita(self.it, k), f"{k} manca in italiano")
                self.assertTrue(_definita(self.en, k), f"{k} manca in inglese")


class TestPromesseCoerenti(unittest.TestCase):
    """I minuti detti all'utente devono essere quelli che il codice applica davvero.

    La scheda Sicurezza dice «7 minuti» e il velo pure: se qualcuno cambia IDLE_MIN
    senza cambiare i testi, l'app promette una cosa e ne fa un'altra. E DOC_TTL lato
    server non puo' essere piu' lungo della promessa, o la frase e' falsa quando il
    browser muore senza riuscire a chiamare DELETE."""

    def setUp(self):
        with open(APP, encoding="utf-8") as f:
            self.src = f.read()

    def test_idle_min_e_sette(self):
        self.assertRegex(self.src, r"const IDLE_MIN=7\b")

    def test_doc_ttl_non_supera_di_troppo_la_promessa(self):
        m = re.search(r"^DOC_TTL = (\d+) \* 60", self.src, re.M)
        self.assertIsNotNone(m)
        minuti = int(m.group(1))
        self.assertLessEqual(minuti, 10,
                             "il server tiene i documenti piu' a lungo di quanto l'app dichiara")


if __name__ == "__main__":
    unittest.main(verbosity=2)
