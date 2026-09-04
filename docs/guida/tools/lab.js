// -*- mode: js -*-
/* Laboratorio di screenshot per la guida di AnonimAI.
   Gira dentro Electron (gia' nel repo: electron/node_modules) e pilota la UI
   VERA servita da src/app/app.py. Nessuna dipendenza nuova.

   Perche' Electron e non il browser: qui possiamo salvare i PNG su disco
   (webContents.capturePage) e ritagliare una regione precisa. */
const { app, BrowserWindow } = require('electron');
const fs = require('fs');
const path = require('path');

const URL_APP = process.env.GUIDA_URL || 'http://127.0.0.1:5011';
const IMG = path.resolve(__dirname, '..', 'img');
// misura del portatile del lettore (MacBook Air 13"), non del monitor di chi scatta
const W = 1470, H = 956;

let win = null;

async function avvia() {
  await app.whenReady();
  win = new BrowserWindow({
    width: W, height: H, useContentSize: true, show: true,
    backgroundColor: '#ffffff',
    webPreferences: { backgroundThrottling: false },
  });
  await win.loadURL(URL_APP);
  await pausa(600);
  await stileLab();
  return win;
}

const pausa = ms => new Promise(r => setTimeout(r, ms));
const js = code => win.webContents.executeJavaScript(code, true);

/* CSS del laboratorio: cursore finto, cornici, numeri cerchiati, bande.
   Vive solo durante la campagna, non tocca l'app. */
function stileLab() {
  return js(`(()=>{const s=document.createElement('style');s.id='lab-css';s.textContent=\`
  .lab-cur{position:fixed;z-index:99999;width:26px;height:34px;pointer-events:none;
    filter:drop-shadow(0 2px 3px rgba(0,0,0,.45))}
  .lab-ring{position:fixed;z-index:99998;width:44px;height:44px;margin:-22px 0 0 -22px;
    border:3px solid #f5b301;border-radius:50%;pointer-events:none;
    box-shadow:0 0 0 3px rgba(245,179,1,.28)}
  .lab-box{position:fixed;z-index:99997;border:3px solid #f5b301;pointer-events:none;
    box-shadow:0 0 0 9999px rgba(0,0,0,0)}
  .lab-box.blu{border-color:#2f6fed}
  .lab-lab{position:fixed;z-index:99999;background:#f5b301;color:#20242c;font:700 13px/1.5
    -apple-system,system-ui,sans-serif;padding:2px 8px;pointer-events:none;white-space:nowrap}
  .lab-lab.blu{background:#2f6fed;color:#fff}
  .lab-n{position:fixed;z-index:99999;width:26px;height:26px;border-radius:50%;
    background:#2f6fed;color:#fff;font:700 15px/26px -apple-system,system-ui,sans-serif;
    text-align:center;pointer-events:none;box-shadow:0 1px 4px rgba(0,0,0,.35)}
  .lab-banda{position:fixed;z-index:99990;background:#fff;pointer-events:none}
  \`;document.head.appendChild(s);})()`);
}

/* --- azioni sulla pagina ------------------------------------------------- */
const clicca = sel => js(`document.querySelector(${JSON.stringify(sel)}).click(),null`);
const scrivi = (sel, txt) => js(
  `(()=>{const e=document.querySelector(${JSON.stringify(sel)});e.value=${JSON.stringify(txt)};
    e.dispatchEvent(new Event('input',{bubbles:true}));
    e.dispatchEvent(new Event('change',{bubbles:true}));return null})()`);
const val = sel => js(`document.querySelector(${JSON.stringify(sel)}).value`);
const esiste = sel => js(`!!document.querySelector(${JSON.stringify(sel)})`);

/* attende che una condizione JS diventi vera (niente sleep a caso) */
async function attendi(expr, ms = 60000, ogni = 250) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    if (await js(`!!(${expr})`)) return true;
    await pausa(ogni);
  }
  throw new Error('timeout attendendo: ' + expr);
}

/* Carica un file come farebbe l'utente: costruisce un File vero nella pagina e
   passa dai gestori dell'app (onFile / drop), non da una scorciatoia interna. */
async function carica(file, { drop = false } = {}) {
  const b64 = fs.readFileSync(file).toString('base64');
  const nome = path.basename(file);
  await js(`(async()=>{
    const bin=Uint8Array.from(atob(${JSON.stringify(b64)}),c=>c.charCodeAt(0));
    const f=new File([bin],${JSON.stringify(nome)},{type:'application/pdf'});
    const dt=new DataTransfer();dt.items.add(f);
    document.getElementById('pdf').files=dt.files;
    ${drop ? `window.dispatchEvent(new DragEvent('drop',{dataTransfer:dt,bubbles:true}));`
           : `onFile(f);`}
    return null})()`);
}

