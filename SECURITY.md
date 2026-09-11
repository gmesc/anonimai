# Security policy

## Versioni supportate

Solo l'**ultima release** pubblicata riceve correzioni. Le versioni precedenti vanno aggiornate.
I limiti noti sono dichiarati in `docs/CHANGELOG.md` (voce più recente) e in `docs/CONFORMITA-CH.md`.

## Segnalare una vulnerabilità

Un difetto che lascia **dati personali in chiaro** nell'output, che fa uscire dati dalla macchina, o
che espone il server senza che l'utente lo sappia è una vulnerabilità. Segnalala **in privato**:

- email: giacomo@insegnai.ch (oggetto: `[anonimai security]`). La casella è ospitata da
  **Infomaniak** (Ginevra): posta e allegati restano su data center in Svizzera, certificati
  **ISO 27001**, e non escono da lì. Dettagli e limiti in [PRIVACY.md](PRIVACY.md);
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

## Verificare da soli

```bash
python -m unittest discover tests   # include test_no_egress.py e test_claims.py
python src/app/smoke_offline.py     # 22 endpoint con la rete bloccata in-process
```

La campagna completa — sandbox di sistema, CSP applicata dal browser, e ciò che **non** è stato
verificato — è in [docs/VERIFICA-OFFLINE.md](docs/VERIFICA-OFFLINE.md).

## Perimetro

- L'app **non fa chiamate di rete** a runtime: niente API, telemetria, CDN, aggiornamenti automatici.
  Una dipendenza online è considerata un bug di architettura.
- Il server ascolta su `127.0.0.1`. Esporlo (`--host 0.0.0.0`, Docker senza `127.0.0.1:`) è una scelta
  dell'operatore, che ne assume la responsabilità. Chi lo espone deve impostare
  `PII_AUTH="utente:password"` (credenziale HTTP Basic su tutto tranne `/health` e `/assets`; l'app
  avvisa all'avvio se manca) e mettere davanti un proxy TLS: Basic da solo viaggia in chiaro.
- I binari delle release sono accompagnati da un file `.sha256`: verificare l'impronta prima di
  installare (`scripts/checksums.sh --check <file>`).
- Le dipendenze sono passate a `pip-audit` a ogni build (job `audit` in `tests.yml` e uno step nel
  build Windows, sull'ambiente che finisce davvero nell'installer). Le Action di GitHub sono
  pinnate al commit, non al tag mobile.
