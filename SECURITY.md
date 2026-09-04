# Security policy

## Versioni supportate

Solo l'**ultima release** pubblicata riceve correzioni. Le versioni precedenti vanno aggiornate.
I limiti noti sono dichiarati in `docs/CHANGELOG.md` (voce più recente) e in `docs/CONFORMITA-CH.md`.

## Segnalare una vulnerabilità

Un difetto che lascia **dati personali in chiaro** nell'output, che fa uscire dati dalla macchina, o
che espone il server senza che l'utente lo sappia è una vulnerabilità. Segnalala **in privato**:

- email: giacomo@insegnai.ch (oggetto: `[anonimai security]`);
- oppure GitHub → Security → *Report a vulnerability* sul repository `gmesc/anonimai`.

**Non aprire una issue pubblica** con documenti veri o valori personali: usa dati inventati.

Cosa aspettarsi:

| Passo | Tempo |
|---|---|
| Conferma di ricezione | 5 giorni lavorativi |
| Valutazione e piano | 15 giorni lavorativi |
| Correzione o limite dichiarato nel CHANGELOG | alla release successiva; prima, se il difetto fa uscire dati |

Se un difetto non è correggibile in tempi brevi viene **dichiarato come limite noto** nel CHANGELOG e
nella scheda Sicurezza dell'app: chi usa il software deve sapere che cosa non copre.

## Perimetro

- L'app **non fa chiamate di rete** a runtime: niente API, telemetria, CDN, aggiornamenti automatici.
  Una dipendenza online è considerata un bug di architettura.
- Il server ascolta su `127.0.0.1`. Esporlo (`--host 0.0.0.0`, Docker senza `127.0.0.1:`) è una scelta
  dell'operatore, che ne assume la responsabilità.
- I binari delle release sono accompagnati da un file `.sha256`: verificare l'impronta prima di
  installare.