/* L'overlay del drag&drop: serve un dragenter con dataTransfer che contiene Files */
const dragEntra = () => js(`(()=>{const dt=new DataTransfer();
  dt.items.add(new File([new Uint8Array(4)],'atto.pdf',{type:'application/pdf'}));
  window.dispatchEvent(new DragEvent('dragenter',{dataTransfer:dt,bubbles:true}));return null})()`);
const dragEsce = () => js(`(()=>{DRAGN=0;document.getElementById('dropOverlay').classList.remove('on');return null})()`);

/* Riquadri manuali: la UI li disegna col mouse. Qui si iniettano le stesse
   frazioni 0-1 che il mouse produrrebbe, passando dalle funzioni dell'app. */
const riquadro = (page, x0, y0, x1, y1) => js(
  `(()=>{BOXES.push({page:${page},x0:${x0},y0:${y0},x1:${x1},y1:${y1}});boxesChanged();return null})()`);

/* --- segni sopra la pagina ----------------------------------------------- */
const CUR = `<svg viewBox="0 0 24 32" xmlns="http://www.w3.org/2000/svg"><path d="M3 2l16 12-7 1 4 8-3 1.5-4-8-6 4z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>`;

async function puntatore(sel, { dx = 0.5, dy = 0.6, anello = true } = {}) {
  await js(`(()=>{const r=document.querySelector(${JSON.stringify(sel)}).getBoundingClientRect();
    const x=r.left+r.width*${dx}, y=r.top+r.height*${dy};
    ${anello ? `const a=document.createElement('div');a.className='lab-ring';
      a.style.left=x+'px';a.style.top=y+'px';document.body.appendChild(a);` : ''}
    const c=document.createElement('div');c.className='lab-cur';
    c.style.left=x+'px';c.style.top=y+'px';c.innerHTML=${JSON.stringify(CUR)};
    document.body.appendChild(c);return null})()`);
}

async function cornice(sel, { etichetta = '', blu = false, dove = 'sopra', pad = 4 } = {}) {
  await js(`(()=>{const el=document.querySelector(${JSON.stringify(sel)});
    if(!el)return null;const r=el.getBoundingClientRect();const p=${pad};
    const b=document.createElement('div');b.className='lab-box${blu ? ' blu' : ''}';
    b.style.left=(r.left-p)+'px';b.style.top=(r.top-p)+'px';
    b.style.width=(r.width+2*p)+'px';b.style.height=(r.height+2*p)+'px';
    document.body.appendChild(b);
    const t=${JSON.stringify(etichetta)};
    if(t){const l=document.createElement('div');l.className='lab-lab${blu ? ' blu' : ''}';
      l.textContent=t;l.style.left=(r.left-p)+'px';document.body.appendChild(l);
      const lh=l.getBoundingClientRect().height;
      l.style.top=(${JSON.stringify(dove)}==='sotto'?r.bottom+p:r.top-p-lh)+'px';}
    return null})()`);
}

/* numeri cerchiati: [{sel, n, dove:'tl'|'tr'|'bl'|'br'|'sx'}] */
async function numeri(lista) {
  await js(`(()=>{const L=${JSON.stringify(lista)};
    for(const it of L){const el=document.querySelector(it.sel);if(!el)continue;
      const r=el.getBoundingClientRect();const d=document.createElement('div');
      d.className='lab-n';d.textContent=it.n;
      const dove=it.dove||'tl';
      let x=r.left-13,y=r.top-13;
      if(dove==='tr'){x=r.right-13;}
      if(dove==='br'){x=r.right-13;y=r.bottom-13;}
      if(dove==='bl'){y=r.bottom-13;}
      if(dove==='sx'){x=r.left-32;y=r.top+r.height/2-13;}
      if(dove==='sotto'){x=r.left+r.width/2-13;y=r.bottom+2;}
      d.style.left=x+'px';d.style.top=y+'px';document.body.appendChild(d);}
    return null})()`);
}

/* fondo bianco sotto i numeri di una barra (altrimenti illeggibili) */
const banda = (sel, alt = 30) => js(
  `(()=>{const r=document.querySelector(${JSON.stringify(sel)}).getBoundingClientRect();
    const b=document.createElement('div');b.className='lab-banda';
    b.style.left='0px';b.style.top=(r.top-${alt})+'px';b.style.width='100%';
    b.style.height='${alt}px';document.body.appendChild(b);return null})()`);

