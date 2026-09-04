# Modelli da compilare: registro, valutazione d'impatto, informativa

> **Bozze da far validare.** Sono scheletri, non documenti pronti: le parti che dipendono
> dall'app sono già compilate e verificabili nel codice, quelle che dipendono da te sono
> segnate `[da compilare]`. Falli leggere a un consulente prima di appoggiarci una decisione
> d'ente. Data: 4 settembre 2026.
>
> A chi servono: a chi usa AnonimAI dentro uno studio, una scuola, un ufficio o una ditta e
> deve produrre la documentazione che la legge chiede al **titolare del trattamento** — cioè
> a lui, non agli autori del software. La mappa articolo per articolo è in
> [CONFORMITA-CH.md](CONFORMITA-CH.md); il quadro per settori, senza gergo, è in
> [RAPPORTO-CONFORMITA-SETTORI.md](RAPPORTO-CONFORMITA-SETTORI.md).

---

## 1. Riga di registro dei trattamenti

Il registro è obbligatorio per gli enti pubblici e, fra i privati, per chi ha almeno 250
collaboratori o tratta dati delicati su larga scala o fa profilazione a rischio elevato
(nLPD art. 12; per gli enti ticinesi vale la LPDP). Sotto quelle soglie resta una buona
abitudine: è il documento che, davanti a una contestazione, dimostra che sapevi che cosa
stavi facendo.

Questa è **una riga**: il trattamento «documento interno → anonimizzazione locale → servizio
di intelligenza artificiale esterno → ripristino locale». Se usi l'app per flussi diversi
(per esempio anche per consegnare atti a terzi), ogni flusso è una riga sua.

| Voce | Contenuto |
|---|---|
| **Titolare del trattamento** | `[da compilare: ragione sociale / ente, indirizzo, persona di contatto]` |
| **Nome del trattamento** | Assistenza redazionale con intelligenza artificiale su documenti pseudonimizzati |
| **Scopo** | `[da compilare: es. redazione e revisione di atti, sintesi di documenti, traduzione]` |
| **Categorie di persone interessate** | `[da compilare: clienti, pazienti, allievi e genitori, dipendenti, controparti]` |
| **Categorie di dati** | Dati anagrafici e di contatto, identificativi (AVS, IDI, IBAN, targhe, mappali), importi. `[da compilare: dati degni di particolare protezione? salute, misure amministrative, procedimenti]` |
| **Destinatari** | Nessuno riceve dati in chiaro. Il fornitore del servizio di intelligenza artificiale riceve **testo con segnaposto** (`[FULLNAME_1]`), non valori. `[da compilare: nome del fornitore e sede]` |
| **Comunicazione all'estero** | `[da compilare: Stato del fornitore; base della comunicazione: decisione di adeguatezza, Swiss-U.S. Data Privacy Framework, clausole contrattuali tipo]` |
| **Durata di conservazione** | Dentro l'app: nessuna. I documenti stanno in memoria e vengono cancellati con «Pulisci», alla chiusura, dopo 7 minuti di inattività, e comunque entro 10 minuti sul lato server. Il dizionario reversibile vive nella sessione del browser salvo attivazione esplicita di «ricorda». `[da compilare: quanto conservi i documenti e i rapporti nella tua pratica]` |
| **Misure di sicurezza tecniche** | Elaborazione **interamente locale**, nessuna chiamata di rete (verificata da prove automatiche); server su `127.0.0.1`, credenziale obbligatoria se esposto in rete; nessuna copia su disco né nella cache del browser; redazione reale del PDF con pulizia di annotazioni, campi, allegati e metadati; verifica finale dei valori residui. `[da compilare: disco cifrato, blocco schermo, gestione degli accessi]` |
| **Misure organizzative** | Rilettura umana obbligatoria di ogni testo prima dell'invio; archiviazione del Rapporto di anonimizzazione con la pratica. `[da compilare: chi è autorizzato, formazione, direttiva interna]` |
| **Responsabile del trattamento** | Gli autori di AnonimAI **non** sono responsabili del trattamento: il software gira sulle vostre macchine e non riceve dati. `[da compilare: il fornitore del servizio di intelligenza artificiale è un responsabile o un destinatario? va contrattualizzato]` |

---

## 2. Scheletro di valutazione d'impatto (nLPD art. 22)

Serve quando il trattamento può comportare un **rischio elevato** per le persone: dati sulla
salute, dati di minori, valutazione sistematica di aspetti personali, uso di tecnologie nuove.
Un flusso che manda testi a un servizio esterno di intelligenza artificiale ricade quasi
sempre in questa descrizione, e per gli enti pubblici ticinesi va accompagnato dal contatto
con l'Incaricato cantonale.

### 2.1 Descrizione del trattamento
`[da compilare: chi lo fa, su quali documenti, con quale frequenza, con quale servizio esterno]`

Catena tecnica, uguale per tutti: documento originale → rilevamento locale dei dati personali
(modello linguistico locale + regole con verifica matematica dei numeri) → sostituzione con
segnaposto → invio al servizio esterno del **solo testo con segnaposto** → ritorno della
risposta → ripristino locale dei valori veri tramite il dizionario, che non lascia la macchina.

### 2.2 Necessità e proporzionalità
`[da compilare: perché serve un servizio esterno, che alternativa è stata valutata, perché il
volume di dati trattato è il minimo necessario]`

Elemento a favore, verificabile: al servizio esterno arriva la struttura del testo, non
l'identità delle persone. È la forma più contenuta di comunicazione compatibile con lo scopo.

