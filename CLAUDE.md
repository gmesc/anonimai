# CLAUDE.md

Guida per Claude Code (claude.ai/code) quando lavora in questa repo. **Prima di trasformare un
braindump in un piano leggere [GUIDA-ARCHITETTO.md](GUIDA-ARCHITETTO.md)** (invarianti,
vocabolario, protocollo). Panoramica e struttura
delle cartelle in **[README.md](README.md)**. Documenti di dettaglio:
**[docs/TASSONOMIA_TAG.md](docs/TASSONOMIA_TAG.md)** (i 22 tag),
**[docs/DATASET.md](docs/DATASET.md)** (composizione completa di train/validation) e
**[docs/TRAINING.md](docs/TRAINING.md)** (unione dei due dataset HF, accortezze sui tag,
iperparametri).

## Cos'è questo progetto

Pipeline per addestrare un modello **mmBERT** (`jhu-clsp/mmBERT-base`) a fare **token
classification di PII**, con focus su **testi legali italiani** (atti, contratti, sentenze)
ma con training **multilingue**. Obiettivo finale: anonimizzare documenti **in locale**
prima di mandarli a LLM closed (anonymize → placeholder + dizionario reversibile locale →
API → ricostruzione), per studi legali / compliance GDPR.

Scelta di mmBERT (encoder multilingue, architettura ModernBERT, context nativa 8192) e non
ModernBERT vanilla perché quest'ultimo è quasi solo inglese.

## Ambiente — vincoli critici e non ovvi

GPU **RTX 5060 Ti (Blackwell, sm_120)** su Windows; Python in `D:\programmi\python`.
Questi punti fanno fallire tutto se ignorati:

- **torch DEVE essere build cu128**: `torch 2.11.0+cu128` (da `https://download.pytorch.org/whl/cu128`).
  Le build cpu/cu121 non supportano sm_120 → `torch.cuda.is_available()` False o crash.
- **torchvision/torchaudio vanno disinstallati** se a versioni vecchie: rompono l'import di
  transformers con `operator torchvision::nms does not exist`. Non servono qui.
- **accelerate ≥ 1.14** (transformers 4.57 chiama `unwrap_model(keep_torch_compile=...)`).
- Windows: nel Trainer **`dataloader_num_workers=0`** (altrimenti `RuntimeError ... bootstrapping`).
- **seqeval non si compila** (bug setuptools_scm) → metriche entity-level (P/R/F1) calcolate
  a mano dentro gli script, nessuna dipendenza.
- Dipendenze extra installate: **`wandb`** (tracking) e **`python-dotenv`** (legge `.env`).
- **Log da PowerShell**: redirezioni `>` e `Tee-Object` scrivono **UTF-16** → leggerli con
  `Get-Content`/`python`, NON con lo strumento Read. Gli script forzano `sys.stdout` UTF-8.

## Mappa della repo

Struttura completa in [README.md](README.md). In breve: codice in `src/`, dati in `dataset/`,
modelli in `models/<versione>/`, artefatti dei run in `experiments/<run>/`, doc in `docs/`.
**I path negli script sono assoluti (risolti da `__file__`): girano da qualsiasi CWD.**

**Pipeline dati — `src/data_pipeline/` (ordine di esecuzione):**
- `llm_template_bank.py` — Gemini scrive documenti legali con soli segnaposto `{SLOT}` →
  `dataset/synthetic/legal_templates.json` (72 template). Guard scarta i template con nomi inline.
- `generate_synthetic_pii.py` — inietta nei template dati con **checksum validi** (CF/PIVA/IBAN)
  → `dataset/synthetic/synthetic_pii_it_200k.jsonl` (`tokens` + `bio_labels`).
- `augment_real_pii.py` — inietta entità sintetiche in **frasi reali** Ai4Privacy (it) in posizioni
  variabili → `dataset/synthetic/synthetic_pii_it_realaug.jsonl`. Spezza il legame template/posizione.
- `prepare_deepmount.py` — rimappa `DeepMount00/pii-masking-ita` (56 tipi Faker IT) sui 22 tag →
  `dataset/processed/deepmount_pii_it_{train,test}.jsonl`.
