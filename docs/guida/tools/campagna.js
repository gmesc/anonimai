// -*- mode: js -*-
/* Campagna di screenshot per la guida di AnonimAI — nell'ordine della guida.
 *
 * Prerequisiti:
 *   1) il server gira:   .venv/bin/python src/app/app.py --port 5011
 *   2) i documenti finti:  .venv/bin/python docs/guida/tools/fixtures.py
 * Lancio:
 *   electron/node_modules/.bin/electron docs/guida/tools/campagna.js
 *
 * Ogni passo e' isolato: se cade, si annota e si continua (riepilogo in fondo).
 * Rilanciare da zero e' piu' sicuro che rifotografare a pezzi.
 */
const path = require('path');
const { app } = require('electron');
const L = require(path.join(__dirname, 'lab.js'));
const {
  pausa, js, clicca, scrivi, attendi, carica, dragEntra, dragEsce, riquadro,
  puntatore, cornice, numeri, scatta, passo, riepilogo, mostraTip,
} = L;

const FIX = path.join(__dirname, 'fixtures');
const ATTO = path.join(FIX, 'atto_esempio.pdf');
const SCAN = path.join(FIX, 'scansione_esempio.pdf');

const TESTO = `Il sottoscritto Mario Rossi, nato a Milano il 12/06/1985, codice fiscale \
RSSMRA85H12F205Z, residente in Via Garibaldi 24, 20121 Milano (MI), email \
m.rossi@studiorossi.it, tel. 333 1234567, dichiara di aver versato la somma di \
EUR 128.500,00 sul conto IBAN IT60X0542811101000000123456 intestato a Edilnord \
Costruzioni S.r.l., con sede in Corso Venezia 8, Milano.`;

/* stato pulito fra un capitolo e l'altro */
const azzera = async () => { await clicca('#clear'); await pausa(400); };

/* aspetta che l'analisi sia finita (DATA valorizzato) */
const analizza = async () => {
  await clicca('#go');
  await attendi('DATA', 180000);
  await pausa(500);
};

