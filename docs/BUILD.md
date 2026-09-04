# Build dell'app desktop (CPU — Windows, Linux e macOS)

Crea un eseguibile/installer **standalone e offline** dell'anonimizzatore PII.
Usa una build **CPU di PyTorch** (gira su qualsiasi PC, niente CUDA richiesta).
Windows: vedi sotto. **Linux** (.deb/.AppImage): vedi **[§ Build Linux](#build-linux-debappimage)**.
**macOS** (.app/.dmg): vedi **[§ Build macOS](#build-macos-appdmg)**.

Esistono due modi di impacchettare, entrambi CPU/offline:

- **Tauri (consigliato per distribuire)** — vera **finestra nativa** (WebView2) + installer NSIS
  per-utente. Vedi **[§ App Tauri](#app-tauri-finestra-nativa--installer-nsis)**.
- **PyInstaller + Inno Setup (legacy)** — apre l'UI nel **browser di sistema** su localhost.
  Vedi **[§ PyInstaller](#pyinstaller--inno-setup-legacy-browser)**. È anche la base del sidecar Tauri.

## Architettura (perché un "sidecar")

Il motore dell'app è **Python + PyTorch + il modello mmBERT**: non gira dentro Rust/WebView.
Per questo, sia con Tauri sia col build legacy, il backend è il **server Flask** (`src/app/app.py`)
impacchettato con PyInstaller. Con Tauri la finestra nativa lo lancia come **processo figlio
(sidecar)**, attende che risponda su `127.0.0.1:5005`, poi mostra l'UI; alla chiusura lo termina.

---

## OCR delle scansioni (tessdata)

L'OCR dei PDF-scansione usa il **Tesseract compilato dentro la wheel di PyMuPDF**: non serve
installare Tesseract, servono **solo i language data** (`ita.traineddata`, `eng.traineddata`).
Senza, l'app funziona come prima e i messaggi d'errore spiegano come abilitarlo
(`/health` espone `"ocr": true|false`).

```bash
# opzione A — cartella propria (vale su qualsiasi OS; anche per il sidecar Tauri):
mkdir -p ~/tessdata && cd ~/tessdata
curl -LO https://github.com/tesseract-ocr/tessdata_fast/raw/4.1.0/ita.traineddata
curl -LO https://github.com/tesseract-ocr/tessdata_fast/raw/4.1.0/eng.traineddata
export PII_TESSDATA=~/tessdata          # Windows: setx PII_TESSDATA %USERPROFILE%\tessdata
```

- **opzione B (macOS)**: `brew install tesseract tesseract-lang` — la cartella viene trovata da sola.
- **opzione B (Windows)**: installer UB Mannheim (spuntare Italian) — poi `PII_TESSDATA` sulla
  sua cartella `tessdata` se non viene trovata da sola.
- **Docker**: già incluso nel `Dockerfile` (scaricato pinnato in build, offline a runtime).
- Lingue diverse: `PII_OCR_LANGS` (default `ita+eng`); i file delle lingue elencate devono
  esistere nella cartella, altrimenti l'OCR si dichiara non disponibile.

## Guscio Electron (prova rapida, `npm start`)

Per **provare l'app in una finestra desktop senza impacchettare niente** — niente Rust,
niente PyInstaller — c'e' un guscio Electron in **`electron/`**. Fa lo stesso mestiere della
finestra Tauri (lancia il backend Flask come processo figlio, aspetta `/health`, punta la
finestra sull'app, e alla chiusura termina il figlio), ma il backend gira **dal sorgente**
con un Python del sistema.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # una volta
npm install        # scarica Electron in electron/node_modules
npm start          # apre la finestra AnonimAI
```

- **Python**: si cerca `PII_PYTHON` → `.venv/` → `venv/` → `build_env/` → `python3`. Se manca
  qualcosa la finestra lo dice invece di restare in caricamento.
- **Porta**: `PII_PORT=5006 npm start` per cambiarla; se e' occupata il backend esce con **76**
  e lo splash lo spiega (stesso codice che riconosce Tauri).
- **OCR**: nessuna configurazione se Tesseract e' installato di sistema (`brew install tesseract
  tesseract-lang`), altrimenti `PII_TESSDATA=/percorso/tessdata npm start`.
- I link esterni (repo, Hugging Face nei Crediti) si aprono nel **browser di sistema**.

⚠️ **Non e' il guscio di distribuzione**: gli installer firmati restano Tauri (sotto). Qui non
c'e' sidecar impacchettato, quindi la cartella `electron/` non entra nelle build di rilascio.

## App Tauri (finestra nativa + installer NSIS)

### Prerequisiti (una volta)
- **Rust** (`rustup`), **Node.js** + **npm**, **WebView2 Runtime** (già presente su Win10/11 aggiornati).
- Il **venv CPU** `build_env/` (vedi § PyInstaller, passo 1) per costruire il sidecar.

### 1. Costruire il sidecar (backend headless)
Entry dedicato `src/app/serve.py` (solo Flask, niente browser); spec `build_sidecar.spec`.
Si costruisce **dentro le risorse Tauri**:
```powershell
build_env\Scripts\pyinstaller.exe build_sidecar.spec --noconfirm `
  --distpath tauri\src-tauri\backend --workpath build\sidecar_work
```
Output: `tauri\src-tauri\backend\pii-backend\pii-backend.exe` (+ `_internal\`, modello, asset) ≈ 1,8 GB.

### 2. Build dell'app + installer
```powershell
cd tauri
npm install                  # prima volta: scarica la CLI di Tauri
npx tauri icon ..\src\app\assets\detective.png   # (ri)genera le icone dall'icona detective
npx tauri build              # compila Rust + bundle + installer NSIS
```
Output installer: `tauri\src-tauri\target\release\bundle\nsis\AnonimAI_2.0.0_x64-setup.exe`
(il nome viene da `productName` in `tauri.conf.json`).
Installer **per-utente** (niente admin), in italiano, con shortcut e disinstallazione.

### Sviluppo / debug
- `npx tauri dev` avvia l'app collegata ai sorgenti (ricompila Rust al volo).
- Log del backend: `%LOCALAPPDATA%\anonimai\backend.log` (il sidecar è windowed, niente console).
- Per rigenerare con un **nuovo modello**: riaddestra (crea `models\rizzo-pii-0.3B-v{VERSION}\`),
  aggiorna il path in **`build_sidecar.spec`** (riga `datas += [("models/rizzo-pii-0.3B-v...", "pii_model")]`),
  poi rifai il passo 1 e il passo 2. Build attuale: **v1.5.0**.

### Build Windows da macOS/Linux → GitHub Actions

**Non si compila da un altro SO**, nemmeno con Docker: su macOS i container sono Linux, e
PyInstaller non cross-compila (il sidecar è Python+torch, va costruito sul SO di destinazione).
La strada è un runner Windows di GitHub Actions: **[`.github/workflows/build-windows.yml`](../.github/workflows/build-windows.yml)**
fa gli stessi passi 1 e 2 su `windows-latest` e allega l'installer alla release del tag.

Il modello è gitignorato: il workflow lo scarica da Hugging Face, repo **pubblico**
[`rizzoaiacademy/rizzo-pii-0.3B`](https://huggingface.co/rizzoaiacademy/rizzo-pii-0.3B)
branch `v1.5.0` → nessun token, nessun secret. Per cambiare modello si aggiornano insieme
`MODEL_REPO`/`MODEL_REV`/`MODEL_DIR` nel workflow e il path in `build_sidecar.spec`.

Due modi di lanciarlo:
```bash
# a) build di prova: l'installer resta come artifact del run (5 giorni, serve accesso al repo)
gh workflow run build-windows.yml        # oppure Actions > build-windows > Run workflow

# b) release vera: il tag fa partire anche release.yml, che crea la release;
#    build-windows la attende (max 5 min) e ci carica l'.exe
git tag -a v2.0.1 -m "AnonimAI 2.0.1" && git push origin v2.0.1

# c) riempire una release GIA' pubblicata (es. l'.exe mancante sulla 2.0.0):
#    l'asset lo carica il runner, non passa da casa
gh workflow run build-windows.yml -f release_tag=v2.0.0
```
L'installer viene rinominato **`AnonimAI-<versione>-Windows-Setup.exe`** (la versione arriva da
`tauri.conf.json`), la stessa convenzione degli artefatti macOS/Linux a cui puntano i pulsanti di
download della landing in [`docs/index.html`](index.html). Attenzione: gli **artifact dei run non
sono pubblici** (servono login e accesso al repo, e scadono) — per la landing serve sempre un
**asset di release**, cioè la via (b) o la (c).
Ri-pushare lo stesso tag sostituisce l'asset (viene cancellato e ricaricato: l'API di GitHub
non sovrascrive un asset con lo stesso nome).

Accortezze:
- **Limite di 2 GiB per asset di release.** L'NSIS sta sui ~1,5-1,8 GB: passa, ma con poco
  margine. Se cresce, l'upload risponde 422.
- **Disco del runner** ~25 GB liberi: per questo si usa l'indice `whl/cpu` di torch (il wheel
  Windows di default tira dentro CUDA) e si cancella `build/sidecar_work` dopo PyInstaller.
- **Tempi**: ~35 min il primo run, ~15 i successivi (cache di cargo su `src-tauri/target`).
- L'installer **non è firmato** → SmartScreen avvisa al primo avvio, come per la build locale.

---

## Build Linux (.deb/.AppImage)

**Non si compila da Windows** (PyInstaller e i bundle Tauri Linux/`webkit2gtk` vanno fatti su
Linux). Usa una macchina Ubuntu/Debian o **WSL2**. Tutto è automatizzato in **`build_linux.sh`**
(root): stesso `build_sidecar.spec`, ma il sidecar esce come `pii-backend` (senza `.exe`) e i
bundle sono `deb`/`appimage`. Il Rust ([`lib.rs`](../tauri/src-tauri/src/lib.rs)) sceglie già il
nome del binario in base al SO (`cfg!(windows)`).

```bash
# prerequisiti di sistema (una volta)
sudo apt update && sudo apt install -y \
  build-essential curl wget file libssl-dev libxdo-dev patchelf \
  libwebkit2gtk-4.1-dev librsvg2-dev libayatana-appindicator3-dev
# + Rust (https://rustup.rs) e Node.js 18+

# copia il modello addestrato sulla macchina Linux in models/rizzo-pii-0.3B-v1.2.0/
bash build_linux.sh
```
Output: `tauri/src-tauri/target/release/bundle/{deb/*.deb, appimage/*.AppImage}`. Il modello è
gitignorato (~1,23 GB): va copiato a mano sulla macchina Linux, non è nel repo.

### Con Docker (consigliato: riproducibile, non sporca il sistema)

`Dockerfile.linux` (root) crea un'immagine con tutta la toolchain + le dipendenze Python già
installate (torch CPU, transformers, pyinstaller). Sorgenti e modello si **montano** a runtime
(`-v`), così l'immagine resta riutilizzabile e l'output finisce sull'host. Serve Docker (su
Windows: Docker Desktop con backend WSL2).

```bash
cd /mnt/d/documenti/rizzo_pii     # o una copia in ~/ (più veloce: vedi nota)
docker build -t anonimai-builder -f Dockerfile.linux .
docker run --rm -e VENV=/opt/venv -e APPIMAGE_EXTRACT_AND_RUN=1 \
  -v "$PWD":/work -w /work anonimai-builder
# artefatti -> tauri/src-tauri/target/release/bundle/{deb,appimage}/  (visibili anche da Windows)
```
- L'immagine si ricostruisce solo se cambiano le dipendenze; le build successive sono veloci.
- Se l'**AppImage** fallisce nel container (FUSE): `... anonimai-builder bash build_linux.sh deb`
  produce solo il `.deb`.
- **Velocità**: buildare sul mount `/mnt/d` (filesystem Windows) è lento. Per build ripetute,
  `rsync` i sorgenti + il modello in `~/` dentro WSL e monta quella copia.

---

## Build macOS (.app/.dmg)

Come per Linux, **non si compila da un altro SO**: PyInstaller e il bundle Tauri macOS vanno
fatti su un Mac. Tutto automatizzato in **`build_macos.sh`** (root), speculare a `build_linux.sh`:
stesso `build_sidecar.spec`, sidecar `pii-backend` senza estensione (il Rust in
[`lib.rs`](../tauri/src-tauri/src/lib.rs) sceglie il nome col `cfg!(windows)`), bundle `app`/`dmg`
al posto di `nsis` — la conf Tauri resta su NSIS per Windows e qui si sovrascrive da CLI con
`--bundles`.

```bash
# prerequisiti (una volta)
xcode-select --install                 # Command Line Tools
# + Rust (https://rustup.rs) e Node.js 18+

bash build_macos.sh                    # .app + .dmg
bash build_macos.sh app                # solo il .app (piu' veloce, per provare)
VENV=build_env_macos bash build_macos.sh   # venv dedicato invece di .venv
```
Output: `tauri/src-tauri/target/release/bundle/macos/AnonimAI.app` e `.../dmg/*.dmg`.

Note specifiche di macOS:
- **Niente indice PyTorch CPU**: su macOS la ruota di default è già CPU/MPS, quindi lo script
  installa `torch` senza `--index-url` (a differenza di Windows/Linux).
- **Firma**: il bundle **non è firmato né notarizzato**. In locale si apre senza problemi (un file
  che non arriva da internet non ha l'attributo di quarantena). Copiandolo su un altro Mac serve
  "tasto destro → Apri", oppure `xattr -dr com.apple.quarantine "AnonimAI.app"`. Per distribuirlo
  davvero servono un Developer ID e la notarizzazione Apple.
- **Architettura**: il `.app` esce per l'arch della macchina che compila (arm64 su Apple Silicon).
  Per un binario universale servirebbero due build di PyInstaller + `lipo`.
- **Porta 5005**: se stai già facendo girare `python src/app/app.py` in sviluppo, fermalo prima di
  lanciare il `.app`, altrimenti il sidecar esce con codice 76 e lo splash chiede una porta nuova.

---

## PyInstaller + Inno Setup (legacy, browser)

## Componenti
- `src/app/desktop_app.py` — entry point: avvia il server locale e apre il browser.
- `src/app/app.py` — logica (modello + chunking); `MODEL_DIR` si risolve anche dentro l'exe.
- `build.spec` (root) — configurazione PyInstaller. Impacchetta `models/rizzo-pii-0.3B-v1.2.0` come
  `pii_model` dentro l'exe; esclude TF/CUDA/ecc. Entry: `src/app/desktop_app.py`, `pathex=src/app`.
- `installer.iss` — script Inno Setup per l'installer `.exe`.
- `build_env\` — virtualenv CPU dedicato (NON il Python di sistema, che ha torch CUDA).

## Passi

### 1. Ambiente CPU (una volta)
```powershell
python -m venv build_env
build_env\Scripts\python.exe -m pip install --upgrade pip
build_env\Scripts\python.exe -m pip install --index-url https://download.pytorch.org/whl/cpu torch
build_env\Scripts\python.exe -m pip install "transformers==4.57.3" tokenizers safetensors flask pymupdf pyinstaller
```

### 2. Build dell'eseguibile
```powershell
build_env\Scripts\pyinstaller.exe build.spec --noconfirm
```
Output: `dist\AnonimizzatorePII\AnonimizzatorePII.exe` (cartella autocontenuta, include il modello).
Avviabile direttamente con doppio clic — apre il browser su http://127.0.0.1:5005/.

### 3. Installer (opzionale, per distribuirlo)
Installa Inno Setup (https://jrsoftware.org/isdl.php), poi:
```powershell
iscc installer.iss
```
Output: `installer_out\AnonimizzatorePII-Setup.exe` — installer per-utente (niente admin),
con shortcut nel menu Start e disinstallazione.

## Note
- **Dimensione**: la cartella/installer è di alcuni GB (PyTorch + modello incluso). Normale.
- **Rigenerare col modello definitivo**: il modello è impacchettato dalla cartella versionata
  `models\rizzo-pii-0.3B-v{VERSION}\` (vedi `datas` in `build.spec` / `build_sidecar.spec`; build
  attuale **v1.5.0**). Quando riaddestri una nuova versione, aggiorna quel path negli spec e rifai
  il passo 2 (e 3). Per provare senza modello si può puntare a `models\pii_model_legacy`.
- **console=True** in `build.spec` mostra una finestra con i log; mettila `False` per nasconderla
  (consigliato solo dopo che tutto funziona).
- **SmartScreen**: un exe non firmato mostra l'avviso "editore sconosciuto". Per la distribuzione
  serve un certificato di code signing.