- `build_validation.py` — **unica validation reale** → `dataset/validation/validation_real.jsonl`.
- `build_subset.py` — subset stratificati (multilingua + tag) per smoke test →
  `dataset/subsets/{train_subset_10k,val_subset_5k}.jsonl`.

**Training — `src/training/`:**
- `train_pii.py` — fonde tutte le fonti, addestra, salva il modello, plotta la loss, stampa
  metriche train/val, logga su **W&B** (run `rizzo-pii:0.3B-v{VERSION}`). **Modello versionato**:
  ogni run grande salva in `models/rizzo-pii-0.3B-v{VERSION}/` (storico, niente sovrascrittura;
  `MODEL_VERSION` in cima al file o `--version`; storia in `models/registry.json`). Vedi "Parametri".
- `test_pii.py` — inferenza CLI sul modello salvato (entità + testo anonimizzato). Risolve in automatico
  l'**ultima** versione `rizzo-pii-0.3B-v*` (fallback al vecchio non versionato → legacy; override `PII_MODEL_DIR`).

**Utility / ispezione (read-only) — `src/inspect/`:**
- `validate_checksums.py` — ricalcola i checksum CF/IBAN/PIVA; **blueprint della rete regex+checksum**
  da affiancare al modello in produzione.
- `inspect_ai4privacy.py` (conteggi lingue/tag), `inspect_lengths.py` (lunghezze), `inspect_no_iban.py`.