### 2.3 Rischi per le persone interessate

| Rischio | Come si manifesta | Gravità |
|---|---|---|
| **Valore non rilevato** | Un nome o un numero sfugge al rilevamento e viene comunicato al servizio esterno | `[da compilare]` |
| **Identificabilità indiretta** | Il testo non contiene nomi ma la vicenda descritta identifica comunque la persona | Alta: nessuna misura tecnica la copre |
| **Categorie senza formato** | Diagnosi, misure disciplinari, permessi di soggiorno: concetti, non formati; il rilevamento non li vede | `[da compilare, alta per medici e scuola]` |
| **Perdita o furto del dizionario** | Chi ottiene il dizionario ricostruisce il documento originale | Alta |
| **Comportamento del fornitore estero** | Conservazione, riutilizzo per addestramento, accesso di autorità straniere | `[da compilare in base al contratto]` |
| **Computer incustodito** | Schermo aperto, account condiviso, disco non cifrato | `[da compilare]` |

### 2.4 Misure già in atto (fornite dal software)

Queste sono verificabili nel codice e non richiedono configurazione:

- Elaborazione **interamente locale**: nessuna chiamata di rete, nessuna telemetria, nessun
  aggiornamento automatico. Una prova automatica fallisce se qualcuno introduce una dipendenza
  online (`tests/test_no_egress.py`, `src/app/smoke_offline.py`).
- **Nessuna scrittura su disco**: i documenti vivono in memoria (`_DOCS`), muoiono con
  «Pulisci», con la chiusura della finestra, dopo 7 minuti di inattività e comunque entro 10
  minuti lato server. Le risposte non sono memorizzabili nella cache del browser.
- **Dizionario nella sola sessione** per impostazione predefinita; la conservazione su disco
  richiede una spunta e una conferma esplicita.
- **Redazione reale del PDF**: i caratteri sono rimossi dal contenuto, non coperti; annotazioni,
  campi modulo, allegati, segnalibri e metadati vengono ripuliti.
- **Verifica finale**: i valori ancora leggibili («residui») e quelli non cercati perché troppo
  corti («saltati») vengono contati e dichiarati; se nel PDF non si trova nessuna occorrenza
  l'app rifiuta di produrre il file invece di consegnarlo intatto.
- **Verifica matematica** degli identificativi che ne hanno una: AVS, IDI, IBAN, codice fiscale,
  carta di credito. Un numero con cifra di controllo sbagliata non viene spacciato per valido.
- **Perimetro di rete**: ascolto su `127.0.0.1`; se il server viene esposto, credenziale
  obbligatoria (`PII_AUTH`) e avviso in pagina e all'avvio.
- **Rapporto di anonimizzazione** senza valori, da archiviare con la pratica.

### 2.5 Misure che restano a te
`[da compilare]` — le principali: rilettura umana di ogni testo prima dell'invio; scelta e
contrattualizzazione del fornitore (endpoint senza conservazione né addestramento); disco
cifrato; blocco automatico dello schermo; account personali; cancellazione di dizionari e copie
a pratica chiusa; formazione delle persone che usano lo strumento; direttiva interna che dica
quali documenti possono passare da questo flusso e quali no.

### 2.6 Rischio residuo ed esito
`[da compilare: il rischio residuo è accettabile? se resta elevato, la nLPD chiede la
consultazione dell'Incaricato federale; per gli enti ticinesi, dell'Incaricato cantonale]`

Data, firma del titolare, data di revisione prevista: `[da compilare]`

---

## 3. Paragrafo per l'informativa alle persone interessate

Da inserire nell'informativa che già consegni (ai pazienti, ai clienti, alle famiglie, ai
dipendenti). Adatta il vocabolario al tuo pubblico.

> **Uso di strumenti di intelligenza artificiale.** Per alcune attività di redazione e di
> analisi dei documenti ci avvaliamo di strumenti di intelligenza artificiale. Prima che un
> testo raggiunga un servizio esterno, i dati che permettono di identificarvi (nome, indirizzo,
> data di nascita, numeri di identificazione, riferimenti bancari) vengono sostituiti sul nostro
> computer con dei segnaposto da un programma che funziona **senza collegamento a internet**: al
> fornitore esterno arriva il testo con i segnaposto, non i vostri dati. La corrispondenza fra
> segnaposto e dati veri resta sui nostri sistemi e non viene mai trasmessa.
> `[se applicabile:]` Il fornitore esterno ha sede in `[Stato]` e la comunicazione avviene sulla
> base di `[decisione di adeguatezza / Swiss-U.S. Data Privacy Framework / clausole contrattuali
> tipo]`.
> Ogni testo viene comunque riletto da una persona prima dell'invio. Potete chiederci in ogni
> momento quali dati vi riguardano trattiamo e come: `[contatto]`.

---

## 4. Che cosa non trovate qui

- **Il testo del contratto con il fornitore** del servizio di intelligenza artificiale: dipende
  dal fornitore e va negoziato o accettato con cognizione.
- **La direttiva interna** su quali documenti possono passare da questo flusso: è una decisione
  di merito, e nei settori più esposti (salute, minori) è la misura che conta più di tutte le
  altre.
- **Il parere sulla qualificazione del risultato**: con il dizionario attivo l'output è una
  pseudonimizzazione, cioè ancora un dato personale; senza dizionario l'anonimizzazione è
  definitiva ma la valutazione sull'identificabilità indiretta resta una valutazione umana.
  Su questo serve un consulente, non un modello di documento.
