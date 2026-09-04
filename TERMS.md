# Condizioni d'uso di AnonimAI — versione 2026-09-04

> **Bozza da far validare da un avvocato** (diritto della protezione dei dati e delle tecnologie,
> Svizzera). Lo stesso testo compare nell'app (⚙️ → Condizioni) e viene mostrato al primo avvio.
> Finche' non arriva la versione validata, questo resta un testo provvisorio e ogni frase nuova
> nei testi pubblici passa da `tests/test_claims.py`, che vieta i claim non sostenibili.
> English summary at the end.

## 1. Che cos'è AnonimAI

AnonimAI è un **software open source di supporto** alla pseudonimizzazione e anonimizzazione di
testi e PDF. Gira interamente sul computer dell'utente. Non è un servizio: nessun dato raggiunge
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
  l'app segnala valori residui o saltati, fermarsi e verificarli.
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

Queste condizioni sono versionate con la data. Una versione nuova viene mostrata di nuovo al primo
avvio successivo. Il Rapporto di anonimizzazione registra la versione presa visione.

---

## English summary

AnonimAI is open-source **support software** for pseudonymising and anonymising text and PDFs. It runs
entirely on the user's computer; the authors receive no data and are neither controllers nor
processors. The user remains the **data controller** and must **re-read every output** before sharing
it: detection is statistical and can miss or mislabel values, and indirect identification is not
covered. With the reversible dictionary on, the output is pseudonymised, i.e. still personal data.
The software is provided **"as is", without warranty**, under MIT (source) and AGPL-3.0 (binaries);
to the extent permitted by law, authors and contributors are not liable for any damage, including
incomplete anonymisation. Exposing the server on a network makes the operator a service provider.
