# GUIDA-ARCHITETTO — AnonimAI

> **A chi serve questo documento.** A chi riceve un braindump dell'utente e deve trasformarlo
> in un piano di implementazione: un agente, una skill (`/architetto`), o un collaboratore
> nuovo. Raccoglie ciò che cambia lentamente: filosofia, invarianti, mappa, vocabolario,
> processo, trappole.
> **La regola di lettura**: questo documento dice *come si costruisce qui*; **a che punto
> siamo** lo dicono [docs/CHANGELOG.md](docs/CHANGELOG.md), le issue GitHub e
> [CLAUDE.md](CLAUDE.md) (dettaglio operativo per gli agenti). Se sembrano in conflitto, ha
> ragione il documento più recente.
> **La regola di manutenzione**: si aggiorna quando cambia un invariante o la mappa — di rado,
> mai per registrare lo stato di una sessione.

## 1. Che cos'è il progetto

**AnonimAI** (già rizzo-pii) è un anonimizzatore di PII per testi italiani che gira **interamente in locale**:
un modello mmBERT da ~0,3B (token classification, 22 tag + 1 solo-regex) affiancato da una rete
regex+checksum, dentro un'app Flask con UI, distribuita come app desktop (Tauri + sidecar
PyInstaller), container Docker o server. Il flusso che giustifica tutto:
**anonimizza in locale → placeholder + dizionario reversibile locale → LLM di frontiera →
ripristino in locale**. I dati veri non lasciano mai la macchina.

Per chi: studi legali, commercialisti, notai — e, come impiego dichiarato dall'utente, **medici
e istituti scolastici del Canton Ticino**. Repo **pubblico e open source** (sorgente MIT, binari
rilasciati AGPL-3.0), con contributori esterni e un dataset comunitario su Hugging Face.

Le tre proprietà che lo definiscono più di ogni funzione:

1. **La privacy è il prodotto**: ogni scelta tecnica (offline, in-memory, dizionario locale) è
   subordinata a «i dati veri non escono».
2. **Onestà prima di cortesia**: quando l'anonimizzazione non può essere garantita, l'app
   restituisce un errore o un avviso, mai un risultato che *sembra* anonimizzato.
3. **Due nature in un repo**: la pipeline di training (dati sintetici, GPU, W&B) e l'app di
   anonimizzazione (CPU, offline) convivono ma non si importano a vicenda.

## 2. Vocabolario

