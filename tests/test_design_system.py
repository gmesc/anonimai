# -*- coding: utf-8 -*-
"""Il CSS dell'app resta dentro il design system StudIA (skill studia-app-layout).

L'audit vero e' MISURATO sull'app viva (altezze reali di ogni controllo in ogni
stato): quello non entra in una suite senza modello e senza browser. Qui restano
le promesse verificabili sul SORGENTE, che sono anche quelle che si rompono per
distrazione mentre si scrive una regola nuova:

  - lo stack dei font e' testo -> emoji -> generico (se il generico viene prima,
    le emoji tornano quelle di sistema e nel tema dell'app si vede);
  - niente ombra a riposo: l'ombra e' per l'hover e per cio' che fluttua;
  - niente border-radius fuori dalle due eccezioni (pallini 50%, chip 999px);
  - mai outline:none, che spegne la navigazione da tastiera;
  - niente dialetti: i componenti del sistema si usano, non si ricopiano.

Gira senza modello (invariante 4): legge il testo di app.py.
"""
import os
import re
import unittest

APP = os.path.join(os.path.dirname(__file__), "..", "src", "app", "app.py")
GENERICI = ("sans-serif", "serif", "monospace", "system-ui", "cursive")


def _css():
    """Il blocco di stile della pagina (fra <style> e </style>)."""
    with open(APP, encoding="utf-8") as f:
        src = f.read()
    return "\n".join(re.findall(r"<style>(.*?)</style>", src, re.S))


class TestStackDeiFont(unittest.TestCase):
    """Ogni font-family proprio ripete l'ordine: testo, poi emoji, poi generico."""

    def test_l_emoji_font_precede_il_generico(self):
        colpevoli = []
        for stack in re.findall(r"font-family:([^;}]+)", _css()):
            voci = [v.strip() for v in stack.split(",")]
            if not any("--emoji-font" in v for v in voci):
                # uno stack senza generico non ha bisogno dell'emoji-font
                if any(v in GENERICI for v in voci):
                    colpevoli.append("senza emoji-font: " + stack.strip())
                continue
            i_emoji = next(i for i, v in enumerate(voci) if "--emoji-font" in v)
            generici = [i for i, v in enumerate(voci) if v in GENERICI]
            if generici and min(generici) < i_emoji:
                colpevoli.append("generico prima dell'emoji-font: " + stack.strip())
        self.assertEqual(colpevoli, [], "stack fuori ordine:\n" + "\n".join(colpevoli))


class TestOmbreERaggi(unittest.TestCase):

    def test_nessuna_ombra_a_riposo(self):
        # ammesse: il token dell'hover, gli inset (bordi interni) e le LINEE
        # (un box-shadow senza sfocatura e' un separatore che non occupa spazio,
        # come quello fra le due colonne)
        sospette = []
        for sh in re.findall(r"box-shadow:([^;}]+)", _css()):
            v = sh.strip()
            if "--sh-3d" in v or "inset" in v or v == "none":
                continue
            if re.fullmatch(r"-?\d+(?:px)? -?\d+(?:px)? 0 var\(--[a-z-]+\)", v):
                continue           # linea netta, non un'ombra
            sospette.append(v)
        self.assertEqual(sospette, [], "ombre a riposo: " + str(sospette))

    def test_nessun_raggio_fuori_dalle_eccezioni(self):
        raggi = [r.strip() for r in re.findall(r"border-radius:([^;}]+)", _css())]
        fuori = [r for r in raggi if r not in ("0", "0px", "50%", "999px")]
        self.assertEqual(fuori, [], "raggi non ammessi: " + str(fuori))


class TestTastiera(unittest.TestCase):

    def test_mai_outline_none(self):
        # spegnere l'outline toglie la bussola a chi naviga con Tab
        self.assertNotRegex(_css(), r"outline:\s*none")

    def test_il_focus_visibile_sui_bottoni_arriva_dai_token(self):
        # le regole :focus dell'app devono restare sui CAMPI DI TESTO, dove
        # l'anello e' voluto anche col mouse; sui bottoni comanda :focus-visible
        # di tokens.css. Un ':focus' su un bottone rimetterebbe il frame a ogni clic.
        for sel in re.findall(r"([^{}]+):focus\{", _css()):
            s = sel.strip().lower().split(",")[-1].strip()
            self.assertRegex(s, r"(textarea|input|select)",
                             f"regola :focus su un elemento che non e' un campo: {s}")


class TestNienteDialetti(unittest.TestCase):

    def test_il_gruppo_segmentato_e_quello_del_sistema(self):
        # .seg-tabs era una copia riga per riga di .tseg (tokens.css)
        self.assertNotIn("seg-tabs", _css())

    def test_le_barre_non_scrivono_le_proprie_misure(self):
        # dentro una regola di .tbtn/.tbar/.tseg l'altezza e il corpo vengono dai
        # token: un pixel scritto a mano e' l'inizio di una seconda scala
        css = _css()
        for regola in re.findall(r"\.(?:tbtn|tbar|tseg)[^{]*\{([^}]*)\}", css):
            for prop in ("height", "font-size"):
                m = re.search(prop + r":\s*(\d+px)", regola)
                self.assertIsNone(m, f"{prop} a mano in una regola di barra: {regola[:60]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
