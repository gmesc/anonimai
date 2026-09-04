# -*- coding: utf-8 -*-
"""Prova STATICA dell'invariante 1: l'app non ha modo di parlare con la rete.

Non misura il traffico (per quello c'e' `src/app/smoke_offline.py` e la sessione
sotto sandbox documentata in docs/VERIFICA-OFFLINE.md): qui si legge il CODICE e
si nega la possibilita' stessa. Se un domani qualcuno aggiunge `import requests`
in src/app/, una fetch verso un dominio, un aggiornamento automatico o una
telemetria, questo test diventa rosso prima della release.

Copre: i moduli Python dell'app, il JS della UI dentro app.py, la UI dello splash
Tauri, il main di Electron, il Cargo.toml del guscio Rust, e il fatto che il
blocco offline di app.py stia PRIMA dell'import di torch/transformers.

Gira senza modello e senza dipendenze (invariante 4)."""

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "src" / "app"

# Moduli di rete che in un'app offline non hanno ragione di esistere.
# `socket` e' l'eccezione motivata: server_config lo usa per il pre-bind check
# della porta (nessuna connessione in uscita), app.py per lo stesso controllo.
NET_MODULES = {"requests", "urllib", "urllib3", "http", "httpx", "aiohttp",
               "websocket", "websockets", "ftplib", "smtplib", "telnetlib",
               "xmlrpc", "socketserver", "paramiko", "boto3", "google",
               "sentry_sdk", "posthog", "analytics", "mixpanel", "segment"}
# `socket` e' ammesso solo dove NON serve a connettersi:
#   server_config.py  -> pre-bind check della porta (bind, non connect)
#   smoke_offline.py  -> lo script che BLOCCA la rete: sostituisce socket.connect
#                        con una versione che lancia se l'indirizzo non e' loopback
SOCKET_ALLOWED = {"server_config.py", "smoke_offline.py"}


def py_files():
    return sorted(p for p in APP_DIR.glob("*.py"))


def const_value(path: Path, name: str):
    """Valore di una costante stringa di modulo, letto dall'AST (i commenti non
    contano). Concatenazioni di letterali incluse."""
    for node in ast.parse(path.read_text("utf-8")).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                return None
    return None


def ui_script(app_py: str) -> str:
    """Il blocco <script> finale di app.py: e' la UI vera e propria."""
    return app_py.split("<script>")[-1].split("</script>")[0]


class TestPythonSenzaRete(unittest.TestCase):

    def test_nessun_import_di_rete(self):
        for f in py_files():
            tree = ast.parse(f.read_text("utf-8"), filename=f.name)
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for n in names:
                    top = n.split(".")[0]
                    if top == "socket":
                        self.assertIn(f.name, SOCKET_ALLOWED,
                                      f"{f.name}: socket ammesso solo per il pre-bind check")
                    else:
                        self.assertNotIn(top, NET_MODULES,
                                         f"{f.name}: import di rete '{n}' (invariante 1)")

    def test_nessuna_url_assoluta_nel_codice_python(self):
        """URL http(s) ammesse solo nei testi della UI (link dei Crediti, aperti
        dal browser di sistema su gesto dell'utente) e nei commenti/docstring,
        mai dentro una chiamata."""
        for f in py_files():
            src = f.read_text("utf-8")
            code = ui_script(src).join(["", ""]) if False else src
            for m in re.finditer(r"https?://[^\s\"'<>)\\]+", code):
                line = code[:m.start()].count("\n") + 1
                ctx = code.splitlines()[line - 1]
                self.assertFalse(
                    re.search(r"\b(get|post|put|urlopen|connect|request)\s*\(", ctx),
                    f"{f.name}:{line}: URL dentro una chiamata -> {ctx.strip()[:90]}")


