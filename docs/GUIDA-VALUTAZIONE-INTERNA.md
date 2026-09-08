# Guida alla valutazione interna: provare AnonimAI sui propri atti e mandare il Rapporto

> Per lo studio o l'ufficio che vuole capire se lo strumento serve, **senza che nessun documento
> esca dai propri computer**. Un pomeriggio di lavoro per una persona. Data: 6 settembre 2026.

## Che cosa vi serve

- Un computer dello studio: macOS (Apple Silicon), Windows o Linux. Installer e istruzioni nel
  [README](../README.md); l'installer Windows non è ancora firmato, quindi il sistema chiederà una
  conferma in più.
- Una **decina di documenti veri**, scelti per varietà: due rogiti o contratti, un estratto del
  registro di commercio o catastale, un incarto successorio, tre lettere, un PDF scansionato, un
  documento in tedesco o francese se ne trattate. Non serve di più; serve che siano diversi.
- Una persona che conosca quei documenti: la valutazione è la rilettura, e la rilettura la fa chi
  sa che cosa c'è dentro.

Prima di iniziare: al primo avvio l'app mostra le condizioni d'uso e un promemoria sul blocco
dello schermo. Leggeteli: sono corti e dicono le due cose che contano.

## La prova, passo per passo

1. **Aprite l'app, staccate la rete.** Wi-Fi spento o cavo staccato. Tutto quello che segue deve
   funzionare uguale. Se qualcosa non funziona senza rete, è un difetto da segnalare.
2. **Caricate il primo documento** (trascinatelo nella finestra) e premete **Anonimizza**.
3. **Guardate l'anteprima a destra**: ogni valore riconosciuto è colorato con la sua etichetta.
   Fate tre domande al documento:
   - *Che cosa è rimasto in chiaro?* Un nome, una ragione sociale, un numero che l'app non ha
     visto. Segnatevelo: tipo di dato e come era scritto (senza copiare il valore).
   - *Che cosa è stato etichettato male?* Una ditta letta come persona, una data letta come
     importo. Redatto comunque, ma l'etichetta sbagliata conta.
   - *Che cosa è stato coperto per errore?* Una parola comune presa per un dato. Devasta il
     testo? Segnatevelo.
4. **Premete «Testo da copiare»** e leggete il testo con i segnaposto come lo leggerebbe un
   estraneo. La domanda è una sola: *si capisce di chi si parla?* Se sì, avete trovato il caso
   che nessun programma copre, e vale la pena annotare che tipo di documento era.
5. **Premete «PDF anonimo»**, aprite il file prodotto, provate a selezionare e a cercare il testo
   sotto i rettangoli neri. Non deve esserci. Controllate le proprietà del file: autore e titolo
   devono essere vuoti.
6. **Premete 📋 Rapporto**: si scarica `rapporto_anonimizzazione.json`. Rinominatelo con un
   numero progressivo e il tipo di documento (`01_rogito.json`, `02_estratto_rc.json`).
7. **Premete «Pulisci»** e passate al documento successivo. Alla fine chiudete l'app.
8. Per le ragioni sociali e i clienti ricorrenti, provate anche i **Termini personali**
   (🏷️ → 📌): aggiungete tre voci e rifate un documento. Sono salvati in chiaro sul computer:
   toglieteli a prova finita, se il computer è condiviso.

## Prima di mandare i Rapporti: controllateli

Il Rapporto non contiene valori. Contiene però il **nome del file** che avete caricato
(`input.name`): se il file si chiamava `Rossi_successione.pdf`, quel nome è nel Rapporto. Due
modi per evitarlo: rinominate i file prima di caricarli (`doc01.pdf`), oppure aprite il Rapporto
con un editor di testo e cancellate la riga `"name"`. Contiene anche il nome della macchina da cui
avete usato l'app (`served_from`, di norma `127.0.0.1`) e il numero dei Termini personali, non le
voci. Rileggetelo: è un file di testo, si legge in un minuto.

Nel messaggio aggiungete, per ogni Rapporto, tre righe scritte a mano: il tipo di documento, che
cosa è rimasto in chiaro (per tipo, non per valore: «una ragione sociale con Sagl», «un numero di
polizza», «un cognome composto»), e se la persona era riconoscibile dal racconto. Sono queste
righe, insieme ai conteggi, a rendere utile la prova. Inviate a giacomo@insegnai.ch con oggetto
`[anonimai valutazione]`. Nessun documento, mai, nemmeno in parte: se vi scappa un allegato
sbagliato, avete comunicato un atto a un terzo.

## A che cosa serve il Rapporto, oltre a questo

**A voi, subito.** È il **verbale del trattamento** per l'incarto: data, impronta del documento
di partenza, che cosa è stato coperto e che cosa è rimasto in chiaro, versione del programma. Se
un giorno qualcuno chiede «che cosa avete mandato fuori e con quali cautele», la risposta è in
quel file, senza dover ricostruire nulla.

**A voi, se adottate lo strumento.** Serve alla riga di registro dei trattamenti e alla
valutazione d'impatto (scheletri in [MODELLI-DOCUMENTAZIONE.md](MODELLI-DOCUMENTAZIONE.md)):
la valutazione chiede di descrivere i rischi con dei fatti, e dieci Rapporti sui vostri documenti
sono i fatti. Serve anche a confrontare due versioni del programma sugli stessi documenti: stessa
impronta, conteggi diversi, e vedete se un aggiornamento ha migliorato o peggiorato.

**Al progetto.** Con Rapporti da studi diversi si vede, senza vedere un solo dato, quali formati
sfuggono e su quali tipi di documento, quali etichette sbagliano, quanti valori restano in chiaro
per pagina. È il modo in cui il profilo svizzero può essere misurato su atti veri senza che
nessun atto esca da uno studio, ed è l'unico che l'autore accetta: un documento vero nella sua
posta farebbe di lui un detentore di dati coperti dal vostro segreto.

## Che cosa non aspettarvi in cambio

Nessun attestato, nessuna dichiarazione di conformità, nessun contratto, nessuna assistenza con
tempi garantiti oltre a quelli scritti in [SECURITY.md](../SECURITY.md). Quello che potete
aspettarvi: un difetto dichiarato o corretto nel registro delle modifiche, e una risposta.
