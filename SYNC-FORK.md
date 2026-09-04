# Sincronizzare questo fork con upstream (Rizzo-AI-Academy/rizzo-pii)

Questo file esiste solo nel fork `gmesc/anonimai`. Regola della casa: **il codice
del fork vive in file che upstream non ha**, gli agganci nei file di upstream sono
singole righe marcate `# fork` / `# --- fork gmesc/anonimai ---`.

## Dove vive il codice del fork

| File | Che cosa contiene |
|---|---|
| `src/app/detectors_local.py` | profilo Svizzera (AVS/Cantoni/NAP/targa CH) + Termini personali + persistenza della chiave `custom_terms` in prefs.json |
| `tests/test_svizzera.py` | le prove di tutto quanto sopra (girano senza modello) |
| `SYNC-FORK.md` | questo file |

Agganci dentro i file di upstream (piccoli, cercali con `grep -n fork src/app/app.py`):
import + `install()` + `swissify_tags()` + `load/save_custom_terms()` +
`match_custom_terms()` in `app.py`; la riga `source == "utente"` in `_merge`;
il blocco `custom_terms` in `/settings`; sezione 📌 nella UI (CSS/markup/JS/i18n);
una voce nella scheda Sicurezza.

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