**App di anonimizzazione locale — `src/app/` (+ packaging in `docs/BUILD.md`):**
- `server_config.py` — **configurazione host/porta** (+ `prefs.json` con tag esclusi e stato del
  dizionario) condivisa tra tutti gli entry point e con Tauri.
  Catena di precedenza: **CLI `--host`/`--port` > env `PII_HOST`/`PII_PORT` > `config.json` > default
  `127.0.0.1:5005`**. Il config.json è in `%LOCALAPPDATA%\anonimai\` (Windows) /
  `~/.local/share/anonimai/` (Linux) / `~/Library/Application Support/anonimai/` (macOS), lo
  stesso file letto/scritto da Tauri (lib.rs). Include `port_available()` (pre-bind check) e il
  codice di uscita `EXIT_PORT_CONFLICT = 76`: i 3 entry point escono con 76 se la porta è occupata
  **prima di caricare il modello** (evita secondi sprecati). Tauri riconosce il codice 76 e mostra
  il form di configurazione nello splash screen.
- `app.py` — server Flask + **UI**: testo, PDF o file `.md`/`.txt`, chunking con overlap, offset
  globali + dedup. I PDF passano dall'**OCR** dove serve (vedi sotto) e l'UI ha i **riquadri
  manuali** (✏️) per oscurare firme e timbri: frazioni 0-1 della pagina mostrata, inviate come
  `manual_boxes` a `/pdf` e `/pdf/preview`; con i riquadri il download funziona anche senza PII
  testuali (scansione con la sola firma). Anonimizzazione **reversibile** (ogni PII → `[FULLNAME_1]`/`[IBAN_1]`… +
  dizionario locale; tab "Ripristina"). Affianca al modello una **rete regex/checksum** (EMAIL/
  TELEFONO/IBAN/CF/PIVA/carta/importo/targa/**URL**; IBAN/CF/PIVA/carta validati con checksum, che ha
  priorità sul modello). `URL` è un **23° tag solo-regex**: il modello non lo conosce; matcha schema,
  `www.` e domini nudi solo su una **lista chiusa di TLD** (senza, `p.iva`/`S.r.l.` diventerebbero
  domini). **Profilo Svizzera** sempre attivo nei tag esistenti: AVS→`ID_DOC` (checksum EAN-13),
  Cantoni→`PROVINCE`, NAP→`ZIPCODE` (19xx/20xx esclusi: anni), targa CH→`TARGA`, IDI/UID `CHE-…`→`PIVA` (checksum mod-11), telefono `+41`/`091 …`→`TELEPHONENUM`, `CHF`/`Fr.`→`AMOUNT`, `mappale n. … RFD`→`CATASTO`, tessera `80756…`→`ID_DOC` (solo forma). I detector CH stanno **in testa** a `DETECTORS` (sort stabile in `_merge`: vincono i pareggi). n. registro di commercio vecchio formato `CH-020.3.912.345-6`→`PIVA` (solo forma).
  Fixture: `tests/fixtures_ticino.jsonl`. Cornice legale in `docs/CONFORMITA-CH.md`, quadro per
  settori in `docs/RAPPORTO-CONFORMITA-SETTORI.md`, modelli da compilare in
  `docs/MODELLI-DOCUMENTAZIONE.md`. UI: sesta scheda **Buone abitudini** (`habits_body`) e
  promemoria del blocco schermo (`pii_lock_reminder_off`). **Termini
  personali** (🏷️→📌): lista `{value, tag}` in `prefs.json` (`custom_terms`, cap 200, ≥3
  alfanumerici), match letterale con confini di parola in `detectors.match_custom_terms`,
  priorità massima in `_merge` (source `utente`), tag liberi ammessi; su `/settings` GET/POST.
  **Termini in chiaro** (🏷️→👁️, lo specchio): lista `{value, tags}` in `prefs.json` (`keep_terms`,
  cap 200, ≥3 alfanumerici) di valori che NON vanno coperti anche se il modello li riconosce (i nomi
  delle scale nei referti: Ritvo, Beck, Wechsler). `detectors_local.drop_keep_terms` filtra **dopo**
  `_merge` con un **fullmatch** ("Beck" non scopre "Beckenbauer"), opzionalmente ristretto a certi
  tag; si aggiunge col 👁️ sulle righe del dizionario (conferma + rianonimizzazione) e si toglie
  dalla scheda 🏷️. TOGLIE protezione: il Rapporto registra `cleared_on_purpose {count, by_tag}` e
  `keep_terms_count`, mai i valori. `APP_VERSION`. Endpoint: `GET /health` (readiness senza inference, 200/503),
  `POST /analyze`, `POST /pdf`, `POST /preview`, `POST /pdf/preview`, `GET /doc/<id>/page/<n>.png`,
  `GET /doc/<id>/file.pdf`, `DELETE /doc/<id>`, `GET/POST /settings` (alias storico `/tags`),
  `GET/POST /config`, `GET /port-check`; CLI `--host`/`--port`/`--exclude-tags`/`--no-mapping`/`--auth`.
  **Credenziale** (solo se esposto): `PII_AUTH="utente:password"` o `--auth` → HTTP Basic su tutto
  tranne `/health`, `/healthz`, `/favicon.ico`, `/assets/*`; parsing/confronto in `server_config.py`
  (`parse_auth`, `check_basic` con `hmac.compare_digest`, `is_loopback`), mai in `config.json`
  (inv. 11) né in `prefs.json`. Host non-loopback senza credenziale = avviso all'avvio, non rifiuto.
- **Anteprima del PDF a video, prima e dopo** — le due colonne mostrano il documento *renderizzato*,
  non solo il testo. A sinistra, appena si carica un PDF: `POST /preview` lo tiene in memoria e
  ritorna testo + numero di pagine, e la card offre due viste (**Anteprima PDF** default, **Testo**).
  A destra, dopo l'anonimizzazione, una **terza vista** accanto ad Anteprima/Testo: **PDF censurato**,
  cioè lo stesso documento redatto con i placeholder al posto delle PII.
  Il render è **server-side con PyMuPDF** (`page.get_pixmap` → PNG per pagina): dentro Tauri non c'è
  un viewer PDF affidabile (WebView2/WKWebView) e l'app è offline, quindi niente pdf.js da CDN.
  Le pagine sono **pigre** (`loading=lazy`) e messe in cache: un PDF di 200 pagine non costa 200 render.
  **Zoom (issue #92)**: ctrl/⌘+rotella (= pinch del trackpad) o i comandi `− % +` in testata;
  lo zoom è la **larghezza** delle pagine (`--z`), non un `transform`, e vale per **entrambe** le
  colonne — `matchScroll` specchia ora anche l'asse X. ⚠️ il fattore di scala si **misura** sugli
  `scrollWidth/Height` prima/dopo il reflow (con `z/ZOOM` il punto sotto il puntatore scivolava:
  padding e margini non scalano). Oltre 1,5× le pagine visibili si richiedono a **220 dpi**
  (`?dpi=220`, lista chiusa in `pdf_export.parse_preview_dpi`), con tetto `MAX_HIRES_PAGES=8`
  per documento.
  I documenti stanno in una **LRU in memoria** (`_DOCS`, `MAX_DOCS=6`, **`DOC_TTL` 10 min** di
  inattività, sweep a ogni accesso + thread daemon) e **mai su disco**: valgono
  quanto il documento stesso e muoiono col processo. `DELETE /doc/<id>` (sempre 204, idempotente)
  li butta **subito**: lo chiamano «Pulisci», il caricamento di un documento nuovo, il `pagehide`
  della finestra e lo **svuotamento per inattività** dell'UI (`IDLE_MIN=7` minuti, avviso a 6,
  fermo mentre `#go` è disabilitato). ⚠️ il TTL del server non può superare i 7 minuti dichiarati
  a schermo: `tests/test_i18n_chiavi.py` lega le due cose.
  `POST /pdf/preview` fa lo stesso lavoro di `/pdf` ma lascia il binario nello store e ritorna
  `{doc_id, n_pages, residual, skipped}`: l'anteprima a destra e il bottone "Scarica PDF" usano
  **la stessa copia**, quindi guardare il PDF e poi scaricarlo costa **una sola** anonimizzazione
  (il download passa da `/doc/<id>/file.pdf`). `/pdf` resta invariato per chi usa l'API.
- **Preferenze di anonimizzazione** → `prefs.json` nella config dir (`EXCLUDED_TAGS`,
  `MAPPING_ENABLED`). File **separato da `config.json`** perché Tauri riscrive quest'ultimo per
  intero quando si cambia porta dallo splash. Precedenza: campo nella richiesta > CLI > env > file.
- **Tag disattivabili**: i tag deselezionati vengono rilevati ma **non** sostituiti (restano in
  chiaro) — serve a confrontare gli importi o a tenere età/sesso in un caso clinico. Env
  `PII_EXCLUDE_TAGS`, campo `exclude_tags`. UI: icona 🏷️ nell'header → legenda dei 23 tag con
  toggle. La legenda (descrizioni IT/EN + esempi) vive in `TAGS` in cima a `app.py`.
- **Dizionario reversibile on/off** (`MAPPING_ENABLED`, default **on**; env `PII_MAPPING=0`, campo
  `include_mapping`): con off l'anonimizzazione è **definitiva**. Non è cosmetico — `analyze()` non
  costruisce la mappa, la risposta non ha `mapping`, e i segmenti-entità **perdono il campo `t`**
  (altrimenti il dizionario si ricostruirebbe dal payload); l'UI non scrive `pii_map` e nasconde il download. Il dizionario vive in **`sessionStorage`** per default (muore con la finestra); `localStorage` solo con «💾 ricorda» (`pii_map_persist`). Bottone **📋 Rapporto**: JSON senza valori (SHA-256 input, conteggi, residui, versioni) per documentare il trattamento. La **numerazione resta** (`[FULLNAME_1]` due volte = stesso
  soggetto): è utile all'LLM e da sola non riporta al valore. UI: switch nella card di input, ambra
  quando è off. `source_text` continua a tornare — è il documento che hai appena mandato tu, non una
  chiave di ripristino.
- `pdf_export.py` + endpoint **`POST /pdf`** — **download del PDF anonimizzato** (issue #7, punto 1),
  bottone "📄 Scarica PDF anonimizzato" nella card Risultato. Due modalità: se l'input era un **PDF**
  si fa **redazione vera** del documento originale (`apply_redactions()`: il testo esce dal content
  stream, non ci si disegna sopra un rettangolo) con i placeholder al posto delle PII e il layout
  intatto; altrimenti (testo incollato, `.md`/`.txt`) si **ricostruisce** un PDF impaginando da zero
  il solo testo anonimizzato.
  **Il dizionario non viaggia sulla rete in nessuna direzione**: `/pdf` prende lo stesso input di
  `/analyze`, richiama `analyze(..., mapping_enabled=True)` internamente e la mappa muore con la
  richiesta. Per questo il bottone funziona identico anche con il **dizionario reversibile
  disattivato**, dove il client non ne ha nessuno (il costo è una seconda inferenza).
  Matching **char-preciso** con confini di parola (indice per carattere da `rawdict` + regex ancorate
  `(?<!\w)…(?!\w)`), tollerante alla **sillabazione a fine riga** e agli spazi tra token: "DE" non
  viene redatto dentro "CORDELLA". Unica eccezione alle ancore: se il valore ha **punteggiatura ai
  bordi** il modello ha tagliato a metà una parola spezzata a fine riga (su "Fran-\ncesco Cordella"
  etichetta `-\ncesco Cordella`) — lì il confine di parola è proprio ciò che impedirebbe di trovarlo,
  quindi si toglie, ma **solo** se il resto ha ≥ 4 caratteri alfanumerici (altrimenti `.it`
  matcherebbe "it" dentro ogni parola).
  Oltre al testo di pagina ripulisce ciò che `apply_redactions()` **non** tocca e in cui la PII
  sopravviverebbe: metadati + XMP, contenuto delle **annotazioni**, valore dei **campi modulo**,
  titoli dei **segnalibri**; gli **allegati incorporati** vengono rimossi in blocco.
  **Due casi in cui un valore resta in chiaro, entrambi segnalati con un avviso nell'UI** (header
  `X-PII-Residual` e `X-PII-Skipped`): (a) *residui* = valore ancora leggibile nell'output alla
  verifica finale; (b) *saltati* = valori con < 2 caratteri alfanumerici o di 2 sole cifre (es. "45"),
  non cercabili senza devastare il documento. Se in tutto il PDF non si trova **nessuna** occorrenza
  e non ci sono riquadri manuali → `422`, non un PDF "anonimizzato" che non lo è. Nessuna
  dipendenza dal modello: `pdf_export.py` è testabile in isolamento.
- **OCR (issue #98)** — `pdf_export.page_textpage()`: per pagina, tre vie — solo testo nativo
  (nessun OCR), scansione (`get_textpage_ocr(full=True)`), **ibrida** con carta intestata/loghi
  come immagine su pagina normale (`full=False`, OCR delle sole immagini fuso col nativo). Usa il
  **Tesseract compilato nella wheel di PyMuPDF**: servono solo i file **tessdata** (`PII_TESSDATA`
  o `TESSDATA_PREFIX` o ricerca automatica; lingue `PII_OCR_LANGS`, default `ita+eng`, i cui file
  devono esistere o l'OCR si dichiara non disponibile — `/health` espone `"ocr"`). ⚠️ la libreria
  legge **anche l'env `TESSDATA_PREFIX`** e può vincere sul parametro `tessdata=`: l'env viene
  riallineato alla cartella scelta in `tessdata_dir()`. La verifica dei **residui ri-OCRizza**
  le pagine toccate (senza, su una scansione direbbe sempre "0 residui"); sulle pagine-scansione
  redatte si scrive un **layer di testo invisibile** (`render_mode=3`, solo rotazione 0) col testo
  OCR non-PII → l'output è ricercabile; le parole che coincidono con un valore del dizionario
  (anche "saltato") **non** entrano nel layer. Senza tessdata: comportamento identico a prima,
  messaggi con l'istruzione per abilitare. Docker: tessdata scaricato pinnato in build.
- **Riquadri manuali (issue #98 punto 2)** — `redact_pdf(..., manual_boxes=...)`: rettangoli
  `{page, x0..y1}` in frazioni 0-1 della pagina **come mostrata** (stesso spazio del PNG di
  anteprima e di `add_redact_annot`, rotazione inclusa: nessuna matrice lato client); pixel
  cancellati con `PDF_REDACT_IMAGE_PIXELS`, grafica vettoriale intatta. Dizionario vuoto ammesso
  solo con riquadri. Validazione in `parse_manual_boxes` (clamp, max 500, degeneri scartati).
- **Offline dimostrato, non dichiarato**: in testa ad `app.py` le variabili `HF_HUB_OFFLINE`/
  `TRANSFORMERS_OFFLINE`/`HF_HUB_DISABLE_TELEMETRY`/`DO_NOT_TRACK` (setdefault **prima** degli
  import pesanti: quelle librerie le leggono all'import); `@app.after_request` manda CSP
  (`connect-src 'self'`) + `no-store` **imposto** (⚠️ `send_file` ne mette uno suo: con
  `setdefault` le PNG delle pagine restavano cacheabili). Prove: `tests/test_no_egress.py`
  (AST, non stringhe), `tests/test_claims.py` (lint dei claim pubblici),
  `src/app/smoke_offline.py` (22 endpoint con `socket.connect` bloccato). Campagna e limiti
  in `docs/VERIFICA-OFFLINE.md`.
- `serve.py` — entry **headless** (solo Flask, niente browser): è il backend dell'app Tauri; log su
  `%LOCALAPPDATA%\anonimai\backend.log`. Pre-check porta + `sys.exit(76)` se occupata.
  `desktop_app.py` — entry PyInstaller legacy (apre il browser); stesso pre-check.
  `assets/` — mascotte (il riccio) + icone + **`tokens.css`** (design system StudIA, fonte di
  verità per palette/barre/tema — la UI embedded in `app.py` lo carica per primo) +
  **`fonts/OpenMoji-color.woff2`** (emoji self-hosted, offline). L'interfaccia si chiama
  **AnonimAI** e segue gli standard StudIA (`~/.claude/skills/studia-app-layout`): zero
  border-radius, tre accenti coi ruoli fissi (teal=azione, giallo=segni utente/riquadri,
  blu=riferimento), tema chiaro/scuro via `data-theme` (localStorage `pii_theme`), colori dei
  tag con doppia rampa chiaro/scuro in `colors()`. **Due modalità senza tab**: si apre in
  Anonimizza, il click sul brand 🕵️ commuta su Deanonimizza (label `AnonimAI — <modalità>`
  nella testata). Niente dropzone: **drag&drop su tutta la finestra** (solo in Anonimizza,
  overlay flottante); l'input file resta hidden nel DOM. Icona: `assets/detective.png`
  (OpenMoji 1F575). **Impostazioni (⚙️) a cinque schede**: Server · Come funziona · Sicurezza ·
  Crediti · Condizioni (`terms_body` = `TERMS.md`, versione `TERMS_VERSION` mostrata al primo
  avvio finché `pii_terms_ack` non coincide; banner `#netWarn` se `location.hostname` non è loopback) (chiavi i18n `how_body`/`sec_body`/`cred_body`; il modello nei crediti arriva da
  `/health`). I tre bottoni del risultato hanno un **popup d'uso a 900 ms** (`.htip`,
  `transition-delay`, niente timer JS; chiavi `tip_copy`/`tip_pdf`/`tip_dict`). Niente
  footer: i crediti e l'attribuzione OpenMoji stanno lì. Le card non hanno cornice propria
  (unica linea: il confine fra le due colonne). `smoke_app.py`, `make_test_pdf.py`.

**App desktop Tauri — `tauri/`:** finestra nativa **AnonimAI** (WebView2) che lancia il backend
`serve.py` impacchettato come **sidecar** (`build_sidecar.spec` → `tauri/src-tauri/backend/`).
All'avvio legge `config.json` (host/porta), passa i valori al sidecar via env `PII_HOST`/`PII_PORT`,
attende il server sulla porta configurata e mostra l'UI. Se il sidecar esce con codice **76** (porta
occupata), lo splash mostra un form di configurazione (host + porta) con "Salva e riprova": Tauri
scrive `config.json`, rilancia il sidecar e riprova. Splash con badge UE/GDPR + versione. `npx tauri build`
→ installer NSIS per-utente. Dettagli e comandi in `docs/BUILD.md`. Comandi Tauri esposti allo splash:
`save_config(host, port)` e `retry_backend`.

**Config:** `.env` (segreti W&B, **gitignorato**), `.gitignore`, `build.spec`/`build_sidecar.spec`/
`installer.iss` + `tauri/` (packaging).
**Artefatti non versionati** (gitignored): `dataset/`, `models/`, `experiments/`, `wandb/`, `build_env/`,
`dist/`, `build/`, `tauri/node_modules/`, `tauri/src-tauri/{target,gen,backend}/`.

## Idea architetturale chiave: "LLM autore, codice etichettatore"

Il cuore della generazione sintetica: **l'LLM scrive solo la prosa con segnaposto, il codice
inietta i dati**. Risolve insieme tre problemi: label BIO esatte (sappiamo dove iniettiamo),
checksum matematicamente validi, nessuna PII reale rigurgitata dall'LLM. **Non far mai scrivere
all'LLM i dati sensibili veri.**

## Tassonomia: 22 tag (dettaglio in TASSONOMIA_TAG.md)

`TAG_MAP` + `DROP_TYPES` + `normalize_labels()` in `train_pii.py` rimappano **al caricamento**
(file grezzi intatti). Per cambiare la tassonomia si edita **solo** `TAG_MAP`/`DROP_TYPES`.

Fusioni: nomi+ruoli legali → `FULLNAME`; `SEX`→`GENDER`; `TAXNUM`→`PIVA`; `PEC`→`EMAIL`;
`RG`→`DOCID`; `IDCARDNUM`/`PASSPORTNUM`/`DRIVERLICENSENUM`/`SOCIALNUM`→`ID_DOC`; `CONTO`→`IBAN`.
Rimossi (→`O`): `TITLE` (appellativo), `TRIBUNAL` (ente pubblico, non PII).
Tag aggiunti via sintetico: `ORG`, `DOCID`, `CATASTO`, `CONTO`(→IBAN), `PROVINCE`.

I 5 tag legali IT-specifici (`CF`, `PIVA`, `CATASTO`, `DOCID`, `PROVINCE`) non esistono come
dato reale da nessuna parte → vengono solo dai sintetici.

## Fonti dati (dettaglio in DATASET.md)

Quattro fonti, tutte ricondotte ai 22 tag al caricamento:
1. **Ai4Privacy** `open-pii-masking-500k` — reale, **8 lingue**, ~464k righe train (it ~55k).
   `hf download ai4privacy/open-pii-masking-500k-ai4privacy`. Ha `mbert_tokens`+`mbert_token_classes`.
2. **Sintetico da template** — `generate_synthetic_pii.py`, 200k righe, copre i tag legali IT.
3. **Augment** — `augment_real_pii.py`, 40k, entità sintetiche in frasi reali it.
4. **DeepMount** `DeepMount00/pii-masking-ita` — Faker IT, 41k; dà contesto reale a IBAN/ORG/AMOUNT/TARGA.

Train pool ≈ **745k righe** (multilingue; italiano rinforzato al ~45%). ~38% sintetico.

## Validation: UNA validation reale unificata

`validation_real.jsonl` (7k righe, **solo italiano**, da `build_validation.py`):
- base reale held-out = Ai4Privacy val (it) + DeepMount test;
- i 5 tag senza dato reale sono **iniettati in frasi reali held-out** (frasi della validation
  Ai4, non nel training) → contesto reale, niente leakage.

Tutti i sintetici e il DeepMount **train** stanno nel pool di training; il DeepMount **test**
è consumato solo nella validation. Scelta: validation italiana perché l'uso reale è il dominio
legale IT (il training resta multilingue; le altre lingue non sono validate).

## Parametri di training importanti (`src/training/train_pii.py`)

- `LANG = None` → **multilingue** (8 lingue Ai4Privacy); `"it"` = solo italiano. Synth/DeepMount
  sempre inclusi (già italiani, rinforzo).
- `MAX_LEN = 768` → copre i sintetici (max 771 subword) e DeepMount (660); con 512 si troncava il
  **33% dei sintetici**. Padding dinamico.
- `BATCH = 16` + `GRAD_ACCUM = 2` (batch **effettivo 32**) → a MAX_LEN 768 su una 16 GB **condivisa
  col desktop**, batch più grandi saturano la VRAM e causano **thrashing** (allocatore CUDA che
  libera/ri-alloca ad ogni batch lungo → 24-37 s/step). Con 16 il picco di attivazioni resta ~8-9 GB.
  Altre mitigazioni: `group_by_length=True` (`LengthGroupedTrainer` usa lunghezze precalcolate per
  non ri-tokenizzare il dataset lazy) e `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`.
  Chiudere le app che usano la GPU (Chrome/WhatsApp/…) libera 1-2 GB.
- `EPOCHS = 1`. L'eval **non** gira durante il training: train loss a ogni step, **metriche P/R/F1
  ALLA FINE** su validation e su un campione di train (`TRAIN_EVAL_N`).
- **Modalità del run** (`--type {full,subset}`, default `full`; anche `PII_SUBSET=1` forza subset):
  `subset` = smoke test / tuning sui subset `dataset/subsets/` (10k/5k), MAX_LEN 256, BATCH 32,
  ~3 min → `experiments/subset_smoke/`. `full` = run grande.
- Output run grande: `models/rizzo-pii-0.3B-v{VERSION}/` (+ tokenizer) e `experiments/full_run_v{VERSION}/`
  (loss + out/) + append a `models/registry.json`. La versione viene da `MODEL_VERSION` o `--version`.

## Weights & Biases

`train_pii.py` carica `.env` con `load_dotenv()`; se c'è `WANDB_API_KEY` attiva
`report_to=["wandb"]` (progetto da `WANDB_PROJECT`, default impostato a `pii-mmbert-it`).
Logga la **train loss live a ogni step** e le **metriche finali** (`final/train_*`, `final/val_*`).
Il `.env` è **gitignorato**: non committarlo. Senza chiave, W&B si disattiva da solo.

## Comandi

Tutti gli script forzano UTF-8 e risolvono i path da soli (girano da qualsiasi CWD; i comandi
sotto si lanciano dalla root per comodità).

```powershell
# 1) (opz.) template legali via Gemini   (richiede GEMINI_API_KEY)
python src/data_pipeline/llm_template_bank.py --per-type 5 --append

# 2) sintetico da template (200k)
python src/data_pipeline/generate_synthetic_pii.py -n 200000 --out dataset/synthetic/synthetic_pii_it_200k.jsonl

# 3) augment in testo reale (40k)
python src/data_pipeline/augment_real_pii.py -n 40000 --out dataset/synthetic/synthetic_pii_it_realaug.jsonl

# 4) DeepMount rimappato 56->22 tag  (richiede login HF: hf auth login)
python src/data_pipeline/prepare_deepmount.py

# 5) validation reale unificata (7k)
python src/data_pipeline/build_validation.py

# 6) subset stratificati per smoke test (10k/5k)
python src/data_pipeline/build_subset.py

# 7a) smoke test / tuning sul subset (~3 min)  -> experiments/subset_smoke/
python src/training/train_pii.py --type subset
# 7b) run grande su tutto  -> models/rizzo-pii-0.3B-v{VERSION}/ + experiments/full_run_v{VERSION}/ + W&B
python src/training/train_pii.py --type full                  # usa MODEL_VERSION nel file
python src/training/train_pii.py --type full --version 1.2.0  # oppure versione esplicita

# inferenza / app
python src/training/test_pii.py "Mi chiamo Mario Rossi, IBAN ..."
python src/app/app.py            # http://127.0.0.1:5005  (PII_PORT per override; 5000 = AirPlay su macOS)

# ispezione read-only
python src/inspect/inspect_ai4privacy.py
python src/inspect/inspect_lengths.py
```

## Limiti noti / aspettative oneste

- **Overfit strutturale**: i tag che vengono solo dai template rischiano di imparare la
  *struttura* invece dell'entità. Mitigazioni in atto: 72 template (non più ~29), augment in
  testo reale, e il contesto vario di DeepMount per IBAN/ORG/AMOUNT/TARGA.
- **Validation solo italiana**: non misura le 7 lingue non-it (scelta voluta).
- **Tag legali IT-only** (`CF`/`PIVA`/`CATASTO`/`DOCID`/`PROVINCE`): in validation sono entità
  generate in frasi reali → buon proxy, non eval completamente cieco. `PROVINCE` nel train ha
  poca diversità di contesto (quasi solo dai template).
- **Sbilanciamento di classe**: FULLNAME ≫ CREDITCARDNUMBER (~66×) → i tag rari sono più rumorosi.
- **Valori off-domain di DeepMount**: nomi/indirizzi USA; utili per forma/contesto, non come
  valori italiani.
- In produzione affiancare **sempre** la rete regex+checksum (`src/inspect/validate_checksums.py`) al modello.
