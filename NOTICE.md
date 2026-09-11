# Avviso di modifica

**Questo è un fork modificato.** AnonimAI deriva da **rizzo-pii** di Simone Rizzo — Rizzo AI
Academy ([Rizzo-AI-Academy/rizzo-pii](https://github.com/Rizzo-AI-Academy/rizzo-pii)), rilasciato
sotto licenza MIT. Le modifiche descritte qui sotto sono state apportate da **Giacomo Meschini**
fra **agosto e settembre 2026** e proseguono; il registro completo, datato e motivato, è in
[docs/CHANGELOG.md](docs/CHANGELOG.md).

Questo file esiste per due ragioni. La prima è la licenza: i binari pubblicati sono AGPL-3.0
perché incorporano PyMuPDF, e il §5 lettera a di quella licenza chiede che una versione
modificata porti un avviso ben visibile che dica che è stata modificata, con la data. La seconda
è più semplice: chi scarica un programma che maneggia documenti riservati ha diritto di sapere
chi ha scritto che cosa.

## Che cosa viene da rizzo-pii

Il **modello** e tutto ciò che lo produce: l'architettura mmBERT, i 22 tag della tassonomia, la
pipeline di generazione dei dati sintetici, l'addestramento, le metriche. Il micro-F1 di 0,989
citato nel README è misurato da quel progetto, su un benchmark **italiano**. L'impianto
dell'applicazione locale — server Flask, interfaccia, flusso «anonimizza, copia, ripristina»,
dizionario reversibile — nasce lì, così come la prima rete di espressioni regolari con verifica
matematica per i codici italiani.

Senza quel lavoro questo fork non esisterebbe, e il modo giusto di dirlo è questo: il motore è
suo.

## Che cosa è stato aggiunto o cambiato in questo fork

**Riconoscimento svizzero e ticinese.** Numero AVS con verifica della cifra di controllo, IDI/UID
delle imprese, numero di registro di commercio nel vecchio formato, IBAN svizzero e del
Liechtenstein, cantoni, numeri postali, targhe, telefoni, importi in franchi, mappali e fondi del
registro fondiario, numero della tessera d'assicurato. Vive in `src/app/detectors_local.py`, un
file che upstream non ha, e non richiede un nuovo addestramento del modello.

**Redazione vera dei PDF.** I caratteri vengono rimossi dal contenuto del file, non coperti da un
rettangolo; annotazioni, campi modulo, segnalibri, allegati e metadati vengono ripuliti uno a uno;
i valori ancora leggibili nell'output vengono contati e dichiarati. Riconoscimento ottico per le
scansioni, riquadri manuali per firme e timbri, anteprima affiancata prima e dopo con zoom
condiviso fra le due colonne.

**Misure di protezione dei dati.** Nessuna chiamata di rete, con prove automatiche che lo
verificano a ogni modifica; nessuna copia su disco né nella cache del browser; documenti che
vivono in memoria e muoiono con un gesto, con la chiusura, dopo sette minuti di inattività;
dizionario nella sola sessione salvo consenso esplicito; credenziale per chi espone il server in
rete; promemoria sul blocco dello schermo e scheda di buone abitudini; rapporto del trattamento
senza valori; elenco dei termini che l'utente dichiara non personali.

**Condizioni d'uso, informativa e documentazione di conformità.** Il posizionamento come strumento
di pseudonimizzazione con verifica umana obbligatoria prima di ogni invio, la mappa fra le norme
svizzere e le funzioni dell'applicazione, il quadro per settori, i modelli da compilare per chi
adotta lo strumento in un ente.

**Nome e identità.** Il prodotto si chiama AnonimAI. Il nome, l'interfaccia nella sua forma
attuale e i testi sono di questo fork; il modello pubblicato su Hugging Face continua a chiamarsi
`rizzo-pii-0.3B` ed è quello di upstream, usato senza modifiche.

## Che cosa NON è cambiato, e va detto

I pesi del modello non sono stati riaddestrati. La qualità del riconoscimento sui nomi e sui testi
in prosa è quella misurata da rizzo-pii sull'italiano: il profilo svizzero aggiunge formati, non
migliora il modello. Chi legge un numero di qualità in questo repository deve sapere a quale delle
due cose si riferisce, ed è per questo che il README lo annota ogni volta.

## Se cerchi l'originale

L'opera non modificata è su
[github.com/Rizzo-AI-Academy/rizzo-pii](https://github.com/Rizzo-AI-Academy/rizzo-pii). Questo
fork non parla a nome di Rizzo AI Academy, non è approvato né sostenuto da loro, e ogni difetto
introdotto qui è responsabilità di chi lo mantiene. Il procedimento con cui il fork resta
allineato a monte è descritto in [SYNC-FORK.md](SYNC-FORK.md).

Contatto: giacomo@insegnai.ch
