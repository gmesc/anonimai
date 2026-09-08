# Condizioni d'uso di AnonimAI — versione 2026-09-04 (rev. 2)

> **Bozza da far validare da un avvocato** (diritto della protezione dei dati e delle tecnologie,
> Svizzera). Lo stesso testo compare nell'app (⚙️ → Condizioni) e viene mostrato al primo avvio.
> Finche' non arriva la versione validata, questo resta un testo provvisorio e ogni frase nuova
> nei testi pubblici passa da `tests/test_claims.py`, che vieta i claim non sostenibili.
> English summary at the end.

## 1. Che cos'è AnonimAI

AnonimAI è un **software open source di supporto** alla **pseudonimizzazione** di testi e PDF:
sostituisce gli identificatori diretti (nomi, indirizzi, numeri) con dei segnaposto. Con il
dizionario reversibile attivo l'operazione è reversibile da chi possiede il dizionario; spegnendolo
nessuna chiave viene creata e la sostituzione è irreversibile. **Che il risultato sia un dato
anonimo resta però una valutazione giuridica**, non una proprietà del programma: un testo senza
nomi può identificare comunque una persona (identificabilità indiretta).

Gira interamente sul computer dell'utente. Non è un servizio: nessun dato raggiunge
gli autori, nessun server, nessuna telemetria, nessun aggiornamento automatico. Le prove di questa
affermazione, e i loro limiti, sono in `docs/VERIFICA-OFFLINE.md`.

## 2. Chi è responsabile dei dati

Chi usa AnonimAI è, e resta, il **titolare del trattamento** dei documenti che elabora (nLPD
art. 5 lett. j; LPDP per gli enti pubblici ticinesi; GDPR art. 4 n. 7 per i dati di persone
nell'UE). Gli autori e i contributori del software **non trattano alcun dato**, non ne vengono a
conoscenza e non sono né titolari né responsabili del trattamento.

## 3. Che cosa il software non garantisce

- Il rilevamento delle informazioni personali si basa su un modello statistico e su regole. **Può
  sbagliare**: omettere un valore, etichettarne uno in modo errato, non riconoscere una
  identificazione indiretta (una vicenda descritta per esteso identifica la persona anche senza un
  nome).
- Con il dizionario reversibile attivo l'output è una **pseudonimizzazione**, cioè ancora dato
  personale per chi possiede il dizionario.
- Il software **non certifica** la conformità di alcun trattamento. La conformità dipende da come,
  da chi e per quale scopo viene usato.

## 4. Obblighi dell'utente

- **Rileggere sempre l'output** prima di comunicarlo a terzi (fornitori di LLM inclusi). Quando
  l'app segnala valori residui o saltati, fermarsi e verificarli. La **supervisione umana non è
  delegabile** e nessun controllo automatico la sostituisce.
- **Rispettare le regole dell'organizzazione per cui si lavora.** Se l'utente opera per uno studio,
  una scuola, un ente pubblico o un'azienda, il titolare del trattamento è quell'organizzazione, e
  valgono le sue direttive interne: quali documenti possono essere comunicati, verso quali servizi
  esterni, con quale autorizzazione. **L'uso di questo software non autorizza alcuna comunicazione**:
  un divieto posto da una direttiva, dal segreto professionale o da una norma resta tale anche
  quando il testo comunicato contiene soltanto segnaposto.
- Custodire il dizionario reversibile e i Termini personali come il documento originale.
- Valutare autonomamente la comunicazione dei dati all'estero (nLPD art. 16-17), la necessità di
  una valutazione d'impatto (nLPD art. 22) e gli obblighi di segreto professionale (art. 321 CP).
- Non esporre il server in rete senza accesso controllato; chi lo fa offre un servizio a terzi e
  ne assume le responsabilità (oltre al §13 della licenza AGPL-3.0 per i binari).

## 5. Garanzia e responsabilità

Il software è fornito **«così com'è», senza garanzia di alcun tipo**, secondo la licenza MIT (codice
sorgente) e AGPL-3.0 (binari distribuiti). Nei limiti consentiti dalla legge applicabile, gli autori
e i contributori non rispondono di alcun danno derivante dall'uso o dall'impossibilità d'uso del
software, incluse anonimizzazioni incomplete o errate. Questa esclusione non si estende ai casi in
cui la legge la vieta (in Svizzera: dolo e colpa grave, CO art. 100).

## 6. Segnalazioni

Difetti che lasciano in chiaro dati personali si segnalano come descritto in `SECURITY.md`. I limiti
noti del software sono elencati in `docs/CHANGELOG.md` e in `docs/CONFORMITA-CH.md`.

## 7. Modifiche

Queste condizioni sono versionate con la data, e con un numero di revisione quando cambiano nello
stesso giorno. Una versione nuova viene mostrata di nuovo al primo
avvio successivo. Il Rapporto di anonimizzazione registra la versione presa visione.

---

## English summary

AnonimAI is open-source **support software** for **pseudonymising** text and PDFs: it replaces direct
identifiers with placeholders, reversibly while the dictionary is on. With the dictionary off no key
is created, but whether the result qualifies as anonymous data remains a legal assessment, not a
property of the program. It runs entirely on the user's computer; the authors receive no data and are
neither controllers nor processors. The user remains the **data controller** — or must follow the
rules of the organisation that is — and must **re-read every output** before sharing it: human review
cannot be delegated, detection is statistical and can miss or mislabel values, and indirect
identification is not covered. Using this software authorises no disclosure: a ban set by an internal
policy, by professional secrecy or by law still applies to placeholder-only text. With the reversible dictionary on, the output is pseudonymised, i.e. still personal data.
The software is provided **"as is", without warranty**, under MIT (source) and AGPL-3.0 (binaries);
to the extent permitted by law, authors and contributors are not liable for any damage, including
incomplete anonymisation. Exposing the server on a network makes the operator a service provider.
