# Informativa privacy — versione 2026-09-11

> **Bozza da far validare da un avvocato**, come le condizioni d'uso.
> Riguarda i dati che **io** ricevo da te. Non riguarda i documenti che elabori con l'app:
> quelli non li vedo, non li ricevo e non esistono da nessuna parte fuori dal tuo computer.
> English summary at the end.

## 1. La cosa più importante, in due righe

**L'applicazione non raccoglie niente.** Gira sul tuo computer, non fa chiamate di rete, non ha
telemetria, non ha aggiornamenti automatici, non sa che esisti. È una proprietà verificata da
prove automatiche a ogni modifica del codice, e puoi controllarla staccando la rete: l'app funziona
uguale. Il procedimento per verificarlo è in [docs/VERIFICA-OFFLINE.md](docs/VERIFICA-OFFLINE.md).

Questa informativa esiste perché in **tre** punti, tutti facoltativi e tutti fuori dall'app, puoi
decidere di scrivermi. Lì i tuoi dati arrivano a me, e allora hai diritto di sapere che cosa ne
faccio.

## 2. Chi sono, e dove arriva quello che mi scrivi

Giacomo Meschini, Canton Ticino, Svizzera. Contatto: **giacomo@insegnai.ch**.
Sviluppo AnonimAI come progetto open source personale, senza società e senza fatturarlo.

