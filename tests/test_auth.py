# -*- coding: utf-8 -*-
"""Credenziale del server esposto: parsing, confronto Basic, riconoscimento loopback.

Gira SENZA il modello (invariante 4): server_config non importa torch. E' il pezzo
che decide chi entra, quindi e' il pezzo che va provato — l'avviso all'avvio e il
before_request di Flask sono due righe che si guardano a mano.
"""
import base64
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "app"))
import server_config  # noqa: E402


def _basic(user, pwd):
    return "Basic " + base64.b64encode(f"{user}:{pwd}".encode("utf-8")).decode("ascii")


class TestParseAuth(unittest.TestCase):
    def test_forma_valida(self):
        self.assertEqual(server_config.parse_auth("studio:Parola2026"),
                         ("studio", "Parola2026"))

    def test_password_con_due_punti(self):
        # si divide sul PRIMO due punti: la password puo' contenerne altri
        self.assertEqual(server_config.parse_auth("u:a:b:c"), ("u", "a:b:c"))

    def test_spazi_ai_bordi_ignorati(self):
        self.assertEqual(server_config.parse_auth("  u:p  "), ("u", "p"))

    def test_forme_rifiutate(self):
        # una credenziale a meta' e' peggio di nessuna: fa credere a una difesa
        for cattiva in (None, "", "   ", "senzaduepunti", ":password", "utente:", ":"):
            with self.subTest(cattiva=cattiva):
                self.assertIsNone(server_config.parse_auth(cattiva))


class TestLoadAuth(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.pop(server_config.AUTH_ENV, None)

    def tearDown(self):
        os.environ.pop(server_config.AUTH_ENV, None)
        if self._old is not None:
            os.environ[server_config.AUTH_ENV] = self._old

    def test_senza_env_nessuna_credenziale(self):
        self.assertIsNone(server_config.load_auth())

    def test_da_env(self):
        os.environ[server_config.AUTH_ENV] = "u:p"
        self.assertEqual(server_config.load_auth(), ("u", "p"))

    def test_cli_vince_sull_env(self):
        os.environ[server_config.AUTH_ENV] = "env:env"
        self.assertEqual(server_config.load_auth("cli:cli"), ("cli", "cli"))


class TestCheckBasic(unittest.TestCase):
    CRED = ("studio", "Parola2026")

    def test_credenziale_giusta(self):
        self.assertTrue(server_config.check_basic(_basic(*self.CRED), self.CRED))

    def test_password_sbagliata(self):
        self.assertFalse(server_config.check_basic(_basic("studio", "altra"), self.CRED))

    def test_utente_sbagliato(self):
        self.assertFalse(server_config.check_basic(_basic("altro", "Parola2026"), self.CRED))

    def test_header_assente_o_di_altro_tipo(self):
        for h in (None, "", "Bearer abc", "Basic", "Basico " + _basic(*self.CRED)[6:]):
            with self.subTest(h=h):
                self.assertFalse(server_config.check_basic(h, self.CRED))

    def test_base64_rotto_non_solleva(self):
        # input di frontiera: chiunque puo' mandarlo. Deve dare False, non un 500
        for h in ("Basic !!!nonbase64!!!", "Basic " + base64.b64encode(b"\xff\xfe").decode(),
                  "Basic " + base64.b64encode(b"senzaduepunti").decode()):
            with self.subTest(h=h):
                self.assertFalse(server_config.check_basic(h, self.CRED))

    def test_senza_credenziale_configurata_passa_chiunque(self):
        # su 127.0.0.1 non si chiede niente: chi e' sulla macchina e' gia' dentro
        self.assertTrue(server_config.check_basic(None, None))
        self.assertTrue(server_config.check_basic("Basic garbage", None))


class TestIsLoopback(unittest.TestCase):
    def test_solo_questa_macchina(self):
        for h in ("127.0.0.1", "localhost", "LOCALHOST", "::1", "[::1]", " 127.0.0.1 "):
            with self.subTest(h=h):
                self.assertTrue(server_config.is_loopback(h))

    def test_esposto(self):
        # 0.0.0.0 e' il jolly, non il loopback: e' il caso che fa scattare l'avviso
        for h in ("0.0.0.0", "192.168.1.10", "::", "", None):
            with self.subTest(h=h):
                self.assertFalse(server_config.is_loopback(h))


if __name__ == "__main__":
    unittest.main(verbosity=2)