| Termine | Che cos'è | Da non confondere |
|---|---|---|
| **tag** | Una delle 22 categorie PII del modello (`FULLNAME`, `IBAN`…) + `URL` | `URL` è il 23°, **solo-regex**: il modello non lo conosce |
| **placeholder** | Il segnaposto numerato nel testo anonimizzato: `[FULLNAME_1]` | La numerazione resta anche a dizionario spento: due `[FULLNAME_1]` = stesso soggetto |
| **dizionario / mapping** | La mappa placeholder→valore che rende reversibile l'anonimizzazione | **Non viaggia mai sulla rete** (invariante 2); «mapping disattivato» = anonimizzazione definitiva |
| **rete regex+checksum** | I detector di `detectors.py` che affiancano il modello | Il checksum **vince** sul modello, non lo integra soltanto |
| **redazione** | Rimozione vera dal content stream (`apply_redactions`) + placeholder al posto del valore | NON è disegnare un rettangolo sopra il testo |
| **residui** | Valori ancora leggibili nell'output dopo la redazione (verifica finale) | ≠ **saltati**: valori mai cercati perché troppo corti/ambigui. Entrambi → avviso in UI |
| **tag esclusi** | Tag rilevati ma **non** sostituiti (restano in chiaro, scelta dell'utente) | Non è «tag disattivato nel modello»: la rilevazione avviene comunque |
| **scansione** | PDF di sole immagini (foto di documenti): niente layer testuale | Un PDF «nativo» può comunque contenere immagini con testo (carta intestata) |
| **sidecar** | Il backend Flask impacchettato (PyInstaller) lanciato dalla finestra Tauri | `serve.py` è headless; `desktop_app.py` è l'entry legacy che apre il browser |
| **sintetico** | Dati generati: template LLM + valori iniettati dal codice | Mai scritto dall'LLM il valore sensibile (invariante 3) |
| **subset / full** | Le due modalità di `train_pii.py`: smoke ~3 min vs run grande versionato | Il subset non produce un modello utilizzabile |
| **validation reale** | `validation_real.jsonl`, unica validation, solo italiano | I sintetici di training non ci entrano mai (leakage) |

## 3. Gli invarianti

1. **Tutto in locale, offline a runtime.** Niente chiamate di rete, niente CDN, niente
   telemetria nell'app. È la ragione d'esistere del progetto; una dipendenza online è un bug di
   architettura anche se funziona. (Per questo il render PDF è server-side PyMuPDF: dentro
   Tauri non c'è viewer affidabile e pdf.js da CDN è vietato.)
2. **Il dizionario non viaggia sulla rete in nessuna direzione.** `/pdf` ricostruisce la mappa
   internamente e la lascia morire con la richiesta; a dizionario spento la risposta perde
   anche il campo `t` dei segmenti, o si ricostruirebbe dal payload.
3. **LLM autore, codice etichettatore.** L'LLM scrive solo prosa con segnaposto `{SLOT}`; i
   valori (con checksum validi) li inietta il codice. Dà label BIO esatte, checksum
   matematicamente giusti e — soprattutto — **nessuna PII reale scritta da un LLM, mai**.
4. **I moduli dell'app si testano senza il modello.** `pdf_export.py` e `detectors.py` lavorano
   su bytes/stringhe, zero import di torch/transformers: la suite `tests/` gira in secondi
   ovunque. Logica nuova dell'app va messa dove resta testabile in isolamento.
5. **Meglio un errore che un PDF «anonimizzato» che non lo è.** Se nel PDF non si trova nessuna
   occorrenza → 422, non un file intatto spacciato per redatto; residui e saltati si contano,
   si verificano sull'output e si dichiarano all'utente (header `X-PII-*`, toast).
6. **I documenti vivono in memoria e muoiono col processo.** Lo store `_DOCS` è una LRU in RAM
   (`MAX_DOCS=6`), mai su disco: un documento caricato vale quanto i suoi dati.
7. **Il matching nel PDF è char-preciso con confini di parola.** Indice per carattere da
   `rawdict` + regex ancorate `(?<!\w)…(?!\w)`, tolleranza alla sillabazione. Guasto d'origine:
   «DE» redatto dentro «CORDELLA». L'unica eccezione alle ancore (punteggiatura ai bordi)
   richiede ≥ 4 alfanumerici, o «.it» matcherebbe dentro ogni parola.
8. **File grezzi intatti; la tassonomia si cambia solo al caricamento.** `TAG_MAP` /
   `DROP_TYPES` / `normalize_labels()` in `train_pii.py` rimappano in lettura: mai riscrivere i
   dataset su disco per cambiare i tag.
9. **I modelli sono versionati e non si sovrascrivono.** Ogni run grande → cartella
   `models/rizzo-pii-0.3B-v{VERSION}/` + riga in `models/registry.json`. La storia dei run è un
   dato del progetto.
10. **Path assoluti risolti da `__file__`, UTF-8 forzato.** Ogni script gira da qualsiasi CWD e
    stampa UTF-8 anche su Windows (i log PowerShell rediretti sono UTF-16: guasto pagato).
11. **`config.json` e `prefs.json` restano file separati.** Tauri riscrive `config.json` per
    intero quando cambia la porta: qualunque altra chiave lì dentro verrebbe cancellata.
12. **La porta si controlla prima di caricare il modello.** Pre-bind check + exit code 76,
    riconosciuto dallo splash Tauri: mai far pagare secondi di caricamento per poi fallire sul
    bind. (E 5000 su macOS è AirPlay: il default è 5005.)

## 4. Mappa del codice

```
src/data_pipeline/   generazione dati: template LLM → sintetico → augment → DeepMount → validation → subset
src/training/        train_pii.py (fusione fonti, run versionati, W&B) · evaluate/test
src/inspect/         ispezione read-only; validate_checksums.py è il blueprint della rete regex
src/app/             l'app: app.py (server Flask + UI embedded, ~2000 righe) · detectors.py
                     (rete regex+checksum, senza torch) · pdf_export.py (redazione/ricostruzione
                     PDF, senza torch) · server_config.py (host/porta/prefs condivisi con Tauri)
                     · serve.py (entry headless per il sidecar) · desktop_app.py (legacy)
tauri/               finestra nativa; lancia il sidecar, gestisce exit 76 e lo splash
tests/               pytest/unittest, girano SENZA modello (invariante 4)
docs/                BUILD, CHANGELOG (con motivazioni), DATASET, TASSONOMIA_TAG, TRAINING, FORMATO_DATI
scripts/             utilità di build/release
report/              il technical report (Typst + PDF) e le immagini della mascotte
```

L'UI non ha file propri: HTML/CSS/JS vivono dentro `app.py`. Le modifiche di interfaccia si
fanno lì.

## 5. Mappa dei dati

| Dove | Che cosa | Di chi è |
|---|---|---|
| `dataset/` (gitignored) | fonti e sintetici | della pipeline: rigenerabile dagli script |
| `models/` (gitignored) | modelli versionati + `registry.json` | storico dei run: non si sovrascrive (inv. 9) |
| `experiments/`, `wandb/` (gitignored) | artefatti dei run | della pipeline |
| Config dir per-OS (`%LOCALAPPDATA%\anonimai`, `~/Library/Application Support/anonimai`, `~/.local/share/anonimai`; migrazione automatica dal vecchio nome `rizzo-pii`) | `config.json`, `prefs.json`, `backend.log` | dell'installazione utente; condivisa Python↔Tauri (inv. 11) |
| RAM (`_DOCS`) | documenti caricati e loro render | della sessione: mai su disco (inv. 6) |
| `.env` (gitignorato) | chiavi W&B / Gemini | dell'utente: mai committare |
| HF `rizzoaiacademy/*` | modello pubblicato + dataset comunitario | pubblici: ci finisce solo materiale sintetico/verificato |

## 6. Come si verifica

```bash
python -m pytest tests/ -x            # suite app (secondi, senza modello)
python src/app/smoke_pdf_export.py    # smoke della redazione PDF
python src/app/smoke_app.py           # smoke del server
python src/training/train_pii.py --type subset   # smoke della pipeline (~3 min, GPU)
```

Condizioni al contorno che falsano le misure: porta 5005 occupata (l'app esce con 76, non è un
crash); su macOS la 5000 è AirPlay; i log rediretti da PowerShell sono UTF-16 (leggerli con
`Get-Content`, non con tool che assumono UTF-8); l'eval **non** gira durante il training — le
metriche arrivano alla fine.

Filosofia: le prove automatiche coprono la meccanica (checksum, confini di parola, redazione);
la qualità del modello si giudica su run versionati con metriche entity-level calcolate a mano
(niente seqeval, non compila). I gesti dell'UI si provano a mano.

## 7. Come si lavora

- Ramo unico `main`; i contributi esterni arrivano come PR GitHub e si mergiano da lì.
- Commit **conventional, in italiano, minuscoli**: `fix(app): …`, `docs(site): …`,
  `ci(windows): …`, `release: …`. Il soggetto dice il comportamento, non il file.
- Le decisioni con motivazione vanno in `docs/CHANGELOG.md` (voci datate, più recente in alto,
  col *perché*): è il documento di stato del progetto.
- Le release nascono dal push di un tag `v*` (workflow CI); gli installer si costruiscono su
  runner GitHub. I numeri di versione app (`APP_VERSION`) e modello (`MODEL_VERSION`) sono
  indipendenti.
- Il pubblico parla per issue (spesso in italiano): un braindump dell'utente va incrociato con
  le issue aperte — spesso la richiesta esiste già, con contesto in più.

## 8. Trappole permanenti

- ⚠️ **L'ambiente GPU è fragile e documentato in CLAUDE.md** (cu128 per Blackwell,
  torchvision da disinstallare, `dataloader_num_workers=0` su Windows, VRAM condivisa col
  desktop). Non «sistemare» quelle scelte: sono cicatrici, non sviste.
- ⚠️ **`set_metadata` aggiorna solo le chiavi passate**: per azzerare i metadati vanno azzerate
  tutte esplicitamente, o autore/titolo originali sopravvivono nel file redatto.
- ⚠️ **Le PII vivono anche fuori dal testo di pagina**: annotazioni, campi modulo, segnalibri,
  allegati, XMP. `apply_redactions()` da solo non li tocca; `pdf_export` li ripulisce uno a
  uno. Ogni nuova superficie PDF va passata alla stessa lente.
- ⚠️ **I valori corti sono pericolosi in entrambe le direzioni**: cercarli ovunque devasta il
  documento, saltarli li lascia in chiaro. La soglia (< 2 alfanumerici, o 2 sole cifre) e
  l'avviso all'utente sono il compromesso pagato.
- ⚠️ **Il campo upload si chiama `pdf` per storia** (`file` è l'alias): l'UI vecchia lo usa
  ancora. Non rinominarlo senza passare da entrambi.
- ⚠️ **`_merge()` era quadratico** (100 s su un documento lungo): le strutture su testi lunghi
  si misurano prima di fidarsi (changelog 2026-08-03).

## 9. Protocollo per un braindump

1. Leggere: questa guida → `docs/CHANGELOG.md` (voci recenti) → issue GitHub correlate →
   `CLAUDE.md` per il dettaglio operativo dell'area toccata.
2. Tradurre il braindump nel vocabolario (§2) prima di ragionare; le ambiguità vere sono bivi
   da utente.
3. Passare il piano contro gli invarianti (§3), citandoli per numero. Domande-filtro del
   progetto: *questo dato esce dalla macchina?* (inv. 1-2) — *si può testare senza il
   modello?* (inv. 4) — *che cosa vede l'utente quando NON funziona?* (inv. 5) — *tocca disco
   che oggi non tocca?* (inv. 6) — *un LLM vede mai un valore vero?* (inv. 3).
4. Il piano dichiara: file toccati, dove vive la logica nuova e perché, prove, gesti di
   verifica a mano, non-obiettivi, decisioni prese.
5. Chiedere all'utente solo per i bivi materiali; tutto il resto si decide e si dichiara.
6. Lavoro finito = suite verdi + gesti consegnati + `docs/CHANGELOG.md` aggiornato con la
   motivazione + questa guida ritoccata **solo** se è cambiato un invariante o la mappa.

## 10. Fonti vive

| Documento | Che cosa dice | Affidabilità |
|---|---|---|
| [CLAUDE.md](CLAUDE.md) | guida operativa per agenti: ambiente, comandi, parametri, dettaglio moduli | la più densa; aggiornata insieme al codice |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | le decisioni, datate e motivate | il documento di stato |
| Issue GitHub | richieste e bug dal pubblico | da incrociare sempre con un braindump |
| [README.md](README.md) | vetrina pubblica: pitch, download, numeri del modello | curata; i numeri fotografano l'ultima release, non `main` |
| [docs/TASSONOMIA_TAG.md](docs/TASSONOMIA_TAG.md) · [docs/DATASET.md](docs/DATASET.md) · [docs/TRAINING.md](docs/TRAINING.md) · [docs/FORMATO_DATI.md](docs/FORMATO_DATI.md) · [docs/BUILD.md](docs/BUILD.md) | i riferimenti specialistici per area | stabili |
| [CONTRIBUTING.md](CONTRIBUTING.md) | come contribuisce il pubblico (codice e dataset HF) | stabile |