const pulito = () => js(
  `(()=>{document.querySelectorAll('.lab-cur,.lab-ring,.lab-box,.lab-lab,.lab-n,.lab-banda,style.lab-tipcss')
    .forEach(e=>e.remove());
    document.querySelectorAll('[data-lab-tip]').forEach(t=>{t.removeAttribute('data-lab-tip');
      ['opacity','visibility','transform','transition-delay'].forEach(k=>t.style.removeProperty(k));});
    if(document.activeElement&&document.activeElement.blur)document.activeElement.blur();
    return null})()`);

/* --- scatto --------------------------------------------------------------- */
async function scatta(nome, { sel = null, clip = null, margine = 0 } = {}) {
  await pausa(180);
  let rect = null;
  if (sel) {
    const r = await js(`(()=>{const e=document.querySelector(${JSON.stringify(sel)});
      if(!e)return null;const r=e.getBoundingClientRect();
      return {x:r.left,y:r.top,width:r.width,height:r.height}})()`);
    if (!r) throw new Error('selettore non trovato per lo scatto: ' + sel);
    rect = r;
  } else if (clip) rect = clip;
  if (rect) {
    const m = margine;
    rect = {
      x: Math.max(0, Math.round(rect.x - m)), y: Math.max(0, Math.round(rect.y - m)),
      width: Math.round(rect.width + 2 * m), height: Math.round(rect.height + 2 * m),
    };
    rect.width = Math.min(rect.width, W - rect.x);
    rect.height = Math.min(rect.height, H - rect.y);
  }
  const im = rect ? await win.webContents.capturePage(rect) : await win.webContents.capturePage();
  fs.mkdirSync(IMG, { recursive: true });
  const f = path.join(IMG, nome + '.png');
  fs.writeFileSync(f, im.toPNG());
  const s = im.getSize();
  console.log(`  📸 ${nome}.png  ${s.width}×${s.height}`);
  return f;
}

/* un passo della campagna: se cade, si annota e si va avanti */
const ESITI = [];
async function passo(nome, fn) {
  process.stdout.write('▶ ' + nome + '\n');
  try { await fn(); ESITI.push(['ok', nome]); }
  catch (e) { ESITI.push(['KO', nome, e.message]); console.log('  ✖ ' + e.message); }
  try { await pulito(); } catch (e) {}
}

function riepilogo() {
  const ko = ESITI.filter(e => e[0] === 'KO');
  console.log(`\n${ESITI.length - ko.length}/${ESITI.length} passi riusciti`);
  ko.forEach(e => console.log('  ✖ ' + e[1] + ' — ' + e[2]));
  return ko.length;
}

module.exports = { avvia, pausa, js, clicca, scrivi, val, esiste, attendi, carica,
  dragEntra, dragEsce, riquadro, puntatore, cornice, numeri, banda, pulito, scatta,
  passo, riepilogo, IMG, W, H, get win() { return win; } };

/* Il popup d'uso dei bottoni compare in hover dopo 900 ms: l'hover non si
   simula, ma il CSS lo mostra anche in :focus-within. Per gli altri (.infodot,
   solo hover) si forza la visibilita' con una regola del laboratorio: il
   contenuto e' quello vero, cambia solo che cosa lo accende. */
async function mostraTip(selHtip) {
  await js(`(()=>{const e=document.querySelector(${JSON.stringify(selHtip)});
    if(!e)return null;
    const b=e.querySelector('button,[tabindex]');if(b)b.focus();
    const t=e.querySelector('.tip');if(!t)return null;
    t.dataset.labTip='1';
    for(const [k,v] of [['opacity','1'],['visibility','visible'],['transform','none'],
                        ['transition-delay','0s']]) t.style.setProperty(k,v,'important');
    return null})()`);
  // il popup ha una transizione con ritardo (900 ms: e' voluto, non un caso):
  // scattare prima lo fotografa a meta' strada o del tutto invisibile
  await pausa(1400);
}
const nascondiTip = () => js(
  `(()=>{document.querySelectorAll('[data-lab-tip]').forEach(t=>{
    t.removeAttribute('data-lab-tip');
    ['opacity','visibility','transform','transition-delay'].forEach(k=>t.style.removeProperty(k));});
    if(document.activeElement&&document.activeElement.blur)document.activeElement.blur();
    return null})()`);

module.exports.mostraTip = mostraTip;
module.exports.nascondiTip = nascondiTip;
