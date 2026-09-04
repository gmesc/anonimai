# Changelog / note di modifica

Registro delle modifiche significative alla pipeline di training, con motivazione.
Le voci più recenti in alto. (Codice: `src/training/train_pii.py` salvo diverso.)

---

## 2026-09-04 — «in locale» dimostrato invece che dichiarato: CSP, prove anti-egress, catena di fornitura

I tre modi in cui una responsabilità per **dolo** può ricadere sull'autore di un tool offline
sono: dichiarare il falso, lasciare un canale che fa uscire dati, distribuire un binario
manomesso. Tutti e tre erano coperti da promesse (README, invariante 1) e da nessuna prova.

- **Offline per costruzione** (`app.py`, in testa al file): `HF_HUB_OFFLINE`,
  `TRANSFORMERS_OFFLINE`, `HF_HUB_DISABLE_TELEMETRY`, `DO_NOT_TRACK`,
  `HF_HUB_DISABLE_IMPLICIT_TOKEN` con `setdefault` **prima** di importare torch/transformers
  (quelle librerie le leggono all'import). Un download diventa un errore, non una connessione
  silenziosa; la telemetria di Hugging Face è spenta.
- **Intestazioni di sicurezza su ogni risposta** (`@app.after_request`): CSP con
  `connect-src 'self'`, `object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'`, più
  `no-store`, `nosniff`, `no-referrer`, `DENY`. La finestra Tauri punta a un URL http, quindi
  la CSP di `tauri.conf.json` **non** si applica alla pagina: la deve mandare il server. Provato
  nel browser: fetch, WebSocket, sendBeacon e immagini verso l'esterno **bloccati dal motore**,
  `data:`/`blob:` interni funzionanti.
- ⚠️ **`no-store` si impone, non si propone**: `send_file()` mette già un `Cache-Control` e un
  `setdefault` lo lasciava passare. Le PNG di `/doc/<id>/page/N.png` — le pagine del documento,
  PII comprese — erano **cacheabili su disco** dalla WebView. Trovato dalla prova dinamica, non
  a occhio. L'invariante 6 vale anche per la cache del browser.
- **`tests/test_no_egress.py`** (10 prove, senza modello): vieta import di rete, `fetch` non
  relative, `sendBeacon`/`WebSocket`/`XHR`, risorse esterne, updater, client HTTP in Rust, e
  verifica che il blocco offline preceda gli import pesanti. ⚠️ **Due prove, al primo giro,
  erano vacue**: cercavano una sottostringa (`HF_HUB_OFFLINE_X` la conteneva) e trovavano la
  direttiva CSP **in un commento**. Riscritte sull'**AST**. Il metodo: 10 violazioni iniettate
  una per volta, tutte devono far diventare rossa la suite.
- **`tests/test_claims.py`**: lint delle dichiarazioni pubbliche (UI, README, sito, splash,
  TERMS). Vieta «compliant», «certificato», «garantisce», «100% sicuro», e **pretende** che i
  limiti restino scritti e che lo 0,989 sia attribuito al benchmark italiano **accanto** al
  numero. Ha trovato tre metriche non attribuite (badge del README, tabella dei risultati,
  statistica del sito), ora corrette.
- **`src/app/smoke_offline.py`**: `socket.connect` sostituito da una versione che lancia su
  qualunque indirizzo non-loopback, poi 22 endpoint esercitati col modello vero — testo, PDF
  nativo, scansione con OCR, riquadri manuali, anteprime a 110 e 220 dpi. Esito: 22/22, zero
  tentativi di connessione.
- **Catena di fornitura**: `pip-audit` in CI (job dedicato) e nel build Windows
  sull'ambiente che finisce davvero nell'installer; Action GitHub pinnate al **commit**, non al
  tag mobile; `scripts/checksums.sh` per le impronte di `.dmg`/`.AppImage`/`.deb` (l'`.exe` la
  riceve dal workflow). Nessuna vulnerabilità nota nel freeze al 4 settembre 2026.
- **Audit delle superfici**: `/assets` passa ora solo da `send_from_directory` (che sanifica);
  il precedente `os.path.isfile(os.path.join(...))` faceva `stat` su un percorso non
  sanificato. Traversal, metodi non previsti e corpo oltre 50 MB provati: nessuna fuga.
- **`docs/VERIFICA-OFFLINE.md`**: la campagna con i comandi, gli esiti e — soprattutto — le
  **dodici cose che non sono state verificate** (Windows, Tauri, Electron, WebView native,
  Docker, la scadenza attesa a orologio, il checksum della tessera d'assicurato…).

## 2026-09-04 — distribuire senza claim: condizioni d'uso, tagline, banner rete, checksum delle release

Dopo la mappa nLPD/LPDP la domanda era: che cosa espone l'autore di un tool offline? Non il
trattamento (nessun dato lo raggiunge), ma le **dichiarazioni** e i **difetti taciuti**. Quindi:

- **Via «GDPR compliant»** dalla tagline (app, splash Tauri) e badge README/sito riscritto in
  «GDPR / nLPD by design»: «compliant» è un giudizio su un trattamento, non una proprietà del
  software (LCSl). Al suo posto un fatto: «nessun dato esce».
- **`TERMS.md`** (bozza da avvocato, versionata per data) + **scheda «Condizioni»** in Impostazioni +
  **presa visione al primo avvio** per versione (`pii_terms_ack` in localStorage; dentro Tauri =
  per installazione). Non un EULA: tre righe — titolare sei tu, il rilevamento può sbagliare,
  nessuna garanzia. Il Rapporto registra `terms_version_accepted`, `dictionary_persisted`,
  `served_from`.
- **Banner «server esposto»** quando la pagina non arriva da loopback (`location.hostname`, zero
  righe lato server): chi usa un'istanza esposta sa che i suoi documenti passano da un'altra
  macchina e che l'operatore ne risponde. README/compose: esporre = offrire un servizio (+ §13 AGPL).
- **`SECURITY.md`**: come segnalare in privato, tempi, una sola versione supportata, difetti non
  correggibili dichiarati come limite noto. È la definizione operativa di «diligenza».
- **`.sha256` accanto all'installer Windows** nel workflow di release (`Get-FileHash`), istruzione
  di verifica nel README. Il binario manomesso con il nostro nome sopra è il rischio da
  distribuzione più concreto; macOS resta firmato/notarizzato.
- README: frase di posizionamento unica («strumento di supporto, il titolare sei tu, la rilettura
  è tua»), impegno esplicito «nessun aggiornamento automatico, nessuna chiamata di rete», nota ¹
  che attribuisce lo 0,989 al benchmark italiano e il profilo CH alla fixture.
- Non implementabile in codice, e detto: Sagl/RC professionale se si fattura, mai ospitare
  l'app per terzi senza contratto, validazione legale dei testi.

## 2026-09-04 — profilo Ticino completo, privacy by default, rapporto di anonimizzazione (`src/app/`)

Dalla rendicontazione per la scheda su insegnai.ch: la rete regex non vedeva **nessuno** dei
formati svizzeri fuori da AVS/Cantone/NAP/targa — verificato a mano: telefoni `+41`/`091 …`,
importi `CHF`/`Fr.`, IDI/UID, mappali RFD, tessere d'assicurato cadevano tutti sul solo
modello, addestrato sul formato italiano. E la cornice normativa citata nell'app era solo il
GDPR, mentre l'utente ticinese sta sotto **nLPD** (privati) o **LPDP** (enti pubblici).

- **Detector CH aggiunti** (`detectors_local.py`, sempre senza retraining): **IDI/UID**
  `CHE-123.456.789` → `PIVA` con **checksum mod-11** (pesi 5,4,3,2,7,6,5,4; verificato su un
  IDI pubblico), `strict=False` come il CF perché il prefisso `CHE` è inequivocabile; **telefono
  svizzero** 3-2-2 (`+41`, `0041`, `+41 (0)91`, `0xx`) → `TELEPHONENUM`; **importi in franchi**
  con apostrofo delle migliaia e `.–` → `AMOUNT`; **catasto ticinese** `mappale n. 1234 RFD
  Lugano` → `CATASTO` («fondo» solo con `n.` esplicito: è una parola comune); **tessera
  d'assicurato** `80756`+15 cifre → `ID_DOC` senza validatore (nessun checksum garantito, quindi
  niente ✓). Legenda aggiornata con il doppio identificativo anche per PIVA/telefono/importo/catasto.
- ⚠️ **I detector CH vanno in testa a `DETECTORS`, non in coda**: `_merge` ordina con sort
  stabile e a parità di priorità vince chi viene prima. Un AVS che per caso supera anche Luhn
  (1 su 10, es. `756.1000.0000.61`) diventava `CREDITCARDNUMBER`: redatto comunque, ma con
  l'etichetta sbagliata. Test dedicato.
- **Dizionario in `sessionStorage` per default** (art. 7 nLPD, by default): muore con la
  finestra. Prima stava in `localStorage`, cioè su disco in chiaro nel profilo della WebView,
  oltre la sessione. Persistenza solo **opt-in** («💾 ricorda» accanto allo switch,
  `pii_map_persist`); il cambio sposta il dizionario nello store giusto e ripulisce l'altro.
  Un dizionario di una versione precedente in `localStorage` viene ancora letto (nessuna perdita
  silenziosa) e sparisce al primo Pulisci o alla prossima anonimizzazione.
- **TTL dei documenti in RAM** (`DOC_TTL = 30 min`, `_sweep_docs` a ogni accesso + thread
  daemon ogni 60 s): la LRU da sola teneva un PDF dimenticato finché non ne arrivavano altri
  sei. Invariante 6 rafforzato.
- **📋 Rapporto di anonimizzazione** (client-side, `rapporto_anonimizzazione.json`): data,
  SHA-256 dell'input, conteggi per tag e per fonte, tag esclusi, numero di Termini personali,
  residui/saltati e riquadri del PDF, versioni app/modello. **Nessun valore**: si archivia con
  la pratica. Serve alla documentazione richiesta agli enti sotto LPDP e al registro dello studio.
- **Testi**: scheda Sicurezza con la sezione «Cornice legale in Svizzera» (nLPD art. 5/6/7/16-17/22,
  LPDP per gli enti pubblici, art. 321 CP, identificabilità indiretta), IT+EN; «pseudonimizzazione
  = dato personale» ora cita la nLPD accanto al GDPR. Nuovo `docs/CONFORMITA-CH.md`: mappa
  articolo → funzione → cosa resta al titolare, checklist, cosa far validare al consulente.
- **Misura onesta del profilo CH**: `tests/fixtures_ticino.jsonl` (32 frasi sintetiche, checksum
  ricalcolati, zero PII reali) + `tests/test_fixture_ticino.py`. Copre i **formati**, non la
  qualità del modello su atti veri: è il numero da scrivere sulla scheda al posto dello 0,989
  italiano. Suite: 81 test verdi, senza modello.
- Non fatto, e perché: permessi B/C/G/L (categoria semantica, non un formato: Termini
  personali o retraining), UI in FR/DE (Ticino italofono, modello già multilingue), benchmark
  su documenti ticinesi veri (servono i documenti).

## 2026-09-04 — profilo Svizzera/Ticino + Termini personali (`src/app/`)

L'app deve servire anche il sistema svizzero (l'utente lavora su atti ticinesi) e ogni
verticale — scuola, medico, studio legale — ha item suoi da rilevare. Due risposte, entrambe
**senza retraining**: gli identificativi CH hanno un formato (quindi rete regex+checksum), e
gli item specifici di un'installazione sono valori letterali (quindi lista utente).

