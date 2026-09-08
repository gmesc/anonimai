# AnonimAI e la protezione dei dati in Svizzera (nLPD) e in Ticino (LPDP)

> **Non è un parere legale.** È la mappa tecnica fra ciò che l'app fa e ciò che le norme
> chiedono, scritta per il titolare del trattamento e per il consulente che deve validarla.
> Un software non è «conforme»: lo è (o non lo è) chi tratta i dati. L'app può essere
> costruita *by design / by default* e togliere al titolare il lavoro che si può togliere.
> Il resto — la valutazione, la documentazione, la rilettura — resta al titolare.
> Data: 4 settembre 2026. Codice di riferimento: `src/app/` del fork `gmesc/anonimai`.

## 1. Quale legge si applica a chi

| Chi usa l'app | Legge | Autorità |
|---|---|---|
| Studio legale, notaio, fiduciaria, medico privato, azienda | **nLPD** federale (RS 235.1, in vigore dal 1° settembre 2023) | IFPDT (Incaricato federale) |
| Cantone, Comuni, scuole pubbliche, enti e istituti di diritto pubblico ticinesi, privati con compiti pubblici delegati, ordini professionali cantonali | **LPDP** cantonale (RL 163.100, del 9 marzo 1987; revisione totale in corso: verificare lo stato alla fonte) | Incaricato cantonale della protezione dei dati |
| Chiunque tratti dati di persone che si trovano nell'UE | **GDPR** in via extraterritoriale, come seconda cornice | — |
| Avvocati, notai, medici, ausiliari | **art. 321 CP** (segreto professionale), sempre, in aggiunta | — |

## 2. Mappa articolo → funzione dell'app → cosa resta al titolare

