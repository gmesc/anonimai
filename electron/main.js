// AnonimAI — guscio desktop Electron.
//
// Fa lo stesso mestiere della finestra Tauri (tauri/src-tauri/src/lib.rs), in
// versione da banco di prova: lancia il backend Flask come processo figlio,
// aspetta che risponda su /health e poi ci punta la finestra. Alla chiusura
// il figlio muore con lei.
//
// Tauri resta il guscio di distribuzione (installer firmati, sidecar
// PyInstaller); questo serve a provare l'app con `npm start`, senza Rust e
// senza impacchettare niente: il backend gira dal sorgente, con un Python
// del sistema.
//
//   npm install && npm start        (dalla radice della repo)

const { app, BrowserWindow, shell, dialog } = require('electron');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const HOST = process.env.PII_HOST || '127.0.0.1';
const PORT = parseInt(process.env.PII_PORT || '5005', 10);
const URL_APP = `http://${HOST}:${PORT}`;
const EXIT_PORT_CONFLICT = 76;   // lo stesso codice che riconosce Tauri
const ICONA = path.join(ROOT, 'src', 'app', 'assets', 'detective.png');  // OpenMoji 1F575
const AVVIO_MAX_MS = 180000;     // il primo caricamento del modello su CPU e' lento

let win = null;
let backend = null;

/* Il Python con cui far girare il backend. PII_PYTHON vince su tutto: e' la
   via d'uscita quando l'ambiente sta altrove. */
function trovaPython() {
  const cand = [
    process.env.PII_PYTHON,
    path.join(ROOT, '.venv', 'bin', 'python'),
    path.join(ROOT, '.venv', 'Scripts', 'python.exe'),
    path.join(ROOT, 'venv', 'bin', 'python'),
    path.join(ROOT, 'build_env', 'Scripts', 'python.exe'),
  ].filter(Boolean);
  for (const p of cand) if (fs.existsSync(p)) return p;
  return process.platform === 'win32' ? 'python' : 'python3';
}

/* Messaggio nello splash: niente preload e niente IPC per due righe di testo. */
function stato(msg, errore = false) {
  if (!win || win.isDestroyed()) return;
  win.webContents.executeJavaScript(
    `window.stato && window.stato(${JSON.stringify(msg)}, ${errore});`
  ).catch(() => {});
}

/* Il backend risponde? /health e' readiness senza inferenza: 200 = modello
   caricato, 503 = server su ma modello ancora in caricamento. */
async function pronto() {
  try {
    const r = await fetch(`${URL_APP}/health`, { signal: AbortSignal.timeout(2000) });
    return r.status === 200;
  } catch (e) {
    return false;
  }
}

function avviaBackend() {
  const py = trovaPython();
  const script = path.join(ROOT, 'src', 'app', 'serve.py');
  if (!fs.existsSync(script)) {
    stato(`Non trovo ${script}`, true);
    return;
  }
  backend = spawn(py, [script], {
    cwd: ROOT,
    env: { ...process.env, PII_HOST: HOST, PII_PORT: String(PORT) },
  });
  // serve.py devia i suoi print sul log dell'app: qui restano gli errori duri
  backend.stdout.on('data', d => process.stdout.write(`[backend] ${d}`));
  backend.stderr.on('data', d => process.stderr.write(`[backend] ${d}`));

  backend.on('error', err => {
    stato(`Python non eseguibile (${py}): ${err.message}. `
        + 'Crea l\'ambiente con  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt  '
        + 'oppure indica il tuo con PII_PYTHON.', true);
  });

  backend.on('exit', code => {
    backend = null;
    if (code === EXIT_PORT_CONFLICT) {
      stato(`La porta ${PORT} e' occupata. Chiudi chi la usa, oppure riparti con `
          + `PII_PORT=5006 npm start`, true);
    } else if (code !== 0 && code !== null) {
      // il log lo scrive serve.py: ~/anonimai/backend.log su macOS e Linux,
      // %LOCALAPPDATA%\anonimai\backend.log su Windows (verificato, non dedotto)
      const log = process.platform === 'win32'
        ? '%LOCALAPPDATA%\\anonimai\\backend.log'
        : path.join(require('os').homedir(), 'anonimai', 'backend.log');
      stato(`Il backend e' uscito con codice ${code}. Il log e' in ${log}`, true);
    }
  });
}

/* Attesa: si ferma sia quando il server risponde, sia quando il figlio muore —
   senza il secondo caso lo splash girerebbe a vuoto per tre minuti. */
async function attendiEApri() {
  const scadenza = Date.now() + AVVIO_MAX_MS;
  while (Date.now() < scadenza) {
    if (await pronto()) {
      if (win && !win.isDestroyed()) win.loadURL(URL_APP);
      return;
    }
    if (!backend) return;                      // uscito: il messaggio l'ha gia' scritto exit
    await new Promise(r => setTimeout(r, 500));
  }
  stato('Il backend non ha risposto in tempo. Controlla il log e riprova.', true);
}

function creaFinestra() {
  win = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    title: 'AnonimAI',
    backgroundColor: '#fbfbfa',
    icon: ICONA,
    webPreferences: { nodeIntegration: false, contextIsolation: true },
  });
  win.loadFile(path.join(__dirname, 'splash.html'));
  // i link esterni (repo, Hugging Face nei Crediti) vanno al browser di
  // sistema: dentro la finestra dell'app non ci si esce piu'
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  win.on('closed', () => { win = null; });
}

app.whenReady().then(() => {
  // su macOS BrowserWindow.icon viene ignorato: l'icona del Dock si mette qui,
  // o resta quella di Electron e l'app sembra di un altro
  if (process.platform === 'darwin' && app.dock) {
    try { app.dock.setIcon(ICONA); } catch (e) {}
  }
  creaFinestra();
  avviaBackend();
  attendiEApri();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) { creaFinestra(); attendiEApri(); }
  });
});

/* Il figlio non sopravvive alla finestra: un backend orfano tiene la porta e
   il modello in RAM, e al riavvio successivo si becca l'errore 76. */
function fermaBackend() {
  if (backend) { try { backend.kill(); } catch (e) {} backend = null; }
}
app.on('window-all-closed', () => { fermaBackend(); app.quit(); });
app.on('before-quit', fermaBackend);
process.on('exit', fermaBackend);