**La casella di posta è ospitata da [Infomaniak](https://www.infomaniak.com/), a Ginevra.** Non è
un dettaglio tecnico: è il motivo per cui quello che mi scrivi non lascia la Svizzera. Infomaniak
si impegna per contratto a «conservare i tuoi dati esclusivamente nei data center situati in
Svizzera e non trasferire mai le tue informazioni al di fuori di queste infrastrutture», a
informare tempestivamente in caso di violazione, a dichiarare i propri subappaltatori, e a separare
i dati dei clienti con isolamento fisico o logico verificato da test di penetrazione annuali.

Le certificazioni, verificate sulla loro pagina l'11 settembre 2026:

| Norma o label | Che cosa copre | Dal |
|---|---|---|
| **ISO 27001:2022** | gestione della sicurezza delle informazioni | giugno 2018 |
| **ISO 9001:2015** | gestione della qualità | luglio 2022 |
| **ISO 14001:2015** | gestione ambientale | aprile 2015 |
| **ISO 50001:2018** | efficienza e gestione dell'energia | aprile 2015 |
| **Swiss Hosting** | dati ubicati ed elaborati in data center in Svizzera, progettati e gestiti da loro | — |
| **Swiss Made** / **Swiss Made Software** | sede e sviluppo in Svizzera, nessuna delocalizzazione, assistenza compresa | — |
| **B Corp™** | standard di impatto sociale e ambientale, governance, trasparenza | 2025 |

Che cosa questo **non** significa, perché la distinzione è la stessa che vale per l'app stessa:
Infomaniak risponde dell'**infrastruttura**, non di come io tratto i tuoi dati. Nel linguaggio
della legge è un responsabile del trattamento, e il titolare resto io. Le loro certificazioni
dicono che la casella è tenuta bene e sta in Svizzera; quello che faccio con le tue email lo dice
questo documento, e ne rispondo io.

Un effetto pratico che vale la pena conoscere se lavori in uno studio o in un ente: essendo
un'azienda svizzera senza presenza negli Stati Uniti, Infomaniak non ricade sotto il CLOUD Act
statunitense, che è invece la ragione per cui molti servizi di posta diffusi vengono guardati con
diffidenza quando si tratta di dati coperti da segreto professionale.

## 3. I tre casi in cui ricevo qualcosa da te

### a) Mi mandi un Rapporto di anonimizzazione — **facoltativo**

Nella [guida alla valutazione interna](docs/GUIDA-VALUTAZIONE-INTERNA.md) chiedo a chi prova
l'app di mandarmi il file `rapporto_anonimizzazione.json`.

**Non è obbligatorio, e non serve a me più che a te.** Puoi usare l'applicazione per sempre senza
mandarmi niente, e nessuna funzione dipende da quell'invio. Serve a una cosa sola: capire che cosa
il programma sbaglia sui documenti veri. Il modello è addestrato su testi italiani, il profilo
svizzero è verificato su formati inventati, e nessuno — nemmeno io — sa oggi come si comporta su
un rogito di Lugano o su un referto ticinese. Con qualche Rapporto da studi diversi si vede quali
formati sfuggono e quali etichette sbagliano, e si correggono per tutti. È il modo di misurare la
qualità su documenti veri **senza che un solo documento vero esca dal tuo studio**: l'alternativa,
farmi consegnare gli atti, non la accetto, perché mi renderebbe detentore di dati coperti dal tuo
segreto professionale.

Che cosa contiene il Rapporto: data, impronta crittografica del documento di partenza, conteggi
per tipo di dato, versioni del programma. **Nessun valore personale.** Contiene però il **nome del
file** che hai caricato: se il file si chiamava `Rossi_successione.pdf`, quel nome arriva a me. La
guida ti dice di rinominare i file o di togliere quella riga prima di inviare, e te lo ripeto qui.

Che cosa ne faccio: leggo i conteggi, correggo il programma, e tengo il file finché serve a quel
lavoro. Non lo pubblico, non lo condivido, non lo uso per altro. Se mi mandi per sbaglio un
documento vero, te lo dico e lo cancello subito.

### b) Mi segnali una vulnerabilità

Come descritto in [SECURITY.md](SECURITY.md), per email o dal canale privato di GitHub. Ricevo il
tuo indirizzo e quello che scrivi. Lo uso per capire il difetto, risponderti e correggerlo. Se ti
fa piacere ti cito fra i ringraziamenti quando il difetto è chiuso, ma solo se me lo dici tu.
**Non mandare mai documenti veri in una segnalazione**: usa dati inventati.

### c) Apri una issue o una pull request su GitHub

Lì la piattaforma è GitHub, non io: il tuo nome utente, il testo e il codice che scrivi sono
**pubblici** e restano sui loro server, secondo la loro informativa. Io li leggo come chiunque
altro. Anche qui: niente documenti veri, mai, nemmeno in parte.

## 4. Il sito

La pagina di presentazione è ospitata da GitHub Pages. Non ha statistiche d'uso, non ha cookie,
non carica caratteri né immagini da servizi esterni: l'ho verificato sul codice della pagina, e
puoi verificarlo tu. GitHub registra gli accessi ai propri server per proprie ragioni tecniche, e
su quello non ho voce; vale la loro informativa.

## 5. Per quanto tengo le cose, dove stanno, e a chi non le do

Tengo le email e i Rapporti finché servono al lavoro per cui me li hai mandati, e comunque non
oltre due anni. Stanno in **due posti soli**: la casella Infomaniak in Svizzera descritta al
punto 2, e il mio computer, con disco cifrato e blocco automatico dello schermo — le stesse
abitudini che l'app raccomanda a te.

**Non li do a nessuno**: nessun servizio di statistiche, nessuna piattaforma pubblicitaria,
nessun fornitore di intelligenza artificiale, nessun terzo. Non faccio profilazione e non prendo
decisioni automatizzate sul tuo conto. L'unico caso in cui potrei dover consegnare qualcosa è un
ordine di un'autorità svizzera, e in quel caso non avrei scelta.

## 6. I tuoi diritti

Puoi chiedermi che cosa ho di tuo, farmelo correggere, farmelo cancellare, o dirmi di non usare
più un Rapporto che mi avevi mandato. Scrivi a **giacomo@insegnai.ch** e rispondo. Non ti chiedo
di provare chi sei, salvo quando quello che chiedi riguarda dati che non sono chiaramente tuoi.

Se pensi che stia trattando i tuoi dati in modo scorretto puoi rivolgerti all'Incaricato federale
della protezione dei dati e della trasparenza (IFPDT), Berna.

## 7. Modifiche

Questa informativa è versionata con la data. La versione in vigore è quella che leggi qui, nel
repository. Se cambia in modo sostanziale lo scrivo nel [registro delle modifiche](docs/CHANGELOG.md).

---

## English summary

**The application collects nothing.** It runs on your machine, makes no network calls, has no
telemetry and no automatic updates; automated tests verify this on every change, and you can check
it by pulling the network cable. This notice covers the three optional cases in which you may
choose to write to me, all outside the app.

**Anonymisation reports are welcome but entirely optional** — nothing in the app depends on sending
one. They help find what the tool gets wrong on real documents without a single real document
leaving your office, which is the only way I am willing to measure it. A report holds no personal
values, but it does hold the **file name** you loaded: rename your files, or delete that line,
before sending.

**Security reports** reach me by email or through GitHub's private channel; never include real
documents. **Issues and pull requests** are public and live on GitHub's servers under their own
privacy policy.

I keep what you send only as long as it serves the purpose you sent it for, and never beyond two
years, on an encrypted disk. I share it with nobody: no analytics, no advertising, no AI provider,
no third party. No profiling, no automated decisions. Write to **giacomo@insegnai.ch** to see,
correct or delete anything of yours; you may also contact the Swiss Federal Data Protection and
Information Commissioner (FDPIC), Bern.