(async () => {
  await L.avvia();
  await attendi(`document.getElementById('go')`);
  await js(`localStorage.clear(),applyTheme('chiaro'),applyLang('it'),null`);
  await pausa(300);

  /* ---------- 1. la finestra ---------- */
  await passo('finestra-vuota', async () => {
    await scatta('01-finestra-vuota');
  });

  await passo('topbar-numerata', async () => {
    await numeri([
      { sel: '#modeBtn', n: 1, dove: 'sotto' },
      { sel: '.badge', n: 2, dove: 'sotto' },
      { sel: '#lang', n: 3, dove: 'sotto' },
      { sel: '#thTog', n: 4, dove: 'sotto' },
      { sel: '#tagsBtn', n: 5, dove: 'sotto' },
      { sel: '#gearBtn', n: 6, dove: 'sotto' },
      { sel: '#infoBtn', n: 7, dove: 'sotto' },
    ]);
    await scatta('02-topbar', { clip: { x: 0, y: 0, width: L.W, height: 116 } });
  });

  await passo('due-colonne', async () => {
    await numeri([
      { sel: '#src', n: 1, dove: 'tl' },
      { sel: '#go', n: 2, dove: 'tl' },
      { sel: '#mapSw', n: 3, dove: 'tl' },
      { sel: '#viewPrev', n: 4, dove: 'tl' },
      { sel: '.out .seg-tabs', n: 5, dove: 'tl' },
      { sel: '#copy', n: 6, dove: 'tl' },
    ]);
    await scatta('03-due-colonne');
  });

  /* ---------- 2. il primo giro: un testo incollato ---------- */
  await passo('testo-incollato', async () => {
    await scrivi('#src', TESTO);
    await pausa(200);
    await cornice('#go', { etichetta: 'si parte da qui', dove: 'sopra' });
    await puntatore('#go');
    await scatta('04-testo-incollato');
  });

  await passo('risultato', async () => {
    await analizza();
    await pausa(2200);                       // il toast delle PII trovate se ne va
    await scatta('05-risultato');
  });

  await passo('anteprima-evidenziata', async () => {
    await scatta('06-anteprima-tag', { sel: '.out .bd', margine: 6 });
  });

  await passo('dizionario', async () => {
    await js(`document.getElementById('dictCard').scrollIntoView({block:'center'}),null`);
    await pausa(500);
    await numeri([
      // ancorati al PRIMO elemento di ogni riga: la card parte dal bordo della
      // finestra, un numero messo a sinistra del contenitore finirebbe fuori campo
      { sel: '#meta .stat', n: 1, dove: 'tl' },
      { sel: '#legend .chip', n: 2, dove: 'tl' },
      { sel: '#tablewrap th', n: 3, dove: 'tl' },
    ]);
    await scatta('07-dizionario', { sel: '#dictCard', margine: 44 });
    await js(`window.scrollTo(0,0),null`);
    await pausa(800);                        // lo scroll e' morbido: senza attesa
  });                                        // il ritaglio del passo dopo e' fuori posto

  await passo('tre-viste', async () => {
    await js(`window.scrollTo(0,0),null`);
    await pausa(600);
    await cornice('.out .seg-tabs', { etichetta: 'le tre viste del risultato' });
    await numeri([
      { sel: '#vPrev', n: 1, dove: 'sotto' },
      { sel: '#vText', n: 2, dove: 'sotto' },
      { sel: '#vPdf', n: 3, dove: 'sotto' },
    ]);
    await scatta('08-tre-viste', { clip: { x: 740, y: 12, width: 730, height: 158 } });
  });

  await passo('testo-da-copiare', async () => {
    await js(`setView('text'),null`);
    await pausa(400);
    await scatta('09-testo-da-copiare', { sel: '.out', margine: 4 });
    await js(`setView('prev'),null`);
  });

  /* ---------- 3. i tre bottoni e i loro popup ---------- */
  for (const [n, sel, file] of [
    ['copia', '#copy', '10-tip-copia'],
    ['pdf', '#dlpdf', '11-tip-pdf'],
    ['dizionario', '#dl', '12-tip-dizionario'],
  ]) {
    await passo('popup-' + n, async () => {
      const h = `.htip:has(${sel})`;
      await mostraTip(h);                    // dentro c'e' l'attesa dei 900 ms del popup
      // il ritaglio segue il popup, che sta SOPRA il bottone
      const r = await js(`(()=>{const t=document.querySelector('${h} > .tip').getBoundingClientRect();
        const b=document.querySelector('${h}').getBoundingClientRect();
        return {x:Math.min(t.left,b.left)-16,y:t.top-16,
                width:Math.max(t.right,b.right)-Math.min(t.left,b.left)+32,
                height:b.bottom-t.top+32}})()`);
      await scatta(file, { clip: r });
    });
  }

  /* ---------- 4. un PDF ---------- */
  await passo('drop-overlay', async () => {
    await azzera();
    await dragEntra();
    await pausa(300);
    await scatta('13-drop-overlay');
    await dragEsce();
  });

  await passo('pdf-caricato', async () => {
    await carica(ATTO);
    await attendi('SRC_DOC', 60000);
    await pausa(900);
    await scatta('14-pdf-caricato');
  });

  await passo('due-viste-sorgente', async () => {
    await cornice('#srcTabs', { etichetta: 'Anteprima PDF · Testo', blu: true, dove: 'sotto' });
    await cornice('#fileName', { etichetta: 'il file che hai aperto' });
    await scatta('15-viste-sorgente', { clip: { x: 0, y: 34, width: 745, height: 150 } });
  });

  await passo('zoom', async () => {
    await cornice('#zoomG', { etichetta: '−  livello  +' });
    await puntatore('#zLvl');
    await scatta('16-zoom-barra', { clip: { x: 250, y: 55, width: 490, height: 110 } });
  });

  await passo('zoom-200', async () => {
    await js(`zoomSet(2),null`);
    await pausa(1200);
    await scatta('17-zoom-200');
    await js(`zoomSet(1),null`);
    await pausa(600);
  });

  /* ---------- 5. riquadri manuali ---------- */
  await passo('riquadri-modo', async () => {
    await clicca('#boxBtn');
    await pausa(300);
    await cornice('#boxBtn', { etichetta: 'modalità riquadri attiva' });
    await scatta('18-riquadri-modo', { clip: { x: 0, y: 55, width: 740, height: 140 } });
  });

  await passo('riquadro-firma', async () => {
    // pagina 2: la firma a penna e il timbro tondo
    await js(`(()=>{const v=document.getElementById('pdfSrcView');
      const p=v.querySelector('.pg[data-page="1"]');v.scrollTop=p.offsetTop;return null})()`);
    await pausa(700);
    await riquadro(1, 0.11, 0.43, 0.63, 0.56);
    await pausa(500);
    await scatta('19-riquadro-firma', { sel: '#pdfSrcView', margine: 0 });
  });

  await passo('pdf-censurato', async () => {
    await analizza();
    await js(`setView('pdf'),null`);
    await attendi('OUT_DOC', 300000);
    await pausa(1500);
    await js(`(()=>{const v=document.getElementById('pdfOutView');
      const p=v.querySelector('.pg[data-page="1"]');if(p)v.scrollTop=p.offsetTop;return null})()`);
    await pausa(900);
    await scatta('20-pdf-censurato');
  });

  /* l'avviso: valori che la redazione non ha potuto togliere. Il toast dura 9 s
     ma e' gia' passato: lo si richiama dai dati del documento appena costruito. */
  await passo('avviso-residui', async () => {
    await js(`(()=>{const d=OUT_DOC;if(d&&d.residual+d.skipped>0)
      toast(T[L].t_pdf_warn(d.residual,d.skipped),false,9000);return null})()`);
    await pausa(700);
    await scatta('38-avviso-residui', { clip: { x: 200, y: 780, width: 1070, height: 176 } });
    await js(`toast('',true,1),null`);
    await pausa(300);
  });

  await passo('confronto-prima-dopo', async () => {
    await js(`(()=>{const v=document.getElementById('pdfSrcView');
      v.scrollTop=0;matchScroll(document.getElementById('pdfOutView'),v);return null})()`);
    await pausa(900);
    await scatta('21-prima-dopo', { clip: { x: 0, y: 100, width: L.W, height: 700 } });
  });

  /* ---------- 6. scansione + OCR ---------- */
  await passo('scansione', async () => {
    await azzera();
    await carica(SCAN);
    await attendi('SRC_DOC', 90000);
    await pausa(900);
    await js(`setSrcView('text'),null`);
    await pausa(300);
    await cornice('#src', { etichetta: 'testo estratto dai pixel: è l’OCR' });
    await scatta('22-ocr-testo', { clip: { x: 0, y: 55, width: 740, height: 500 } });
  });

  await passo('scansione-anonimizzata', async () => {
    await js(`setSrcView('pdf'),null`);
    await analizza();
    await scatta('23-ocr-risultato');
  });

  /* ---------- 7. tag e termini personali ---------- */
  await passo('tag-modale', async () => {
    await azzera();
    await js(`openTags(),null`);
    await pausa(700);
    await scatta('24-tag-modale');
  });

  await passo('tag-riga', async () => {
    await cornice('.tg-row', { etichetta: 'spunta = viene sostituito' });
    await scatta('25-tag-riga', { sel: '.tg-list', margine: 6 });
  });

  await passo('termini-personali', async () => {
    await js(`document.querySelector('.ct-head').scrollIntoView({block:'center'}),null`);
    await pausa(400);
    await scrivi('#ctVal', 'Istituto Elvetico');
    await scrivi('#ctTag', 'ORG');
    await pausa(200);
    await js(`addTerm(),null`);
    await pausa(400);
    await cornice('.ct-list', { etichetta: 'salvato su questo computer (prefs.json)', dove: 'sotto' });
    await scatta('26-termini-personali', { sel: '.ct-add', margine: 90 });
    await js(`closeTags(),null`);
    await pausa(400);
  });

  /* ---------- 8. dizionario reversibile ---------- */
  await passo('switch-dizionario', async () => {
    await L.mostraTip('#mapSw');
    await cornice('#mapSw', { etichetta: 'ATTIVO = si potrà ripristinare' });
    await scatta('27-switch-dizionario', { clip: { x: 0, y: 600, width: 760, height: 356 } });
  });

  await passo('dizionario-off', async () => {
    await js(`toggleMapping(),null`);
    await pausa(700);
    await scatta('28-dizionario-off', { clip: { x: 120, y: 600, width: 1230, height: 356 } });
    await js(`toggleMapping(),null`);
    await pausa(500);
  });

  /* ---------- 9. deanonimizza ---------- */
  await passo('deanonimizza', async () => {
    await scrivi('#src', TESTO);
    await analizza();
    await js(`toggleMode(),null`);
    await pausa(400);
    await scrivi('#rin', 'Gentile [FULLNAME_1], confermiamo il bonifico di [AMOUNT_1] '
      + 'sull’IBAN [IBAN_1]. Le risponderemo all’indirizzo [EMAIL_1].');
    await pausa(200);
    await cornice('#modeBtn', { etichetta: 'click sul 🕵️ = cambia modalità', blu: true });
    await scatta('29-deanonimizza');
  });

  await passo('ripristinato', async () => {
    await clicca('#rev');
    await pausa(700);
    await scatta('30-ripristinato', { clip: { x: 0, y: 150, width: L.W, height: 560 } });
    await js(`toggleMode(),null`);
    await pausa(300);
  });

  /* ---------- 10. impostazioni ---------- */
  for (const [tab, file] of [['server', '31-set-server'], ['how', '32-set-come'],
                             ['sec', '33-set-sicurezza'], ['cred', '34-set-crediti']]) {
    await passo('impostazioni-' + tab, async () => {
      await js(`openConfig(),null`);
      await pausa(600);
      await js(`setSettingsTab(${JSON.stringify(tab)}),null`);
      await pausa(400);
      await scatta(file, { sel: '.cfg-card', margine: 10 });
      await js(`closeConfig(),null`);
      await pausa(200);
    });
  }

  /* ---------- 11. tema e lingua ---------- */
  await passo('tema-scuro', async () => {
    await js(`applyTheme('scuro'),null`);
    await pausa(700);
    await scatta('35-tema-scuro');
    await js(`applyTheme('chiaro'),null`);
    await pausa(400);
  });

  await passo('lingua-en', async () => {
    await js(`applyLang('en'),null`);
    await pausa(500);
    await scatta('36-lingua-en', { clip: { x: 0, y: 0, width: L.W, height: 200 } });
    await js(`applyLang('it'),null`);
    await pausa(300);
  });

  await passo('avviso-sviluppo', async () => {
    await js(`document.getElementById('infoBtn').classList.add('open'),null`);
    await pausa(400);
    await scatta('37-avviso', { clip: { x: 950, y: 0, width: 520, height: 320 } });
    await js(`document.getElementById('infoBtn').classList.remove('open'),null`);
  });

  const ko = riepilogo();
  app.quit();
  process.exitCode = ko ? 1 : 0;
})().catch(e => { console.error(e); app.quit(); process.exitCode = 1; });
