# -*- coding: utf-8 -*-
"""
Configurazione host/porta del server Flask (condivisa tra tutti gli entry point).

Risoluzione con precedenza:  CLI args  >  env vars  >  config.json  >  default.

Il file config.json e' condiviso con l'app Tauri (che lo legge/scrive dal lato Rust
e passa host/porta al sidecar via env PII_HOST/PII_PORT):

  Windows:  %LOCALAPPDATA%\\anonimai\\config.json
  Linux:    ~/.local/share/anonimai/config.json
  macOS:    ~/Library/Application Support/anonimai/config.json

Formato:  {"host": "127.0.0.1", "port": 5005}

Il codice di uscita 76 (EX_PROTOCOL) segnala "porta occupata" ed e' riconosciuto
dall'app Tauri per mostrare il form di configurazione nello splash.

Nella stessa directory vivono anche le preferenze di anonimizzazione, prefs.json:

  {"excluded_tags": ["AGE", "GENDER"], "mapping_enabled": true}

E' un file separato di proposito: Tauri riscrive config.json per intero quando si
cambia la porta dallo splash, e sovrascriverebbe qualunque altra chiave.

Chi espone il server in rete puo' chiuderlo con una credenziale:

  PII_AUTH="utente:password"   (oppure --auth sulla riga di comando)

HTTP Basic su ogni rotta tranne /health (sonda degli orchestratori) e /assets.
Sta nell'ambiente e non nei file di configurazione: vedi la sezione in fondo.
"""

import base64
import binascii
import hmac
import json
import os
import socket
import sys
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5005
EXIT_PORT_CONFLICT = 76  # riconosciuto da Tauri (lib.rs) come "porta occupata"


def _config_base() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home()))
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def config_dir() -> Path:
    """Directory di configurazione (platform-specific, coerente con serve.py e Tauri).

    Migrazione una-tantum dal vecchio nome: chi aveva l'app quando si chiamava
    rizzo-pii ha config.json/prefs.json in `rizzo-pii/` — al primo avvio col
    nome nuovo i file si COPIANO in `anonimai/` (copia, non rename: un
    eventuale rollback alla versione vecchia ritrova i suoi). Se la cartella
    nuova esiste gia', la vecchia non si guarda piu'."""
    base = _config_base()
    new = base / "anonimai"
    old = base / "rizzo-pii"
    if not new.exists() and old.is_dir():
        try:
            new.mkdir(parents=True, exist_ok=True)
            for fn in ("config.json", "prefs.json"):
                src = old / fn
                if src.is_file():
                    (new / fn).write_bytes(src.read_bytes())
        except OSError:
            pass                      # senza migrazione si riparte dai default
    return new


def config_path() -> Path:
    return config_dir() / "config.json"


def load_config() -> dict:
    """Legge config.json; ritorna {} se mancante o corrotto."""
    p = config_path()
    if p.exists():
        try:
            return json.loads(p.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_config(host: str, port: int):
    """Scrive config.json (crea la directory se necessario)."""
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(
        json.dumps({"host": host, "port": port}, indent=2), "utf-8"
    )


# --------------------------------------------------------------------------- #
# Preferenze di anonimizzazione (prefs.json, accanto a config.json)
#
#   {"excluded_tags": ["AGE"], "mapping_enabled": true}
#
#   excluded_tags   -> tag rilevati ma NON sostituiti (restano in chiaro)
#   mapping_enabled -> false = niente dizionario placeholder->valore, quindi
#                      l'anonimizzazione e' definitiva e non reversibile
# --------------------------------------------------------------------------- #
PREFS_FILE = "prefs.json"
LEGACY_PREFS_FILE = "tags.json"   # nome usato prima che il file contenesse anche il mapping
DEFAULT_MAPPING_ENABLED = True


def prefs_path() -> Path:
    return config_dir() / PREFS_FILE


def parse_tag_list(value) -> list:
    """Normalizza una lista di tag: accetta stringa CSV o iterabile. -> UPPERCASE, senza duplicati."""
    if value is None:
        return []
    if isinstance(value, str):
        items = value.replace(";", ",").split(",")
    else:
        items = list(value)
    out = []
    for it in items:
        t = str(it).strip().upper()
        if t and t not in out:
            out.append(t)
    return out


def parse_bool(value, default=True) -> bool:
    """Accetta bool, 0/1, "true"/"false"/"on"/"off"/"si"/"no". Altro -> default."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    s = str(value).strip().lower()
    if s in ("1", "true", "yes", "y", "on", "si", "sì"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return default


def _read_prefs_file() -> dict:
    """Contenuto grezzo di prefs.json ({} se manca o e' corrotto)."""
    for p in (prefs_path(), config_dir() / LEGACY_PREFS_FILE):
        if p.exists():
            try:
                data = json.loads(p.read_text("utf-8"))
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, OSError):
                pass
    return {}


def load_prefs() -> dict:
    """Preferenze effettive. Catena: env > prefs.json > default.

    env: PII_EXCLUDE_TAGS="AGE,GENDER"   PII_MAPPING=0|1
    """
    data = _read_prefs_file()
    tags = data.get("excluded_tags")
    mapping = data.get("mapping_enabled", DEFAULT_MAPPING_ENABLED)
    if "PII_EXCLUDE_TAGS" in os.environ:
        tags = os.environ["PII_EXCLUDE_TAGS"]
    if "PII_MAPPING" in os.environ:
        mapping = os.environ["PII_MAPPING"]
    return {
        "excluded_tags": parse_tag_list(tags),
        "mapping_enabled": parse_bool(mapping, DEFAULT_MAPPING_ENABLED),
    }


def save_prefs(excluded_tags=None, mapping_enabled=None) -> dict:
    """Scrive prefs.json unendo le chiavi passate a quelle gia' sul file (i None non toccano nulla)."""
    data = _read_prefs_file()
    if excluded_tags is not None:
        data["excluded_tags"] = parse_tag_list(excluded_tags)
    if mapping_enabled is not None:
        data["mapping_enabled"] = parse_bool(mapping_enabled, DEFAULT_MAPPING_ENABLED)
    data.setdefault("excluded_tags", [])
    data.setdefault("mapping_enabled", DEFAULT_MAPPING_ENABLED)
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / PREFS_FILE).write_text(json.dumps(data, indent=2), "utf-8")
    return data