- **Identificativi CH nei tag esistenti** (`detectors.py`): numero **AVS** → `ID_DOC`
  (regex + **checksum EAN-13**, la tassonomia manda lì ogni numero previdenziale personale);
  **Cantoni** → `PROVINCE` (nomi non ambigui da soli; «Canton(e) X» copre anche Uri, Giura e
  le sigle — mai le sigle nude: «ti» è una parola); **NAP** → `ZIPCODE` (`CH-####` sempre;
  il 4-cifre nudo solo davanti a località capitalizzata, e 19xx/20xx esclusi perché anni —
  al prezzo dei NAP romandi scritti senza `CH-`); **targa svizzera** → `TARGA` (sigla
  cantonale maiuscola + 3-6 cifre). Sempre attivi: additivi e innocui su documenti italiani.
  Legenda con doppio identificativo («CAP / NAP», «Provincia / Cantone»), esempi che passano
  il proprio checksum (lezione della #99: `756.1234.5678.97` è valido).
- **Termini personali** (🏷️ → 📌): lista `{value, tag}` in `prefs.json` (non `config.json`:
  Tauri lo riscrive per intero) — valori che l'utente vuole **sempre** anonimizzati, match
  letterale case-insensitive con confini di parola (stessa disciplina del matching PDF),
  **priorità massima in fusione** (sopra il modello, come il checksum: un termine inserito a
  mano è la dichiarazione più esplicita possibile). Tag libero ammesso (`[PROGETTO_1]`):
  placeholder e colori sono già per-label. Minimo 3 alfanumerici a voce (la trappola dei
  valori corti), tetto 200 voci. `/settings` GET/POST esteso con `custom_terms`.
  La scheda Sicurezza dichiara l'eccezione: la lista vive **in chiaro su disco**, per scelta.
- Prove in `tests/test_svizzera.py` (18 test, senza modello). La strada per categorie
  **semantiche** nuove (retraining con slot+template, come i 5 tag legali IT) resta
  documentata ma non serviva qui: tutto il pacchetto CH è formato o lista chiusa.

## 2026-08-21 — zoom al puntatore sulle anteprime, specchiato fra le due colonne (chiude #92)

L'issue #92 chiedeva lo zoom «per poter leggere chiaramente il testo, e capire cosa è stato
anonimizzato o meno»: il punto non è ingrandire, è **verificare la redazione**. Per questo lo
zoom è unico per le due colonne — si guarda l'originale e il censurato *nello stesso punto*.

- **Zoom al puntatore**: ctrl/⌘ + rotella (che è anche il pinch del trackpad su macOS), più i
  comandi `− %  +` nella testata; doppio click alterna 100%/200%. La rotella nuda resta lo
  scroll, o il documento diventerebbe inscorribile.
- **Un solo stato per due viste**: `ZOOM` si applica come `--z` su entrambe, quindi non possono
  sfasarsi; `matchScroll` ora specchia **anche l'asse orizzontale**, che prima non esisteva.
- **Larghezza, non `transform`**: le pagine crescono cambiando larghezza — barre di scorrimento
  native corrette e riquadri manuali (che sono in frazioni della pagina) ancora al loro posto.
- ⚠️ **Il fattore di scala si misura, non si deduce**: con `k = z/ZOOM` il punto sotto il
  puntatore scivolava di ~7 px per passo, perché padding del contenitore e margini fra le
  pagine non scalano. Usando il rapporto vero fra gli `scrollWidth/Height` prima e dopo il
  reflow la deriva misurata è **0 px**.
- **Nitidezza vera oltre 1,5×**: le pagine visibili si richiedono a 220 dpi
  (`/doc/<id>/page/<n>.png?dpi=220`), precaricate e scambiate a caricamento finito per non far
  lampeggiare la vista. A 2× la pagina passa da ~910 a 1819 px nativi.
- **`parse_preview_dpi` in `pdf_export.py`** (dove sta anche `parse_manual_boxes`, e per la
  stessa ragione: è input di frontiera ed è testabile senza modello): **lista chiusa
  {110, 220}**. Un dpi libero dal client sarebbe la leva per far renderizzare un A4 a migliaia
  di dpi dentro un processo che tiene le pagine in RAM.
- **Tetto sulle pagine ad alto dpi** (`MAX_HIRES_PAGES = 8` per documento): una A4 a 220 dpi è
  1-3 MB e senza tetto un documento lungo gonfierebbe lo store. Verificato in modo osservabile
  sui tempi di risposta: dopo 11 pagine chieste a 220, la prima ri-renderizza (28 ms) mentre
  l'ultima è in cache (0,5 ms).
- **Se il documento è scaduto dalla LRU** le pagine danno 404: ora l'app lo dice una volta
  sola invece di lasciare riquadri bianchi (invariante 5).

## 2026-08-21 — guscio Electron per provare l'app con `npm start` (`electron/`)

Banco di prova desktop che non tocca la catena di distribuzione: `electron/main.js` lancia
`src/app/serve.py` come processo figlio, attende `/health`, punta la finestra sull'app e alla
chiusura ammazza il figlio (un backend orfano terrebbe porta e modello, e al riavvio darebbe
il 76). Radice: `npm install && npm start`.

- **Perche' accanto a Tauri e non al suo posto**: Tauri resta il guscio che produce installer
  firmati col sidecar PyInstaller; questo serve a *vedere l'app in una finestra* senza Rust e
  senza impacchettare — il backend gira dal sorgente con un `.venv`.
- **Stessa grammatica del Rust**: `PII_HOST`/`PII_PORT` passati al figlio, codice d'uscita
  **76** riconosciuto e spiegato nello splash, log del backend indicato all'utente quando il
  processo muore.
- **Python risolto a catena**: `PII_PYTHON` → `.venv` → `venv` → `build_env` → `python3`; se
  non e' eseguibile la finestra dice come creare l'ambiente invece di restare a girare.
- **Link esterni** (repo, Hugging Face nei Crediti) aperti nel browser di sistema
  (`setWindowOpenHandler`): dentro una finestra-app non ci sarebbe modo di tornare indietro.
- Renderer senza Node (`contextIsolation`, niente `nodeIntegration`, niente preload): la pagina
  e' servita da Flask e non ha nulla da chiedere al sistema.
- ⚠️ **Nel velo d'avvio l'emoji non va usata come icona**: `🕵️` scritto come testo lo disegna
  il font di sistema — su macOS l'icona Apple, che non somiglia a quella in topbar (dove il
  glifo passa dal webfont OpenMoji dell'app). Il velo usa quindi lo stesso **PNG OpenMoji**
  (`src/app/assets/detective.png`, reso dall'SVG 1F575). Verificato dentro Electron con una
  cattura vera: immagine decodificata 512×512, non il riquadro vuoto.
- Su macOS **l'icona del Dock** si imposta con `app.dock.setIcon()`: `BrowserWindow.icon` lì
  viene ignorato, e l'app resterebbe con il logo di Electron.

## 2026-08-21 — Scheda Sicurezza, popup d'uso ritardati, via Ctrl+Enter (`src/app/app.py`)

- **Ctrl+Enter rimosso** dall'app, non solo nascosto: via il listener su `#src`, via il
  suggerimento `Ctrl+Enter` nella riga comandi e le regole CSS rimaste orfane. Era una
  scorciatoia mezza rotta — agganciata alla sola casella di testo, quindi muta proprio quando
  si guardava l'anteprima di un PDF.
- **Quarta scheda «Sicurezza»** nelle Impostazioni, con i consigli raccolti in un posto solo:
  rileggere sempre l'output, che cosa significano gli avvisi *residui*/*saltati*, controllare
  i tag lasciati in chiaro, il **dizionario come chiave** (vale quanto l'originale: mai
  allegato insieme, mai in un LLM), pseudonimizzazione vs anonimizzazione definitiva, ciò che
  il testo non copre (firme/timbri → riquadri manuali, scansioni → OCR, scritte verticali),
  quale bottone quando, e il perimetro di rete (`127.0.0.1` vs esposizione).
- **Popup d'uso sui tre bottoni** del risultato (Copia · PDF · Dizionario): compaiono dopo
  **900 ms** di puntatore fermo e spariscono subito, con `transition-delay` in CSS — niente
  timer JS. Un suggerimento che scatta al primo passaggio del mouse è rumore; uno che aspetta
  chi si è fermato a chiedersi «e questo?» è un aiuto. Il popup del dizionario porta
  l'avviso in rosso: contiene tutte le PII in chiaro.
- Tutti i testi nuovi sono chiavi i18n (`sec_body`, `tip_copy`, `tip_pdf`, `tip_dict`): IT e EN.

## 2026-08-21 — Impostazioni a schede, riga comandi unica, layout a tutta finestra (`src/app/app.py`)

- **⚙️ Impostazioni a tre schede** (`.tabs` dei token StudIA): **Server** (host/porta, come
  prima) · **Come funziona** (che cosa fa l'app, perché i dati non escono, come trova le PII,
  che cosa succede dentro il PDF, e — dichiarato — che cosa **non** promette: col dizionario
  attivo è *pseudonimizzazione*, quindi dato personale finché il dizionario esiste) ·
  **Crediti** (progetto originale rizzo-pii di Simone Rizzo, link al repo, pesi e dataset su
  Hugging Face, licenze MIT/AGPL-3.0/CC BY-SA, rimando a `THIRD_PARTY_LICENSES.md`). Entrambi
  i pannelli sono chiavi i18n (`how_body`/`cred_body`), quindi seguono la lingua; la riga
  **Modello** è letta a runtime da `/health`, non scritta a mano.
- **Footer eliminato**: i crediti vivono nelle Impostazioni. La MIT non chiede un credito in
  UI (chiede il LICENSE nelle copie, che resta), e l'attribuzione **OpenMoji CC BY-SA** —
  quella sì obbligatoria — è ora nella scheda Crediti.
- **Una riga sola per i comandi** della card di input: Anonimizza · Pulisci · switch
  Dizionario, tutti alti `--ctl-h` (40px). La spiegazione grigia è diventata il popup di una
  **ⓘ** (hover/focus). Quando la colonna si stringe cede solo l'etichetta (ellissi): switch,
  badge di stato e ⓘ non si tagliano mai. ⚠️ Due trappole pagate qui: `flex:none` nella
  regola originale di `.mapsw` vinceva sulla nuova (la riga sforava la colonna di 32px), e
  `overflow:hidden` sullo switch **ritagliava il popup** — il troncamento va sull'etichetta,
  non sul contenitore che ospita un elemento flottante.
- **Niente cornice attorno all'area di lavoro**: `.app` senza padding, card senza bordo
  proprio; resta **una** linea verticale fra le due colonne e in alto confinano con la topbar.
  Il margine interno resta in `.bd`. In Deanonimizza il callout è a tutta larghezza, separato
  dalle viewport da una linea.

## 2026-08-21 — UI a due modalità sul brand, icona detective, drop full-window (`src/app/app.py`)

Quattro cambi di interazione, tutti nell'UI embedded:

- **Via le schede-passo**: l'app apre in **Anonimizza**; il click sul **brand** (🕵️ in alto a
  sinistra) commuta su **Deanonimizza** (l'ex "Ripristina la risposta") e viceversa. La
  modalità è scritta nella testata: `AnonimAI — <modalità>` (label in teal, i18n it/en).
- **Icona detective al posto delle illustrazioni rizzo-pii**: mascotte eliminate da UI, splash
  Tauri e asset (`src/app/assets/detective.png`, reso dall'SVG OpenMoji `1F575` — stessa
  licenza CC BY-SA già attribuita in footer). Favicon e splash aggiornati; per l'icona
  dell'installer: `npx tauri icon ..\src\app\assets\detective.png` (docs/BUILD.md).
- **Colonne contigue e fluide**: gap 0 con bordo condiviso fra le due viewport (anche nella
  vista Deanonimizza), `.app` senza max-width — le colonne seguono la finestra.
- **Drag&drop su tutta la finestra** (solo in modalità Anonimizza): eliminata la dropzone
  dedicata; un overlay flottante compare quando entra un file (contatore dragenter/leave per
  gli eventi annidati) e il nome del file caricato va nella testata della card. ⚠️ Con la
  dropzone se n'è andato anche il **click-per-scegliere-file**: l'`<input type=file>` resta
  nel DOM (hidden) — se servirà un file picker, riattaccarlo a un bottone è una riga.

## 2026-08-20 — il prodotto si chiama AnonimAI, ovunque

Rinomina completa dell'identità di prodotto: `rizzo-pii` → **AnonimAI** in UI, finestra
Tauri (productName, titoli, splash), installer e artefatti di release futuri
(`AnonimAI-<versione>-Windows-Setup.exe`, `.dmg`, volumi), Docker (immagine/servizio/volume
`anonimai`), landing `docs/index.html`, metadati dei PDF prodotti (`creator`/`producer`),
documentazione.

Il confine della rinomina (deciso, non accidentale):

- **La cartella di configurazione diventa `anonimai`** (`%LOCALAPPDATA%\anonimai`,
  `~/Library/Application Support/anonimai`, `~/.local/share/anonimai`) con **migrazione
  una-tantum** dal vecchio nome: `config.json` e `prefs.json` si **copiano** (non spostano:
  un rollback ritrova i suoi) al primo avvio. La migrazione vive **sia** in
  `server_config.py` **sia** in `lib.rs`: Tauri legge la porta prima di lanciare il sidecar,
  e senza la copia lato Rust un utente con porta personalizzata verrebbe atteso sulla 5005.
- **Non si rinomina ciò che è esterno o storico**: il modello **`rizzo-pii:0.3B`** (repo HF
  `rizzoaiacademy/rizzo-pii-0.3B`, cartelle `models/rizzo-pii-0.3B-v*`, run W&B), gli URL
  GitHub `Rizzo-AI-Academy/rizzo-pii` (issue, badge, release, `cd rizzo-pii` dopo il clone),
  il dataset comunitario HF, le persone e l'org (Simone Rizzo, Rizzo AI Academy), le release
  già pubblicate, il profilo keychain di notarizzazione, l'`identifier` Tauri
  `com.rizzoai.pii-anonymizer` (cambiarlo spezzerebbe l'upgrade delle installazioni esistenti)
  e il nome interno del sidecar `pii-backend`.
- ⚠️ Trappola pagata in corso d'opera: "Indi**rizzo**", "Rende**rizzo**", "nota**rizzo**"
  contengono la sottostringa — la rinomina è fatta per token esatti, mai con un sed cieco.

## 2026-08-20 — l'interfaccia diventa AnonimAI, sugli standard StudIA (`src/app/`)

Restyle completo della UI embedded in `app.py` sul design system StudIA
(`~/.claude/skills/studia-app-layout`): la versione AnonimAI del progetto ha ora la sua
identità visiva. Il funzionamento non cambia — stessi id, stessi endpoint, stessa logica.

Scelte che contano:

- **Token separati dalla pelle**: `src/app/assets/tokens.css` (copiato dalla skill, fonte di
  verità per palette/barre/tema) caricato prima; nel `<style>` embedded resta solo il CSS
  specifico dell'app. Cambiare identità = cambiare i tre accenti nei token.
- **Grammatica StudIA**: zero `border-radius` (eccetto chip-toggle e pallini), bordi 1px,
  ombra solo su hover/flottanti, metadati in maiuscolo, testata = `.topbar.tbar-lg`, testate
  dei riquadri = barre `.tbar`, viste segmentate accese in teal.
- **Ruoli fissi degli accenti**: teal = azione (Anonimizza, viste attive, switch ON);
  giallo = segni dell'utente (i **riquadri manuali** sulle firme, lo switch dizionario OFF);
  blu = riferimento (callout della tab Ripristina); rosso solo per gli errori (toast).
- **Tema chiaro/scuro** (`data-theme` su `<html>`, persistito in `pii_theme`): solo i token
  cambiano; i colori deterministici dei tag hanno una **seconda rampa** per il tema scuro
  (`colors()` in JS), o i chip pastello sarebbero illeggibili sul fondo scuro.
- **OpenMoji self-hosted** (`assets/fonts/OpenMoji-color.woff2`, ~1 MB, `unicode-range` sui
  soli blocchi emoji): icone coerenti su ogni OS, zero rete (l'app resta offline — il default
  globale Noto via CDN qui è vietato). Attribuzione CC BY-SA 4.0 nel footer. Le build
  PyInstaller/Tauri includono già `src/app/assets` per intero: niente da toccare negli spec.
- La scrollbar di pagina **resta visibile** (la skill la nasconde solo perché in StudIA la
  sostituisce il binario di lettura, che qui non esiste).

## 2026-08-20 — OCR per le scansioni + riquadri manuali per firme e timbri (`src/app/`)

Chiude la issue #98 (e i punti 2-3 della #7): l'anonimizzazione ora funziona anche sui **PDF
fotografati/scansionati** e sulle **carte intestate incorporate come immagine** in pagine
normali (il caso studi medici / istituti scolastici), e le **firme/timbri** si oscurano con
riquadri disegnati a mano sull'anteprima.

Scelte che contano:

- **OCR = PyMuPDF, niente nuove dipendenze**: Tesseract è già compilato dentro la wheel — servono
  solo i file `tessdata` (`PII_TESSDATA`/`TESSDATA_PREFIX`/ricerca automatica; lingue
  `PII_OCR_LANGS`, default `ita+eng`). Feature **opzionale con degradazione**: senza tessdata il
  comportamento è identico a prima e i messaggi dicono come abilitarla; `/health` espone `"ocr"`.
  ⚠️ pagata sul campo: la libreria legge **anche l'env `TESSDATA_PREFIX`** e vince sul parametro
  `tessdata=` — l'env viene riallineato alla cartella scelta, o un env sbagliato rompe l'OCR col
  percorso giusto in mano.
- **Tre vie per pagina** (`page_textpage`): nativa (zero costo nuovo), scansione (`full=True`),
  ibrida (`full=False`: OCR delle sole immagini, fuso col testo nativo). Il criterio è la natura
  (immagine ≥ 20 pt), non la posizione: header e footer non sono casi speciali. Tutta la catena a
  valle (indice char-preciso, pattern, redazione) è rimasta **invariata**: cambia solo il textpage.
- **La verifica dei residui ri-OCRizza le pagine toccate**: senza, su una scansione direbbe
  sempre "0 residui" anche con la PII ancora nei pixel — il falso-anonimizzato che il modulo
  esiste per impedire. Costo: un secondo passaggio OCR sulle sole pagine OCR, dichiarato.
- **Layer di testo invisibile** (`render_mode=3`) sulle pagine-scansione redatte: l'output
  diventa ricercabile/utilizzabile dagli LLM (il caso d'uso della issue #7). Le parole che
  coincidono con un valore del dizionario — soprattutto i "saltati" — **non** entrano nel layer:
  diventerebbero testo estraibile, peggio dei soli pixel. Niente metriche pixel-perfect alla
  StudIA: qui serve la ricerca, non la selezione.
- **Riquadri manuali**: frazioni 0-1 della pagina **come mostrata** — lo stesso spazio del PNG
  di anteprima e di `add_redact_annot`, rotazione inclusa, quindi zero geometria lato client.
  Pixel cancellati (`PDF_REDACT_IMAGE_PIXELS`), grafica vettoriale intatta (una redazione in una
  cella non porta via i filetti della tabella). Dizionario vuoto ammesso solo con riquadri: un
  documento con la sola firma da coprire ora si scarica invece di prendere un 422.
- Prove: `tests/test_pdf_ocr.py` (si **salta** senza tessdata, mai rossa per una feature
  opzionale) e `tests/test_manual_boxes.py` (gira ovunque, pagine ruotate incluse). Docker:
  tessdata `ita/eng/osd` scaricati **pinnati** (tessdata_fast 4.1.0) in build, offline a runtime.

## 2026-08-07 — `Dockerfile`: l'app come webapp in un container

Finora l'unico modo di far girare l'app era l'installer desktop o `python src/app/app.py` con
il venv giusto; chi la voleva su una macchina condivisa (workstation dello studio, server
interno) doveva ricostruirsi l'ambiente a mano. Ora c'è un `Dockerfile` alla root:

```bash
docker build -t rizzo-pii .
docker run --rm -p 127.0.0.1:5005:5005 rizzo-pii
```

Scelte che contano:

- **modello dentro l'immagine** (`snapshot_download` da `rizzoaiacademy/rizzo-pii-0.3B` in
  build) e `HF_HUB_OFFLINE=1`/`TRANSFORMERS_OFFLINE=1` a runtime: il container non ha bisogno
  della rete per lavorare, che è l'intero punto del progetto;
- **torch e transformers pinnati** (`torch==2.13.0+cpu`, `transformers==5.14.1`, le versioni con
  cui l'immagine è stata verificata) e presi **dall'indice CPU**: la wheel di default di torch si
  porta dietro ~2,5 GB di CUDA inutili qui;
- **gunicorn, 1 worker e 4 thread**: ogni worker sarebbe una copia del modello (~1,2 GB), e il
  server di sviluppo di Flask non ha timeout; `--timeout 600` perché un PDF lungo su CPU sono
  minuti, non secondi;
- **bind `0.0.0.0` dentro, `127.0.0.1:5005:5005` fuori**: il confine di rete lo mette docker,
  documentato nel README perché un `-p 5005:5005` distratto esporrebbe l'anonimizzatore alla LAN;
- `HEALTHCHECK` su `/health`, che è readiness senza inferenza (503 finché il modello carica).

`Dockerfile.linux` resta quello che era: l'ambiente di **build** dei bundle .deb/AppImage, non
un modo di far girare l'app. Il `.dockerignore` ora riammette `src/app/` (era `*`, pensato per
il contesto vuoto di `Dockerfile.linux`, che infatti non fa nessun `COPY`).

## 2026-08-03 — `_merge()` era quadratica: 100 s su un documento lungo (`app.py`)

Il controllo delle sovrapposizioni confrontava **ogni** candidato con **tutta** la lista già
tenuta, e `analyze()` chiama `_merge()` una volta sull'**intero documento**, non per chunk.
Il costo esplode dopo l'inferenza, quando l'utente crede di aver finito (issue #61):

| entità nel documento | prima | dopo |
|---:|---:|---:|
| 5.000 | 1,14 s | **0,025 s** |
| 20.000 | 21,25 s | **0,181 s** |
| 40.000 | 111,35 s | **0,398 s** |
| 100.000 | non misurata (ore) | **2,08 s** |

Le entità tenute sono per costruzione ordinate e non sovrapposte, quindi un candidato può
accavallarsi solo con i due vicini: una ricerca binaria li trova subito.

Comportamento invariato, verificato confrontando l'output della funzione intera fra vecchia e
nuova implementazione: **60.000 casi casuali** (span sovrapposti, annidati, densi, punteggi
tutti uguali per far contare la stabilità del `sorted`, 64.822 candidati di lunghezza zero) e
**48 casi costruiti** (lista vuota, lunghezza zero dentro e fuori un altro span, candidati
identici, stesso `start`, annidamento nei due ordini, adiacenti, sovrapposti di un carattere)
→ **0 output diversi**.

Non risolve da solo la issue #61: lì il grosso è l'inferenza su CPU. Questo è il pezzo che
resta lento anche dopo.
## 2026-08-02 — "Pulisci" non cancellava il dizionario PII (`src/app/app.py`)

Il bottone **Pulisci** nascondeva la card del dizionario ma lasciava i valori in `MAP` e in
`localStorage['pii_map']`: nomi, CF e IBAN in chiaro restavano sul disco, e dall'interfaccia
non c'era nessun modo di toglierli (`removeItem` non compariva da nessuna parte nel repo).

Non è solo igiene. All'avvio il dizionario della sessione precedente viene ricaricato in `MAP`,
quindi la guardia di `reverse()` — «Nessun dizionario: caricane uno .json» — non scatta mai:
chi riapre l'app e incolla la risposta dell'LLM di oggi **senza** caricare il `.json` si vede
sostituire i valori del caso precedente, con l'esito «Valori ripristinati».

    dizionario rimasto sul disco: {"[FULLNAME_1]": "Mario Rossi", "[IBAN_1]": "IT60X054…"}
    "Il ricorrente [FULLNAME_1] chiede il bonifico su [IBAN_1]."
      ->  "Il ricorrente Mario Rossi chiede il bonifico su IT60X054…"

Ora «Pulisci» azzera `MAP`, rimuove `pii_map` da `localStorage` e ripulisce l'etichetta: è
quello che l'UI già dichiara in italiano e in inglese («il dizionario **di questa sessione**…
se hai chiuso e riaperto l'app, **carica il dizionario .json**»). Nient'altro cambia.
## 2026-08-03 — La porta poteva risultare libera mentre era occupata (`src/app/server_config.py`)

`port_available()` provava a legare solo `host:porta`. Se un altro programma ascolta su
`0.0.0.0:5005`, il bind su `127.0.0.1:5005` riesce lo stesso: il controllo diceva **libera**,
l'app partiva, e da quel momento non è definito chi serve le connessioni — l'utente può
ritrovarsi sul server dell'altro programma. È il sintomo riportato nella #17: «You're speaking
plain HTTP to an SSL-enabled server port».

Ora si prova a legare anche l'indirizzo jolly, **senza** `SO_REUSEADDR`: quando ce l'ha anche
il socket dell'altro programma — Werkzeug la imposta di default, quindi vale per qualsiasi
Flask — su Windows il bind riesce lo stesso, ed è proprio il caso da rilevare. Se il jolly
risulta occupato si guarda, con una connessione, se qualcuno risponde davvero su `host:porta`:
potrebbe ascoltare su un'altra interfaccia, e allora la nostra è libera.

| chi occupa la porta | prima | dopo |
|---|---|---|
| nessuno | libera | libera |
| `127.0.0.1:5005` | occupata | occupata |
| **`0.0.0.0:5005`** | **libera** | **occupata** |
| un'altra interfaccia | libera | libera |

Costo: 0,12 ms a chiamata quando la porta è libera. Vale per i tre entry point (`app.py`,
`serve.py`, `desktop_app.py`), che escono con `EXIT_PORT_CONFLICT`, e per `/port-check`.
## 2026-08-03 — Con host `localhost` l'app desktop non partiva mai (`tauri/src-tauri/src/lib.rs`)

`is_our_backend()` costruiva `"{host}:{port}"` e lo passava a `parse::<SocketAddr>()`, che
accetta **solo IP letterali**: con `host = localhost` (valore che si può scrivere nel form
dello splash o passare in `PII_HOST`) il parse fallisce e la funzione restituisce sempre
`false`. Il backend parte e scrive nel log che è pronto, ma `poll_backend` non lo riconosce:
900 iterazioni × 200 ms → **~180 secondi** di splash, poi «il backend non si è avviato».

Ora l'indirizzo si risolve con `to_socket_addrs()` e si provano **tutti** gli indirizzi
restituiti, non il primo: su Windows `localhost` risolve prima `::1` e poi `127.0.0.1`, e il
backend può ascoltare solo sul secondo. I 500 ms restano il budget dell'**intera chiamata** e
vengono divisi fra gli indirizzi: `poll_backend` la ripete 900 volte, e senza questo l'attesa
prima dell'errore sarebbe passata da ~10 a ~18 minuti.

| host | prima | dopo |
|---|---|---|
| `127.0.0.1` | riconosciuto | riconosciuto |
| **`localhost`** | **mai riconosciuto** | riconosciuto |
| servizio estraneo sulla porta | `false` | `false` |
| nessuno in ascolto | `false` | `false` |

Il controllo che distingue il nostro Flask da un servizio estraneo (`GET /config` → il corpo
contiene `config_path`) resta invariato.
## 2026-07-31 — Span delle entità allineate ai confini di parola (`app.py`)

Il modello etichetta i **sotto-token** e a volte ne copre solo una parte: `' No'` di
`' No' + 'vara'`. Sostituendo la span così com'è, l'`anonymized_text` conservava frammenti
leggibili — `Direzione Provinciale di [CITY_2]vara` — da cui il valore originale è banalmente
ricostruibile. In un anonimizzatore è **peggio di un falso negativo pulito**: l'utente vede il
segnaposto e conclude che il dato sia stato rimosso.

`_merge` ora, dopo aver rifilato gli spazi, **estende ogni span fino a coprire per intero le
parole che tocca**, e fonde le span che l'estensione rende sovrapposte o adiacenti con la stessa
etichetta (prima `foglio 21` → `[CATASTO_1][CATASTO_2]`). L'estensione è sempre nella direzione
sicura: nel dubbio si maschera un carattere in più. Nessun impatto sul training.

Riscontrato su 5 documenti sintetici (perizia CTU, ricorso tributario, relazione dell'organo di
controllo, istanza di composizione negoziata, verbale assembleare): spariscono tutti i frammenti
osservati su `CITY`/`DATE`/`DOCID`/`CATASTO`/`ORG`/`TARGA`, le PII dirette restano mascherate
23/23. Resta fuori portata il caso del richiamo parziale su entità multi-parola
(`Guardia di Finanza` → `Guardia di [ORG_2]`), che è un problema del modello, non della
sostituzione. Rif. issue #11.
## 2026-08-03 - Rete regex: i formati con cui gli identificativi sono stampati

La rete regex+checksum copriva la **forma compatta** degli identificativi ma non quella
**stampata sui documenti**, e i due insiemi non coincidono. Un IBAN su una fattura o su una
carta intestata è scritto a gruppi di quattro (`IT60 X054 2811 …`), un codice fiscale può
essere **omocodico** (le cifre sostituite da lettere quando due contribuenti collidono), una
carta è separata anche da punti, un telefono anche da trattini. Nessuno di questi veniva
rilevato. I **validatori erano già corretti** su tutti quei valori: `iban_ok` normalizza gli
spazi come prima cosa, `cf_ok` calcola l'omocodia, `luhn_ok` scarta i non-numeri. Erano le
regex a non passargli mai un caso con i separatori, e su IBAN/PIVA/carta `strict=True`
significa che **non esiste fallback**: senza checksum il valore resta in chiaro.

Le regex ora accettano i separatori che i validatori già normalizzavano. Sull'IBAN i gruppi
dopo il primo devono contenere almeno una cifra, altrimenti il match ingloberebbe la parola
successiva e il mod-97 farebbe cadere tutto; `iban_ok` normalizza ora **gli stessi**
separatori che la regex ammette, altrimenti il resto non servirebbe a niente. Il CF omocodico
è una **voce a parte** con `strict=True`, non un allargamento della voce esistente: quella è
`strict=False` e redige sulla sola forma, e sette posizioni che accettano lettere sarebbero
troppo generiche per fidarsi. Sulla carta il match termina ora per forza su una cifra, così il
punto di fine frase non entra nel placeholder.

La rete è stata spostata in **`src/app/detectors.py`**, stesso principio già applicato a
`pdf_export.py`: nessun import di `torch`/`transformers`/`fitz`, quindi è verificabile in
isolamento. Prima non lo era, perché importare `app.py` carica il modello. `app.py` ri-esporta
i nomi, il comportamento pubblico non cambia. Aggiunti `tests/test_detector_formats.py`
(39 casi, valori sintetici) e una **CI** che esegue `python -m unittest discover tests` senza
installare nulla. Su 200.000 documenti di `generate_synthetic_pii.py` le entità già rilevate
restano identiche e le rilevazioni su span non-PII non aumentano; riformattando gli stessi
identificativi come su un documento vero si passa da 0 a 7.830 IBAN, 24.304 CF e 16.070
telefoni.

Il costo è che i due separatori aggiunti ereditano l'esposizione che gli altri avevano già,
e non di più: una sequenza di 13-19 cifre separate da punti diventa candidata carta e supera
Luhn per caso in circa un caso su dieci (misurato: 493 su 5.000, contro 488 con lo spazio e
480 col trattino, invariati); un numero amministrativo scritto `0521-123456` viene letto come
telefono, esattamente come già accadeva per `0521.123456` e `0521 123456`. Nessun impatto sul
training e nessuna modifica alla tassonomia.
## 2026-08-03 — La targa scritta col trattino restava in chiaro (`app.py`)

Il detector TARGA ammetteva come separatore **solo lo spazio** (`\s?`), quindi `AB-123-CD` —
la forma dei moduli, dei gestionali e degli export — non veniva vista dalla regex. Senza la
rete regex resta il solo modello, che su quella forma sbaglia i confini:

    HK-105-NS  ->  "...ha registrato HK-[TARGA_1]0[TARGA_2]-[TARGA_3] alle ore..."

Il documento resta insieme **leggibile** (la coppia di lettere sopravvive) e **non
ripristinabile** (il dizionario non ricompone la targa).

Su 120 documenti con targa col trattino, contesti presi dallo stress test (`analyze()`,
modello `rizzo-pii-0.3B`): **8 targhe intere in chiaro e 20 sbriciolate come sopra** — il
23% — contro **0 e 0** dopo la modifica. Le forme `AB123CD` e `AB 123 CD` erano e restano a 0.

Con `src/training/evaluate_targa_stress.py` sullo stress test (300 righe, 200 targhe,
tre varianti identiche tranne la forma), modello+regex:

| forma | prima | dopo |
|---|---:|---:|
| `AB123CD` | R 1,000 · F1 0,800 | invariata |
| `AB 123 CD` | R 1,000 · F1 0,800 | invariata |
| **`AB-123-CD`** | **R 0,280 · F1 0,165** | **R 1,000 · F1 0,800** |
| mix delle tre (come il baseline) | R 0,910 · P 0,593 · F1 0,718 | **R 1,000 · P 0,667 · F1 0,800** |

Sale anche la precisione, perché le span sbagliate del modello vengono sostituite da quella
esatta della regex.

Falsi positivi: **0 match nuovi** su 120.911 testi reali di Ai4Privacy (tutte le lingue) e su
100.000 atti legali sintetici senza targa; 0 entità di altri tag toccate su 20.000 documenti;
costo di scansione invariato. Sullo stress test i documenti con falso positivo restano
100/100 sul mix e sulle forme compatta e a gruppi; sulla variante tutta col trattino passano
da 70/100 a 100/100, perché i codici a forma di targa col trattino ora vengono redatti come
già oggi lo sono quelli compatti (`PR450AB`). La regex non distingue una targa da un codice
che ne ha la forma in nessuna delle due scritture, e per un anonimizzatore sovra-redigere è
la direzione sicura.

Limite: `\b` tratta il trattino come confine, quindi una forma di targa **dentro** un codice
più lungo col trattino (`PROT-2024-AB-123-CD-XY`) viene ritagliata. Nei 120.911 testi reali
non se ne trova nessuna.
## 2026-08-03 — Codice fiscale omocodico: riconosciuto dalla rete regex, prodotto dal sintetico

Un codice fiscale **omocodico** finiva in chiaro nel testo anonimizzato.

Quando due persone otterrebbero lo stesso codice, l'Agenzia delle Entrate ne differenzia uno
sostituendo le cifre con una lettera a partire da destra (`0=L 1=M 2=N 3=P 4=Q 5=R 6=S 7=T 8=U
9=V`) e ricalcolando il carattere di controllo. Quello che ne esce è un codice fiscale valido, e
sui documenti compare come qualsiasi altro. In Italia i casi sono circa 24.000, con circa 1.400
nuovi ogni anno, concentrati proprio negli atti anagrafici e fiscali.

Il detector `CF` pretendeva cifre in posizione fissa
(`[A-Za-z]{6}\d{2}[A-Za-z]\d{2}[A-Za-z]\d{3}[A-Za-z]`), quindi un codice omocodico non diventava
nemmeno candidato. `cf_ok()` lo avrebbe validato senza modifiche, ma non veniva mai chiamato.

**1. Detector** (`app.py`). Una seconda voce `CF` in `DETECTORS` accetta `[\dLMNPQRSTUV]` nelle
sette posizioni numeriche. È l'unica voce `CF` con `strict=True`: sulla forma ordinaria si continua
a redigere anche quando il checksum fallisce (comportamento invariato), mentre la forma allargata da
sola non basta a decidere, perché una parola di sedici lettere può combaciare. Lì si redige solo con
il checksum valido.

**2. Sintetico** (`generate_synthetic_pii.py`). `codice_fiscale()` accetta `omocodia=n`, cioè quante
cifre sostituire, e `cf_piece()` ne produce una quota (`OMOCODIA_RATE = 0.05`). La quota non imita
la frequenza reale: a quella frequenza il modello non ne incontrerebbe nessuno. Il carattere di
controllo si calcola dopo la sostituzione, come fa l'Agenzia.

Il punto cieco stava anche a monte del detector: il generatore non aveva mai prodotto un codice
omocodico, quindi il training non ne conteneva e nessun benchmark del progetto poteva accorgersene.
Il `CF` 567/567 della valutazione indipendente in #18 è misurato su una distribuzione che esclude il
caso che fallisce.

**3. Test** (`tests/test_cf_omocodia.py`). Dieci test senza dipendenze esterne, che coprono le sette
profondità di sostituzione, l'ordine da destra, la tabella di conversione e il fatto che la forma
ordinaria si comporti esattamente come prima. Il checksum è riverificato da un'implementazione
scritta nel test e non importata dal generatore, altrimenti direbbe solo che il generatore concorda
con se stesso. I detector vengono letti da `app.py` con `ast` invece che importati: `app.py`
costruisce la pipeline del modello a import-time, e importarlo vorrebbe dire scaricare i pesi per
provare una regex.
## 2026-08-03 — Augment: il secondo frammento cadeva dentro il primo (`augment_real_pii.py`)

`augment()` ricalcolava i confini di frase **dopo ogni inserimento**. Ma `sentence_boundaries()`
considera confine ogni `.` o `;` etichettato `O`, e i frammenti ne contengono: il punto di
`P.IVA`, di `prot. n.`, di `C.F.`. Così il secondo frammento veniva inserito **dentro** il
primo, spezzandolo:

    frammento: 'R . G . n . 15592 / 2018'
    risultato: '... settembre 6º , 1961 R . G . n . IBAN IT31A9653013434814655221101 15592 / 2018'

Le etichette BIO restano valide — l'entità non viene tagliata — ma il contesto sì: il modello
vede «P.» seguito da un IBAN e impara l'associazione sbagliata, proprio sui tag che l'augment
serve a insegnare.

Ora le posizioni si scelgono **una volta sola** sul testo originale e si inserisce da destra a
sinistra, così gli indici già scelti restano validi.

Misurato su 40000 righe generate dalle frasi reali italiane di Ai4Privacy, verificando che i
token di ogni frammento inserito restino contigui nella riga prodotta:

| | prima | dopo |
|---|---:|---:|
| frammenti spezzati, k=2 | 9,87% | **0** |
| frammenti spezzati, k=3 | 14,04% | **0** |
| righe con almeno un frammento spezzato (`--max-inject 2`, il default) | 9,67% | **0** |

Numero di frammenti inseriti, lunghezze e validità BIO invariati (0 anomalie). Per avere
effetto va rigenerato l'augment: `python src/data_pipeline/augment_real_pii.py -n 40000`.
## 2026-08-03 — I sintetici scrivevano il nome in un ordine solo (issue #40)

`full_name()` e `role()` producevano **sempre** `Nome Cognome`: su 20.000 chiamate, 100%.
Ma negli atti, nei moduli e nelle intestazioni il nome si scrive anche `Cognome Nome`
(«Egr. Rossi Mario»), e il modello quell'ordine non lo ha mai visto.

Effetto misurato su `rizzo-pii-0.3B` con `analyze()`, stessi nomi e stesse frasi, cambiato
solo l'ordine — «in chiaro» = almeno metà del nome ancora leggibile dopo l'anonimizzazione:

| | `Mario Rossi` | `Rossi Mario` |
|---|---:|---:|
| frasi con appellativo (`Egr.`, `Spett.le`, `Gentile`) | 2,5% (8/320) | **27,8% (89/320)** |
| frasi senza appellativo | 0,0% (0/640) | **4,2% (27/640)** |

    'Egr. Coppola Dario'   ->  'Egr. Coppola [FULLNAME_1],'
    'Brambilla Ilaria'     ->  'Brambilla [FULLNAME_1], residente in [STREET_1]...'

Ora il 30% dei nomi sintetici esce in ordine invertito (`INVERTED_NAME_P`), con le label
`SURNAME`/`GIVENNAME` scambiate di conseguenza — la tassonomia non cambia, `normalize_labels()`
li fonde in `FULLNAME` in entrambi i casi. Non 50%: nella prosa l'ordine diretto resta il più
frequente, l'inverso domina solo in intestazioni ed elenchi.

Verificato sul generatore: 70,3% / 29,7% su 20.000 nomi, 0 label scambiate su 5.000, e su
20.000 documenti 0 sequenze BIO non valide e 0 offset sbagliati. **Per avere effetto serve
rigenerare i sintetici e riaddestrare** (come per la fix `PROVINCE`):

```powershell
python src/data_pipeline/generate_synthetic_pii.py -n 200000 --out dataset/synthetic/synthetic_pii_it_200k.jsonl
python src/training/train_pii.py --type full
```
## 2026-07-31 — Detector regex DATE e DOCID nell'app (niente più frammentazione)

Il modello da solo frammentava date e numeri di registro in più span, lasciando
**caratteri in chiaro** nel testo anonimizzato (es. `12/06/2025` → `[DATE_1][DATE_2]2[DATE_3]`,
`R.G. 1234/2024` → quattro frammenti + `4` finale scoperta) e corrompendo il ripristino
(`1234/202` al posto di `1234/2024`). Aggiunti in `src/app/app.py` due detector
deterministici alla rete regex+checksum (stesso meccanismo di CF/IBAN, priorità sul modello):

- **`DATE`**: date numeriche (`12/06/2025`, `12-06-25`, `12.06.2025`) e letterali (`12 giugno 2025`)
- **`DOCID`**: `R.G.`/`RG`/`R.G.N.R.`, `Prot.`/`protocollo`, `Rep.`/`repertorio` + numero (con anno opzionale)

Nessun impatto su training e pipeline dati.
## 2026-08-03 — Fix allineamento colonne su paste Excel/TSV (issue #54)

Incollando un intervallo multi-riga/multi-colonna da Excel, il testo anonimizzato
usciva con celle "sfasate": frammenti di placeholder mescolati a pezzi del valore
originale (`VER[FULLNAME_2]`, `[DATE_1][DATE_2]26`, `13[BUILDINGNUM_1]2`).

**Causa**: non era l'ordine di sostituzione dei placeholder (`analyze()` ricostruiva
già il testo in un unico pass sugli offset). Su TSV densi il modello spezza spesso
le entità a metà token; il merge greedy teneva i frammenti non sovrapposti e la
sostituzione lasciava residui nella stessa cella.

**Fix** (`src/app/app.py`): prima del merge, `_snap_to_token_spans()` espande gli
span `source=modello` ai confini dei token `\S+` che sovrappongono. Frammenti nello
stesso token collassano e ne resta uno. La rete regex non viene snappata (span già
precisi; allargarli a `\S+` ingloberebbe punteggiatura, es. la virgola dopo un CF).
Regressione in `tests/test_tsv_anonymize.py` con l'esempio dell'issue. Nessun impatto
sul training.
## 2026-07-30 — I template si possono scrivere con un LLM **locale** (senza chiave Gemini)

Per contribuire dati serviva una chiave Google, e i prompt uscivano dalla macchina: attrito
d'ingresso per chi vuole aiutare, e una stonatura in un progetto il cui punto è **non mandare
niente a terzi**. `llm_template_bank.py` ha ora un secondo backend: se è impostata
**`LLM_BASE_URL`** (endpoint OpenAI-compatibile — llama.cpp server, Ollama, vLLM, LM Studio) i
template li scrive quel modello, in locale. Senza la variabile nulla cambia: si usa Gemini
esattamente come prima.

`call_llm()` smista tra i due backend; `backend_name()` lo stampa nei log; `have_backend()`
sostituisce il controllo della sola `GEMINI_API_KEY` in `contribute_dataset.py`, che ora spiega
entrambe le strade. Le guardie sui template (segnaposto ammessi, nomi inline) sono le stesse:
il testo di un modello locale passa gli stessi controlli.

**Dettaglio non ovvio, costato una diagnosi:** un modello *reasoning* servito in locale può
mettere **tutto** l'output in `reasoning_content` e restituire `content` **vuoto** (visto con
gemma-4-12B su llama.cpp: 175 s di pensiero, zero testo). La richiesta manda quindi
`chat_template_kwargs: {enable_thinking: false}` e, per sicurezza, accetta `reasoning_content`
come ripiego.

**Nuova guardia `non_latin_char()`** in `clean_and_validate()`: un modello locale quantizzato può
infilare un **ideogramma** in mezzo alla prosa italiana (`"oltre a槽 interessi"`), e il template
passava tutti i controlli esistenti — il carattere finiva poi in **ogni** esempio generato da quel
template (visto: 87 righe su 5.000 da un solo template). Ora un template con caratteri non latini
viene scartato. La guardia è utile anche col backend Gemini, ma è coi modelli locali che il caso
si presenta davvero.
## 2026-07-30 — `contribute_dataset.py`: scrittura incrementale invece di accumulo in RAM

`generate()` accumulava **tutte** le righe in una lista e solo alla fine `write_local()` le
scriveva. Con `MAX_N = 200_000` e template lunghi — documenti interi, non frasi: ~4-5 KB per riga —
significa ~1 GB di JSON come oggetti Python, cioè diversi GB di heap, prima che venga scritto il
primo byte. Su una macchina che stia già facendo altro (nel caso reale: server LLM locali che
occupavano 22 GB su 30) il processo va in swap o viene ucciso, e si perde tutta la generazione.

Ora le righe vengono scritte **mano a mano** su un file temporaneo, rinominato alla fine col numero
di righe valide (che si conosce solo al termine, perché il self-check può scartarne). La memoria
resta costante qualunque sia `--n`: misurato su 20.000 righe, **picco 25 MB** invece di ~1 GB, in
2,3 s. Progresso stampato ogni 25.000 righe. `write_local()` è stata rimossa: non serviva più.

Nessun cambio di formato né di interfaccia: stessi argomenti, stesso nome di file finale.
## 2026-07-30 — Una label sconosciuta in un contributo aggiunge una classe al modello, in silenzio

`train_pii.py` costruisce la tassonomia **dai dati**: `label_set` è l'unione delle label presenti
in train + validation e `num_labels = len(label_list)` (righe 315-319). `normalize_labels()` lascia
passare invariata ogni label che non sia in `TAG_MAP` (`TAG_MAP.get(l[2:], l[2:])`).

Conseguenza: un file contribuito che contenga una label non prevista — anche solo un errore di
battitura, `CREDITCARD` invece di `CREDITCARDNUMBER`, `FULLNAM` invece di `FULLNAME` — **non produce
alcun errore**. Diventa una classe nuova della testa di classificazione, con dati di training e zero
support in validation: invisibile nelle metriche, e le percentuali per-tag pubblicate non sono più
confrontabili coi run precedenti. Un cambio di tassonomia può quindi avvenire come effetto
collaterale di un upload, mentre `docs/TASSONOMIA_TAG.md` e `CONTRIBUTING.md` lo descrivono
giustamente come una decisione deliberata (si edita solo `TAG_MAP`/`DROP_TYPES`).

`contribute_dataset.py` ora rifiuta le righe con label fuori dai **22 tag finali** o dai tag grezzi
che `TAG_MAP` sa rimappare, controllando sia `entities` sia `bio_labels`. Il messaggio d'errore
rimanda a `docs/TASSONOMIA_TAG.md`. Chi vuole davvero proporre un tag nuovo apre una PR sul codice,
che è dove la decisione va discussa: cambia la dimensione della testa, impone un riaddestramento e
invalida il confronto con le metriche pubblicate.

---

## 2026-07-30 — Forme nuove sotto `DOCID`: CIG, CUP, polizza, matricola (nessun tag nuovo)

Allargando i tipi di documento oltre gli atti civili compaiono identificativi che il modello non
ha **mai** visto: il **CIG** e il **CUP** di un appalto, il numero di **polizza** in un sinistro, la
**matricola INPS** in un rapporto di lavoro.

Non servono tag nuovi, e questa è la parte importante: identificano una *procedura*, un *contratto*
o una *posizione* — non l'identità di una persona — quindi hanno la stessa politica di mascheramento
di `DOCID`, su cui `TAG_MAP` li rimappa al caricamento. Nessun cambio di `num_labels`, nessun
riaddestramento imposto, metriche pubblicate ancora confrontabili. Il numero previdenziale
**personale** resta invece su `ID_DOC` via `SOCIALNUM`: è un documento della persona, non un codice
di procedura.

Quello che cambia è la **forma**, ed è il punto: oggi `DOCID` conosce solo `NNNN/AAAA` e cifre nude.
Un CIG è alfanumerico a 10 caratteri (`9MUGDORPHV`), un CUP a 15, una polizza ha spesso lettere e
barre (`AB/1234567`), una matricola 10 cifre. Sono grafie che in produzione oggi passerebbero
inosservate. Aggiunti i quattro generatori, gli slot in `ALLOWED_SLOTS`/`SLOT_HINTS` e 5 template
built-in (procedura aperta, denuncia di sinistro, comunicazione di assunzione, reclamo su polizza,
determina a contrarre).

Questa voce dipende dalla validazione della tassonomia (voce sotto): le quattro label grezze vanno
aggiunte all'insieme ammesso, altrimenti il validatore le rifiuta — che è esattamente il
comportamento desiderato per una label non prevista.
## 2026-08-01 — Banca template offline (+60 template, senza Gemini)

Nuovi script `author_templates.py` e `author_templates2.py` (root del repo): scrivono
template legali italiani con **soli segnaposto** `{SLOT}` (nessuna PII reale), seguendo il
principio *"LLM autore, codice etichettatore"*. I template sono validati con la **guardia del
repo** (`llm_template_bank.clean_and_validate` + slot ∈ `generate_synthetic_pii.SLOTS`, niente
nomi inline) e accodati a `dataset/synthetic/legal_templates.json`.

Motivazione: consentono di **arricchire il pool offline da 25 a 85 template senza
`GEMINI_API_KEY`**, aumentando la varietà strutturale (incl. slot lista `NAMELIST`/`ORGLIST`/
`MIXEDLIST` e `PROVINCE`) per mitigare l'overfit strutturale sui tag IT-legali rari
(`CATASTO`/`DOCID`/`CF`/`TARGA`). Complementare al percorso Gemini raccomandato in
`CONTRIBUTING.md`, non sostitutivo. Nessun impatto sul training.

---

## 2026-06-30 — Porta del backend 5000 → 5005 (conflitto AirPlay su macOS)

Gli utenti macOS vedevano una **pagina bianca**: la porta **5000** è occupata di default
dall'**AirPlay Receiver** (ControlCenter), quindi il WebView Tauri si collegava al servizio
sbagliato. Backend spostato su **5005** (`app.py`, `serve.py`, `desktop_app.py` con default
`PII_PORT=5005`; `lib.rs` `ADDR`/`URL` aggiornati). Override sempre possibile con la env
`PII_PORT`. Nessun impatto sul training. Richiede rebuild/ri-notarizzazione del bundle macOS.

---

## 2026-06-28 — App di anonimizzazione: revisione completa + app desktop Tauri

Riscrittura dell'app locale (`src/app/`) e nuovo packaging desktop. Nessun impatto su training.

**1. Anonimizzazione reversibile** (`app.py`). Ogni PII riceve un **ID univoco** (`[FULLNAME_1]`,
`[IBAN_1]`…); valori identici condividono lo stesso ID → l'LLM resta coerente e il **reverse è 1:1**.
Si genera un **dizionario locale** `{placeholder → valore}` scaricabile in `.json`; nuovo tab
**"Ripristina"** che rimette i valori veri nella risposta dell'LLM (matching tollerante a parentesi
alterate / grassetto markdown). Tutto in locale.

**2. Rete regex + checksum** a supporto del modello (`detect_regex` + `_merge`). Detector per
EMAIL/TELEFONO/IBAN/CF/PIVA/carta/importo/targa. IBAN/PIVA/carta richiedono il **checksum valido**
(mod-97 / Luhn) per non avere falsi positivi; il CF si redige sulla sola forma (molto specifica) e
prende il ✓ solo se il checksum passa. Priorità in caso di sovrapposizione: **checksum-valido ›
regex › modello** (risolve la frammentazione di CF/IBAN del modello).

**3. UI rifatta** (tema chiaro, flusso a 2 step, highlight a colori per tag, hover col valore
originale, legenda cliccabile, drag&drop PDF). **Fix layout**: altezza fissa a finestra → lo scroll
avviene **dentro la textarea e l'anteprima**, non sulla pagina.

**4. Mascotte** (il riccio): logo header + favicon (`mascot_shield`) ed empty state (`mascot_doc`),
serviti da `/assets/` con fallback emoji. Asset in `src/app/assets/`.

**5. App desktop Tauri** (`tauri/`). Architettura **sidecar**: il backend Python/Flask
(`serve.py`, headless) è impacchettato con PyInstaller (`build_sidecar.spec`, CPU, ~1,8 GB col
modello) in `tauri/src-tauri/backend/`; la finestra nativa **Rizzo PII** (WebView2) lo lancia come
processo figlio, attende il server su `127.0.0.1:5000`, mostra l'UI e lo termina alla chiusura.
Splash con badge **UE / GDPR compliant**, **versione** (iniettata da Rust dalla config) e crediti
nell'app (Simone Rizzo · Rizzo AI Academy). `npx tauri build` → **installer NSIS per-utente**
(`Rizzo PII_1.0.0_x64-setup.exe`, ~1,3 GB, non firmato → avviso SmartScreen atteso).

**6. Pulizia repo.** Rimossi output/cache rigenerabili: vecchia build PyInstaller `dist/`, intermedi
`build/`, `__pycache__/`, `_archive/`, e log W&B stray in `src/training/`. `.gitignore` esteso agli
artefatti Tauri. README/CLAUDE/BUILD aggiornati.

---

## 2026-06-28 — Primo run grande `rizzo-pii:0.3B`: risultati e fix PROVINCE

Primo training completo (1 epoca, ~1h40, BATCH 16 ×2). Modello salvato in
`models/rizzo-pii-0.3B/`. Valutazione per-tag su `validation_real.jsonl` (nuovo
`src/training/evaluate_pii.py`, report in `experiments/full_run/eval_validation.*`):

- **F1 micro (overall) = 0,977** · precision 0,989 · recall 0,965 · token-acc 0,997. Forte.
- Quasi tutti i tag 0,95-1,00; `CATASTO`/`CF`/`PIVA`/`ID_DOC`/`DOCID`/`GENDER`/`TARGA` = 1,000.
- **`PROVINCE` = 0,000** (support 400): unico fallimento totale.

Causa-radice (diagnosticata): nei sintetici `PROVINCE` appare **quasi solo** come `Citta' (XX)`
(sigla tra parentesi dopo una città), e nell'**augment era del tutto assente** (0 occorrenze) —
l'unico tag IT-only mai mostrato in testo reale con connettori vari. La validation la testa come
`in provincia di XX` / `prov. XX` → contesto mai visto → il modello predice `O`. Overfit
strutturale puro (gli altri 8 tag iniettati stanno nell'augment → fanno ~1,0).

Fix applicato: aggiunti snippet `PROVINCE` a `INJECTION_SNIPPETS` in `augment_real_pii.py`
(`in provincia di {PROVINCE}`, `prov. {PROVINCE}`, `Prov. di {PROVINCE}`, `in provincia ({PROVINCE})`).
**Per avere effetto serve rigenerare l'augment + riaddestrare** (vedi comandi sotto).
Nota pratica: in produzione `PROVINCE` è un set chiuso (~110 sigle valide) → catturabile con
gazetteer/regex nella rete di sicurezza, quindi è il tag meno critico da sbagliare.

Inoltre: il salvataggio di `metrics.{json,txt}` ora avviene anche per il run **full** (prima
solo subset) → i prossimi run grandi scrivono le metriche in `experiments/full_run/`.

Rigenerare + riaddestrare per la fix PROVINCE:
```powershell
python src/data_pipeline/augment_real_pii.py -n 40000 --out dataset/synthetic/synthetic_pii_it_realaug.jsonl
python src/data_pipeline/build_subset.py        # opz., aggiorna i subset
python src/training/train_pii.py --type full
```

---

## 2026-06-28 — VRAM al limite durante il run grande: BATCH 16 + accumulo gradiente

Sintomo (run grande, osservato): ETA ~1h che di colpo schizza a ~23h in concomitanza col
caricamento dei batch lunghi. Diagnosi con `nvidia-smi` durante il training: **memoria GPU a
16006/16311 MiB (98%, satura)**. Causa: a `BATCH=24`/`MAX_LEN=768` i batch di documenti lunghi
(raggruppati da `group_by_length`) chiedono ~12 GB di attivazioni; con la VRAM già piena — anche
per le app desktop che usano la GPU (Chrome, WhatsApp, Claude, ecc., ~1-2 GB) — l'allocatore CUDA
va in thrashing sui cambi di batch. (RAM di sistema 51 GB: non è quello il limite.)

Fix:
- `BATCH` 24 → **16**: picco attivazioni ~8-9 GB, margine ampio anche col desktop sulla GPU.
- `gradient_accumulation_steps = 2` (`GRAD_ACCUM`): **batch effettivo 32**, a costo VRAM di 16
  (qualità del gradiente invariata/migliore, niente thrashing).
- `EVAL_EVERY` ora calcolato sugli **step ottimizzatore** (`microbatches // GRAD_ACCUM`), così
  l'eval intermedia resta a ~4 valutazioni reali.

Consiglio operativo: chiudere le app che usano la GPU (Chrome/WhatsApp/Video) per liberare 1-2 GB.

---

## 2026-06-28 — Flag `--type {full,subset}` per scegliere il run

La modalità si seleziona da riga di comando invece che con la variabile d'ambiente:
`python src/training/train_pii.py --type full` (default) o `--type subset`. Per compatibilità
`PII_SUBSET=1` continua a forzare la modalità subset. Implementato con `argparse` (parse_known_args)
in cima allo script.

---

## 2026-06-28 — Iperparametri di training: warmup, weight decay, eval intermedia

Tre fix standard al `TrainingArguments` del run grande, decisi prima del primo run completo
di `rizzo-pii:0.3B`. Applicati anche al subset (modalità `PII_SUBSET=1`).

| Modifica | Prima | Dopo | Perché |
|---|---|---|---|
| `warmup_ratio` | assente (0) | **0.05** | ~5% di step di riscaldamento (~1.300 su ~27k). La testa di classificazione è inizializzata da zero: partire a LR pieno destabilizza i primi step. È la mancanza più importante. |
| `weight_decay` | 0.0 | **0.01** | Regolarizzazione AdamW canonica per il fine-tuning di transformer. Piccolo guadagno atteso, rischio nullo. |
| `eval_strategy` | `"no"` | `"steps"`, `eval_steps = steps_per_epoch // 4` | ~4 valutazioni (solo `eval_loss`) durante l'epoca → su W&B si vede la curva **train-vs-val** e si colgono overfit/anomalie senza aspettare la fine del run (4-5h). Le metriche **P/R/F1 entity-level restano calcolate ALLA FINE** (sezione 6 dello script), come prima. |

**Costo dell'eval intermedia**: trascurabile. ~4 pass forward sulla validation (7k righe, run
grande) a `EVAL_BATCH=64` → ~minuto a valutazione, contro 4-5h di training.

**Note di implementazione**:
- `EVAL_EVERY = max(1, steps_per_epoch // 4)`: cadenza relativa, così vale sia per il run grande
  (~27k step → eval ogni ~6.700) sia per il subset (313 step → eval ogni ~78).
- `save_strategy="no"` invariato: niente checkpoint su disco, niente selezione del best model.
  L'eval intermedia serve solo a **osservare** la curva, non a fare early-stopping.
- Il plot di fine run continua a usare solo i punti di *train* loss (le voci di eval nel
  `log_history` hanno chiave `eval_loss`, non `loss`, quindi non inquinano il plot).
- `EVAL_BATCH` 64 → **32**: con l'eval ora *durante* il training (optimizer residente in VRAM),
  un batch di eval 64×768 rischiava OOM. 32 lo evita; l'eval è infrequente, costo trascurabile.

**LR lasciato a 5e-5**: scelta sicura per mmBERT/ModernBERT. Da rivedere solo guardando W&B.

### Da valutare DOPO il primo baseline (non ancora applicati)
Decisioni rimandate, da prendere guardando le metriche **per-tag** su W&B:
- `EPOCHS=2` se a fine epoca 1 la val F1 sta ancora salendo (occhio all'overfit sui sintetici).
- `gradient_accumulation_steps=2` (batch effettivo 48) per gradienti più lisci, costo ~nullo.
- `LR=8e-5` se converge lento; `3e-5` se instabile.
- Pesi di classe / focal loss se i tag rari (`TARGA`, `CREDITCARDNUMBER`) hanno recall basso
  (sbilanciamento FULLNAME ≫ CREDITCARDNUMBER ~66×).

> ⚠️ Il subset 10k **non** è il banco per tunare LR/epoche: le dinamiche (numero di step ~30×
> minore, regime di scheduler diverso) non rispecchiano 645k×1epoca. Serve solo a validare la
> pipeline. Il tuning vero si fa sul run grande osservando W&B.

---

## 2026-06-28 — Performance VRAM: fix del thrashing a MAX_LEN 768

Diagnosi (misurata con micro-benchmark): a `MAX_LEN=768` un batch denso da 32 usa **15,5 GB su
17,1** → l'allocatore CUDA, vicino al tetto, libera/ri-alloca blocchi grossi a ogni batch lungo
(padding dinamico) causando **thrashing**: primi 2 step veloci, poi 24-37 s/step (~3h per 10k).
L'attenzione era già `sdpa` (non era quello il problema).

Fix applicati:
- `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` (impostato in cima allo script, prima di
  importare torch) — riduce la frammentazione. Vale per tutti i run.
- `BATCH` 32 → **24** per il run grande (margine VRAM).
- `group_by_length=True` + `LengthGroupedTrainer`: raggruppa sequenze di lunghezza simile (meno
  padding sprecato, batch a memoria uniforme). Usa **lunghezze precalcolate** (conteggio parole)
  per non ri-tokenizzare il dataset lazy — il difetto del `group_by_length` standard.
- Modalità SUBSET: `MAX_LEN=256`, `BATCH=32` → smoke test da ~3 min (era ~3h).

Risultato subset: training in ~108 s, VRAM picco 9,2 GB.

---

## 2026-06-28 — Subset rappresentativi per smoke test/tuning

Nuovo `src/data_pipeline/build_subset.py`: genera `dataset/subsets/train_subset_10k.jsonl` e
`val_subset_5k.jsonl`, stratificati per `(fonte × lingua)` + floor sui tag rari (proporzionale +
floor). Attivati nel training con `PII_SUBSET=1` → artefatti in `experiments/subset_smoke/`.
Servono a validare la pipeline e fare cicli rapidi prima del run grande.

---

## 2026-06-28 — Riorganizzazione della repo

Struttura professionale: codice in `src/{data_pipeline,training,inspect,app}/`, dati in
`dataset/{raw,synthetic,processed,validation,subsets}/`, modelli in `models/<versione>/`,
artefatti dei run in `experiments/<run>/`, documentazione in `docs/`. Tutti i path negli script
sono assoluti (risolti da `__file__`): girano da qualsiasi CWD. Modello di produzione rinominato
`models/rizzo-pii-0.3B` (precedente conservato in `models/pii_model_legacy`). `build.spec`,
`app.py`, `.gitignore` e i doc aggiornati di conseguenza. Dettaglio struttura in
[../README.md](../README.md).