| Norma | Che cosa chiede | Che cosa fa l'app (verificabile nel codice) | Che cosa resta al titolare |
|---|---|---|---|
| nLPD art. 5 lett. a / c | Definizione di dato personale; «anonimizzato» ≠ «pseudonimizzato» | Col dizionario **attivo** l'output è **pseudonimizzato** (reversibile per chi ha il dizionario). Col dizionario **spento** la chiave non nasce mai: `analyze(mapping_enabled=False)` non costruisce la mappa e toglie il campo `t` dai segmenti | Decidere per ogni flusso se serve la reversibilità. Custodire il dizionario come l'originale |
| nLPD art. 6 (proporzionalità, minimizzazione) | Trattare solo i dati necessari allo scopo | Al fornitore dell'LLM arrivano **solo i segnaposto** (`[FULLNAME_1]`), non i valori; i documenti stanno in RAM (`_DOCS`, LRU 6, **TTL 10 min**) e mai su disco; l'UI li **cancella subito** (`DELETE /doc/<id>`) a «Pulisci», al caricamento di un documento nuovo, alla chiusura della finestra e dopo **7 minuti** di inattività | Non mandare fuori il documento integrale quando basta la versione con segnaposto; rileggere l'output |
| nLPD art. 7 (by design / by default) | Impostazioni predefinite protettive | Server su `127.0.0.1`; nessuna chiamata di rete, telemetria o CDN; dizionario in `sessionStorage` per **default** (muore con la finestra), persistenza solo opt-in **con conferma esplicita**; **svuotamento automatico** della sessione dopo 7 minuti di inattività, con avviso un minuto prima; promemoria del **blocco schermo** al primo avvio e scheda **Buone abitudini** in Impostazioni; anonimizzazione a **priorità di sicurezza** (errore per eccesso: la parola tagliata si maschera intera) | Non esporre il server (`--host 0.0.0.0`) senza accesso controllato; non attivare «ricorda» su macchine condivise |
| nLPD art. 8 (sicurezza dei dati) | Misure tecniche e organizzative adeguate | Redazione **vera** del PDF (`apply_redactions`, annotazioni/widget sotto la redazione eliminati, metadati/XMP/allegati ripuliti); verifica finale dei **residui** con ri-OCR; `422` se nel PDF non si trova nessuna occorrenza; `Cache-Control: no-store` su ogni risposta (niente copie nella cache della WebView) e CSP con `connect-src 'self'`; **credenziale HTTP Basic** (`PII_AUTH="utente:password"` o `--auth`) su tutto tranne `/health` e `/assets` quando il server è esposto, con avviso all'avvio se manca | Disco cifrato; cancellare dizionari e file temporanei a pratica chiusa; backup consapevoli; controllo degli accessi al computer |
| nLPD art. 16-17 (comunicazione all'estero) | Verso Stati con protezione adeguata o con garanzie | L'app **non comunica nulla**: il destinatario estero è il fornitore dell'LLM scelto dal titolare, che riceve solo segnaposto | Verificare la certificazione **Swiss-U.S. DPF** (in vigore dal 15 settembre 2024) o le clausole contrattuali del fornitore; tenerne traccia |
| nLPD art. 12 (registro dei trattamenti, per chi vi è tenuto) | Documentare i trattamenti | Bottone **📋 Rapporto**: JSON senza valori con data, SHA-256 dell'input, conteggi per tag e fonte, tag esclusi, residui/saltati, versioni app e modello | Archiviare il rapporto con la pratica; tenere il registro |
| nLPD art. 22 (valutazione d'impatto) | Per trattamenti a rischio elevato | — | Fare la DPIA a livello di studio/ente per il flusso «documento → LLM esterno», soprattutto con dati sanitari o di minori |
| LPDP (enti pubblici ticinesi) | Base legale, proporzionalità, sicurezza, vigilanza dell'Incaricato cantonale | Le stesse funzioni di cui sopra; il Rapporto serve alla documentazione richiesta all'ente | Verificare la base legale del trattamento; coinvolgere l'Incaricato cantonale per i trattamenti nuovi con IA |
| art. 321 CP | Il segreto non si comunica a terzi | Al terzo (fornitore LLM) arrivano segnaposto: il contenuto protetto **non esce** se l'anonimizzazione è completa | La rilettura prima dell'invio: l'**identificabilità indiretta** (vicenda rara descrita per esteso) non è coperta da nessun rilevatore |
| IFPDT, comunicazione del 9 novembre 2023 | La LPD si applica direttamente ai trattamenti basati su IA | Il modello gira **in locale**: nessun dato serve ad addestrare nulla, nessun fornitore di IA vede l'input | Informare le persone interessate se l'output dell'LLM produce decisioni che le riguardano |

## 3. Che cosa l'app rileva sul dominio svizzero (rete regex + checksum, senza retraining)

| Item | Tag | Certezza |
|---|---|---|
| Numero AVS `756.xxxx.xxxx.xx` | `ID_DOC` | **checksum EAN-13**: un AVS con cifra di controllo sbagliata resta in chiaro (voluto) |
| IDI/UID `CHE-123.456.789` (+ IVA/MWST/TVA) | `PIVA` | **checksum mod-11**; forma inequivocabile → redatto anche senza ✓ |
| IBAN `CH..`/`LI..` | `IBAN` | **mod-97**, compatto e a gruppi |
| Cantoni (nome, «Canton(e) X») | `PROVINCE` | lista chiusa; mai le sigle nude |
| NAP (`CH-6600`, `6600 Locarno`) | `ZIPCODE` | forma + contesto; 19xx/20xx esclusi (anni) → NAP romandi senza `CH-` sfuggono |
| Targa `TI 123456` | `TARGA` | forma (sigla maiuscola + 3-6 cifre) |
| Telefono `+41 91 123 45 67`, `091 123 45 67`, `0041…` | `TELEPHONENUM` | forma |
| Importi `CHF 1'250.00`, `Fr. 12'500.–`, `3'000 franchi` | `AMOUNT` | forma |
| Catasto ticinese `mappale n. 1234 RFD Lugano`, `fondo n. 567` | `CATASTO` | forma ancorata alla sigla |
| Tessera assicurato `80756` + 15 cifre | `ID_DOC` | solo forma, nessun checksum garantito |
| N. registro di commercio vecchio formato `CH-020.3.912.345-6` | `PIVA` | solo forma: nessuna formula di controllo pubblica verificabile |
| Qualunque valore locale (comuni, sedi, numeri di pratica) | tag scelto dall'utente | **Termini personali** (📌), match letterale, priorità massima |

Misura onesta: `tests/fixtures_ticino.jsonl` (frasi sintetiche, checksum ricalcolati) + `tests/test_svizzera.py`
coprono **i formati**, non la qualità del modello su atti ticinesi veri. Il micro-F1 0,989 del progetto
originale è misurato sul benchmark **italiano**. Non spacciare l'uno per l'altro.

**Non coperto** (e da non promettere): permessi di soggiorno B/C/G/L (categoria semantica, non un
formato); diagnosi, patologie e dati sulla salute come categoria (idem: sono concetti, non formati);
qualunque identificabilità indiretta.

## 4. Checklist operativa per lo studio / l'ente

1. Dizionario: default in sessione. Se si attiva «💾 ricorda», dichiararlo nella documentazione interna e pulire a pratica chiusa.
2. Disco cifrato (FileVault / BitLocker) **e blocco automatico dello schermo entro 5 minuti** sulle macchine che fanno girare l'app; account personali, mai condivisi. Le altre abitudini stanno nella scheda ⚙️ → **Buone abitudini**.
3. Termini personali e **Termini in chiaro**: entrambi in chiaro in `prefs.json`; rimuoverli se il
   computer cambia mani. I secondi **tolgono protezione** (dicono di non coprire un valore che il
   modello riconosce: il nome di una scala, di un test): rivederli periodicamente, e leggere nel
   Rapporto quante occorrenze sono state lasciate in chiaro di proposito.
4. Per ogni invio a un LLM esterno: rileggere l'output; archiviare il **Rapporto**; se ci sono residui/saltati, fermarsi.
5. Fornitore LLM: verificare e annotare certificazione DPF o garanzie contrattuali; preferire endpoint senza retention/training.
6. Dati sanitari o di minori (medici, scuole): DPIA prima di adottare il flusso; per gli enti pubblici, sentire l'Incaricato cantonale.
7. Server esposto in rete (`--host 0.0.0.0`, Docker): impostare `PII_AUTH="utente:password"` (l'app avvisa all'avvio se manca) e mettere davanti un proxy cifrato; ricordare il §13 AGPL (offrire la sorgente).

## 5. Che cosa far validare a un consulente

Vedi la sezione «Consulente» nella risposta che accompagna questo documento, riportata qui in breve:
qualifica del rapporto (pseudonimizzazione vs anonimizzazione) per i flussi dello studio; applicabilità
nLPD/LPDP per il singolo ente; adeguatezza del fornitore LLM (art. 16-17); necessità della DPIA; testi
dell'informativa e del registro — gli scheletri, con le misure dell'app già compilate, sono in
[MODELLI-DOCUMENTAZIONE.md](MODELLI-DOCUMENTAZIONE.md); wording della scheda pubblica e dei termini
d'uso dell'app (esclusione di garanzia, obbligo di rilettura).

Il quadro **per settori** (scuola, amministrazione pubblica, studi medici, studi legali e notarili,
ditte e indipendenti), scritto per chi decide e non per chi programma, è in
[RAPPORTO-CONFORMITA-SETTORI.md](RAPPORTO-CONFORMITA-SETTORI.md).

## 6. Che cosa protegge l'autore del software (non il titolare)

L'autore non tratta dati: la nLPD non lo riguarda. Restano le dichiarazioni e i difetti taciuti.
Misure in atto: nessun claim di conformità (tagline «nessun dato esce», badge «by design»,
lint automatico che impedisce a un claim di rientrare — `tests/test_claims.py`); la campagna di
verifica dell'assenza di telemetria, con i suoi limiti dichiarati (`docs/VERIFICA-OFFLINE.md`);
`TERMS.md` mostrato al primo avvio e sempre in ⚙️ → Condizioni; `SECURITY.md` con tempi e
versioni supportate; limiti noti nel CHANGELOG; banner quando il server è esposto; `.sha256`
accanto ai binari; nessuna chiamata di rete, nemmeno per gli aggiornamenti. Ciò che nessuna
misura copre: dolo e colpa grave (CO art. 100), e l'ospitare l'app per conto di terzi.

## 7. Fonti

- nLPD, RS 235.1 — fedlex.admin.ch · IFPDT, «IA e protezione dei dati» (9 novembre 2023)
- UFG, elenco degli Stati con protezione adeguata; Swiss-U.S. DPF in vigore dal 15 settembre 2024
- LPDP Ticino, RL 163.100 (9 marzo 1987) e messaggio del Consiglio di Stato del 17 maggio 2023 (revisione totale)
- FSA, Vademecum sul segreto professionale dell'avvocato (art. 321 CP)
- Codice: `src/app/detectors_local.py`, `src/app/server_config.py` (credenziale), `tests/test_svizzera.py`,
  `tests/test_auth.py`, `tests/test_i18n_chiavi.py`, `tests/fixtures_ticino.jsonl`, `docs/CHANGELOG.md`
