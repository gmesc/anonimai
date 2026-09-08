# AnonimAI per studi notarili, legali e fiduciari: che cos'è, che cosa non è, come provarlo

> Presentazione di un progetto open source, non un'offerta commerciale. Nessuno vi chiede di
> comprare, firmare o consegnare documenti. Vi chiede, se vi interessa, di provare l'app **sui
> vostri computer**, con i **vostri** atti, e di mandare all'autore un file che non contiene alcun
> dato: il Rapporto. Data: 6 settembre 2026.

## Il problema che risolve, in una frase

Chi incolla un atto in ChatGPT per farselo riassumere, tradurre o riscrivere consegna nomi, IBAN,
mappali e importi a un server che non controlla. AnonimAI sostituisce quei dati con dei segnaposto
**prima** che il testo esca dal computer, e li rimette al loro posto nella risposta, **dopo**. Il
chatbot lavora su `[FULLNAME_1]`, `[IBAN_1]`, `[CATASTO_1]`; i valori veri non lasciano la vostra
macchina.

## Che cosa fa, verificabile

- Gira **interamente sul computer** dello studio. Nessun server, nessuna registrazione, nessuna
  statistica d'uso, nessun aggiornamento automatico. Staccate la rete: funziona uguale. Nel codice
  c'è una prova automatica che fallisce se qualcuno introduce una chiamata verso l'esterno.
- Riconosce ciò che ha una **forma**: nomi, indirizzi, date, telefoni, email, AVS, IDI, numero di
  registro di commercio, IBAN svizzero e italiano, importi in franchi, targhe, NAP, cantoni,
  mappali e fondi RFD, numeri di pratica e di repertorio. Dove esiste una cifra di controllo la
  verifica, e ve lo segnala con un ✓.
- Vi lascia aggiungere le **vostre** parole da coprire sempre: i clienti seguiti da anni, le
  società del gruppo, la sede dello studio.
- **Censura davvero i PDF**: sotto il rettangolo nero i caratteri sono rimossi, non coperti;
  vengono ripulite anche note, campi, allegati e proprietà del file. Firme e timbri si coprono a
  mano con un riquadro, e sotto il riquadro i pixel spariscono.
- Non lascia nulla su disco. Il documento vive nella memoria del programma e muore con «Pulisci»,
  con la chiusura, o dopo sette minuti senza attività.
- Produce un **Rapporto** del trattamento senza alcun valore: data, impronta del documento, che
  cosa ha trovato e di che tipo, che cosa è rimasto in chiaro, versioni. Si archivia nell'incarto.

## Che cosa non fa, e lo dice

- **Non produce un documento anonimo.** Produce un documento **pseudonimizzato**: chi ha il
  dizionario ricostruisce tutto. Finché il dizionario esiste, quel testo è ancora coperto dal
  vostro segreto professionale.
- **Non vede la vicenda.** Una separazione raccontata nei dettagli identifica le parti anche senza
  un nome. Nessun programma lo vede; una persona sì.
- **Non riconosce i concetti**: diagnosi, permessi di soggiorno, misure disciplinari non hanno un
  formato.
- **Può sbagliare.** Sulle ragioni sociali è meno preciso che sui numeri: «Elettro Bernasconi
  Sagl» può essere letto come una persona. La misura pubblicata (0,989) è fatta su testi
  italiani, non su atti ticinesi. Per questo serve la vostra prova.

Da qui la regola che l'app ripete a ogni passaggio: **prima di incollare in un chatbot, la
verifica di una persona è obbligatoria**. L'invio a un servizio esterno non si annulla.

## A chi serve davvero, dentro uno studio

Allo studio piccolo, con un decisore solo, sugli **atti a formato**: rogiti, contratti, estratti
del registro di commercio e catastali, incarti successori, corrispondenza. Per il contenzioso
raccontato per esteso l'app è un primo passaggio, non una garanzia. Per il fiduciario: la prosa
(lettere all'ufficio di tassazione, reclami, email), non le tabelle né le buste paga.

## Chi c'è dietro, e che cosa vi chiede

Un progetto open source: il codice si legge, si verifica e si modifica. Modello e pipeline vengono
dal progetto italiano rizzo-pii; il profilo svizzero, la redazione dei PDF e i testi sulla
protezione dei dati sono di un fork mantenuto da un insegnante ticinese, senza società e senza
fatturazione. Le condizioni d'uso (`TERMS.md`) sono tre righe: il titolare del trattamento siete
voi, il rilevamento può sbagliare, nessuna garanzia. Nessuno vi certifica nulla, e nessuno vi
chiede di firmare nulla.

Quello che vi chiede è una cosa sola, e vale più di qualunque dichiarazione: **provatelo su una
decina dei vostri atti, sui vostri computer, e mandate il Rapporto.** Il Rapporto non contiene
dati; contiene i conteggi. Con dieci Rapporti da studi diversi si vede quali formati sfuggono,
quali etichette sbagliano, quanti valori restano in chiaro per tipo di documento. È l'unica
misura onesta possibile senza che un solo atto esca da uno studio. Come farlo, passo per passo,
è in [GUIDA-VALUTAZIONE-INTERNA.md](GUIDA-VALUTAZIONE-INTERNA.md).

## In tre righe, per chi decide

1. Tenete i vostri atti dove sono; l'app viene da voi, non il contrario.
2. Quello che esce dallo studio sono segnaposto, riletti da una persona.
3. Se decidete di adottarla, la documentazione che la legge vi chiede ha già uno scheletro in
   [MODELLI-DOCUMENTAZIONE.md](MODELLI-DOCUMENTAZIONE.md); il quadro per settori è in
   [RAPPORTO-CONFORMITA-SETTORI.md](RAPPORTO-CONFORMITA-SETTORI.md); la mappa articolo per
   articolo in [CONFORMITA-CH.md](CONFORMITA-CH.md).

Contatto: giacomo@insegnai.ch · Repository: https://github.com/gmesc/anonimai
