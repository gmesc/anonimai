# Sincronizzare questo fork con upstream (Rizzo-AI-Academy/rizzo-pii)

Questo file esiste solo nel fork `gmesc/anonimai`. Regola della casa: **il codice
del fork vive in file che upstream non ha**, gli agganci nei file di upstream sono
singole righe marcate `# fork` / `# --- fork gmesc/anonimai ---`.

## Dove vive il codice del fork

| File | Che cosa contiene |
|---|---|
| `src/app/detectors_local.py` | profilo Svizzera (AVS/IDI/Cantoni/NAP/targa/telefono/CHF/mappale RFD/tessera) + Termini personali + persistenza della chiave `custom_terms` in prefs.json |
| `tests/test_svizzera.py` | le prove di tutto quanto sopra (girano senza modello) |
| `tests/fixtures_ticino.jsonl` + `tests/test_fixture_ticino.py` | fixture sintetica ticinese: copertura dei formati CH |
| `docs/CONFORMITA-CH.md` | mappa nLPD/LPDP → funzioni dell'app → compiti del titolare |
| `TERMS.md`, `SECURITY.md` | condizioni d'uso (versionate per data, stesso testo in app) e policy di sicurezza |
| `SYNC-FORK.md` | questo file |

Agganci dentro i file di upstream (piccoli, cercali con `grep -n fork src/app/app.py`):
import + `install()` + `swissify_tags()` + `load/save_custom_terms()` +
`match_custom_terms()` in `app.py`; la riga `source == "utente"` in `_merge`;
il blocco `custom_terms` in `/settings`; sezione 📌 nella UI (CSS/markup/JS/i18n);
la sezione «Cornice legale in Svizzera» nella scheda Sicurezza; `DOC_TTL` + `_sweep_docs`
(TTL dei documenti in RAM); il checkbox «💾 ricorda» + `saveMap()`/`setPersist()` (dizionario
in sessionStorage per default); il bottone 📋 Rapporto (`dlrep`, i18n `dlrep`/`tip_rep`/`t_rep_ok`); scheda «Condizioni»
(`stTerms`/`setTerms`, `terms_body`), overlay primo avvio (`termsOverlay`, `TERMS_VERSION`,
`pii_terms_ack`), banner `#netWarn` (`net_warn`); tagline «nessun dato esce» (anche `tauri/ui/index.html`).

## Come si aggiorna (cherry-pick, NON merge del suo main intero)

```bash
git fetch upstream
git log --oneline HEAD..upstream/main        # cosa ha fatto Rizzo
git cherry-pick <hash>                       # solo i commit che vuoi
python -m unittest discover tests            # il contratto di stabilita'
git push origin main
```

Il merge completo (`git merge upstream/main`) resta possibile ma porta dentro
tutto, UI compresa: farlo solo a ragion veduta. In ogni caso, dopo qualunque
sync, la suite decide: se `tests/test_svizzera.py` è verde, le feature del fork
sono vive.

## Se un cherry-pick va in conflitto

Quasi certamente è `app.py` (la UI vive lì per scelta di upstream). Gli agganci
del fork sono poche righe marcate `fork`: in caso di dubbio si prende la versione
di upstream e si ri-applicano gli agganci a mano — l'elenco completo è sopra.