def resolve(cli_host=None, cli_port=None):
    """Risolve host/porta con la catena: CLI > env > config.json > default.

    Ritorna (host: str, port: int).
    """
    cfg = load_config()
    host = cli_host or os.environ.get("PII_HOST") or cfg.get("host") or DEFAULT_HOST
    port = cli_port or os.environ.get("PII_PORT") or cfg.get("port") or DEFAULT_PORT
    return str(host), int(port)


# --------------------------------------------------------------------------- #
# fork gmesc/anonimai: credenziale per il server esposto in rete
#
# Il server ascolta su 127.0.0.1 e li' non serve nessuna credenziale: chi e' sulla
# macchina e' gia' dentro. Ma chi lo espone (--host 0.0.0.0, Docker su un server
# d'ufficio) offre un SERVIZIO: i documenti degli altri passano da li'. Fino a ieri
# l'unica difesa era un proxy davanti; adesso basta PII_AUTH="utente:password".
#
# HTTP Basic e non un login proprio: nessuna schermata da disegnare, nessuna sessione,
# nessun cookie: la finestra la fa il browser. Non protegge da chi ascolta il traffico
# (Basic viaggia in chiaro): il cifrato lo mette un reverse proxy davanti, ed e' scritto
# nel README. La credenziale vive nell'ambiente del processo, come host e porta: NON in
# config.json (Tauri lo riscrive per intero, invariante 11) e NON in prefs.json (e' in
# chiaro e lo maneggia l'UI).
# --------------------------------------------------------------------------- #
AUTH_ENV = "PII_AUTH"
_LOOPBACK = {"127.0.0.1", "localhost", "::1", "[::1]", "0:0:0:0:0:0:0:1"}


def parse_auth(value):
    """"utente:password" -> (utente, password). None se manca o e' malformata.

    Rifiuta le forme senza due punti, senza utente o senza password: una credenziale
    a meta' e' peggio di nessuna credenziale, perche' fa credere che ci sia una difesa.
    La password puo' contenere i due punti (si divide sul primo).
    """
    if not value:
        return None
    s = str(value).strip()
    if ":" not in s:
        return None
    user, _, pwd = s.partition(":")
    if not user or not pwd:
        return None
    return (user, pwd)


def load_auth(cli_auth=None):
    """Credenziale effettiva. Catena: CLI --auth > env PII_AUTH > nessuna."""
    return parse_auth(cli_auth or os.environ.get(AUTH_ENV))


def check_basic(header, credential) -> bool:
    """True se l'header Authorization corrisponde alla credenziale attesa.

    Confronto a tempo costante (hmac.compare_digest) su entrambi i campi: un
    confronto normale con == esce al primo carattere diverso, e la differenza di
    tempo dice a chi prova quanto e' vicino. Entrambi i confronti si eseguono
    sempre, senza corto circuito, per la stessa ragione.
    """
    if not credential:
        return True                       # nessuna credenziale richiesta
    if not header or not header.startswith("Basic "):
        return False
    try:
        raw = base64.b64decode(header[6:].strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    if ":" not in raw:
        return False
    user, _, pwd = raw.partition(":")
    ok_user = hmac.compare_digest(user, credential[0])
    ok_pwd = hmac.compare_digest(pwd, credential[1])
    return ok_user and ok_pwd


def is_loopback(host) -> bool:
    """True se l'indirizzo serve solo questa macchina.

    0.0.0.0 e :: NON sono loopback: sono il jolly, cioe' tutte le interfacce.
    E' il caso che fa scattare l'avviso all'avvio quando manca la credenziale.
    """
    return str(host or "").strip().lower() in _LOOPBACK


def port_available(host: str, port: int) -> bool:
    """True se la porta e' libera.

    Il bind del solo host non basta: se un altro programma ascolta su 0.0.0.0:PORT,
    il bind su 127.0.0.1:PORT riesce comunque e da quel momento non e' definito chi
    serve le connessioni - l'utente puo' finire sul server dell'altro programma.
    Quindi si prova a legare anche l'indirizzo jolly; se e' occupato si guarda, con
    una connessione, se qualcuno risponde davvero su host:port (potrebbe ascoltare
    su un'altra interfaccia, e allora la nostra e' libera).
    """
    def _bind(addr, riusa):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if riusa:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((addr, port))
                return True
        except OSError:
            return False

    if not _bind(host, True):
        return False
    # il jolly si prova SENZA SO_REUSEADDR: quando ce l'ha anche il socket dell'altro
    # programma (Werkzeug la imposta di default) su Windows il bind riesce lo stesso,
    # ed e' proprio il caso da rilevare.
    if _bind("", False):
        return True
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) != 0