class TestUiSenzaRete(unittest.TestCase):

    def setUp(self):
        self.js = ui_script((APP_DIR / "app.py").read_text("utf-8"))

    def test_fetch_solo_relative(self):
        for m in re.finditer(r"fetch\(\s*([`'\"])([^`'\"]*)", self.js):
            url = m.group(2)
            self.assertTrue(url.startswith("/"),
                            f"fetch verso un URL non relativo: {url!r}")

    def test_niente_canali_di_uscita(self):
        for bad in ("XMLHttpRequest", "sendBeacon", "EventSource", "new WebSocket",
                    "importScripts", "navigator.connection"):
            self.assertNotIn(bad, self.js, f"canale di rete nella UI: {bad}")

    def test_niente_risorse_esterne(self):
        """src/href assoluti sono ammessi solo su <a target=_blank> (Crediti):
        il click e' un gesto dell'utente e apre il browser di sistema."""
        html = (APP_DIR / "app.py").read_text("utf-8")
        for m in re.finditer(r"(?:src|href)\s*=\s*[\\]*[\"']\s*(https?:)?//([^\"'\\]+)", html):
            ctx = html[max(0, m.start() - 200):m.start()]
            self.assertIn("<a ", ctx.lower(),
                          f"risorsa esterna caricata dalla pagina: {m.group(0)[:80]}")

    def test_csp_vieta_le_connessioni_esterne(self):
        """Il VALORE della costante CSP, non il testo del file: una menzione in un
        commento non deve poter far passare il test (guasto pagato: la prima
        versione cercava la stringa e un commento la teneva verde)."""
        csp = const_value(APP_DIR / "app.py", "CSP")
        self.assertIsNotNone(csp, "manca la costante CSP in app.py")
        for direttiva in ("default-src 'self'", "connect-src 'self'",
                          "object-src 'none'", "base-uri 'none'",
                          "frame-ancestors 'none'"):
            self.assertIn(direttiva, csp, f"CSP senza {direttiva}")
        self.assertNotIn("unsafe-eval", csp)
        # e deve essere davvero applicata a ogni risposta
        src = (APP_DIR / "app.py").read_text("utf-8")
        self.assertRegex(src, r"@app\.after_request\s+def\s+\w+")
        self.assertRegex(src, r"Content-Security-Policy\"\s*,\s*CSP")


class TestOfflinePerCostruzione(unittest.TestCase):

    def test_env_offline_prima_degli_import_pesanti(self):
        """Le variabili devono essere IMPOSTATE (setdefault con quel nome esatto),
        non solo nominate: `HF_HUB_OFFLINE_X` contiene la sottostringa giusta e
        con un assertIn passerebbe. Si leggono dall'AST le coppie del ciclo."""
        src = (APP_DIR / "app.py").read_text("utf-8")
        impostate = set()
        riga_env = None
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Tuple) and len(node.elts) == 2 and all(
                    isinstance(e, ast.Constant) and isinstance(e.value, str)
                    for e in node.elts):
                impostate.add(node.elts[0].value)
                riga_env = node.lineno if riga_env is None else min(riga_env, node.lineno)
            # os.environ.setdefault("X", "1") scritto per esteso
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "setdefault" and node.args
                    and isinstance(node.args[0], ast.Constant)):
                impostate.add(node.args[0].value)
        for var in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE",
                    "HF_HUB_DISABLE_TELEMETRY", "DO_NOT_TRACK"):
            self.assertIn(var, impostate, f"{var} non viene impostata")
        # e l'impostazione deve precedere gli import che leggono quelle variabili
        righe = src.splitlines()
        for mod in ("import torch", "from transformers import"):
            riga_mod = next(i for i, l in enumerate(righe, 1) if l.startswith(mod))
            self.assertLess(riga_env, riga_mod,
                            f"il blocco offline deve precedere '{mod}'")

    def test_nessun_aggiornamento_automatico(self):
        for name in ("tauri/src-tauri/tauri.conf.json", "tauri/src-tauri/Cargo.toml",
                     "electron/main.js", "tauri/package.json"):
            f = ROOT / name
            if f.exists():
                txt = f.read_text("utf-8").lower()
                for bad in ("updater", "autoupdater", "electron-updater"):
                    self.assertNotIn(bad, txt, f"{name}: aggiornamento automatico ({bad})")


class TestGusciSenzaRete(unittest.TestCase):

    def test_rust_senza_client_http(self):
        f = ROOT / "tauri" / "src-tauri" / "Cargo.toml"
        if not f.exists():
            self.skipTest("guscio Tauri assente")
        txt = f.read_text("utf-8").lower()
        for bad in ("reqwest", "hyper", "ureq", "curl", "isahc", "surf"):
            self.assertNotIn(bad, txt, f"Cargo.toml: client HTTP '{bad}'")

    def test_electron_parla_solo_col_backend_locale(self):
        f = ROOT / "electron" / "main.js"
        if not f.exists():
            self.skipTest("guscio Electron assente")
        js = f.read_text("utf-8")
        for m in re.finditer(r"fetch\(\s*([`'\"])([^`'\"]*)", js):
            url = m.group(2)
            self.assertTrue(url.startswith("${URL_APP}") or url.startswith("/")
                            or "127.0.0.1" in url or "localhost" in url,
                            f"electron: fetch non locale -> {url!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
