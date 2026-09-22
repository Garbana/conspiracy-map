#!/usr/bin/env python3
"""Žaidimo iššūkiams – po mažą puslapį site/g/, kad pasidalinta nuoroda pokalbyje
rodytų lygio pavadinimą, o ne bendrą žemėlapio antraštę.

Ta pati priežastis kaip ir 10_share_pages.py: robotai JavaScript nevykdo, o užklausos
parametrai („?game=1&m=4") meta žymų pakeisti negali – reikia tikro failo. Todėl
kiekvienam lygiui sukuriamas puslapis, o įveiktiems – dar po vieną kiekvienam
galimam žingsnių skaičiui, kad kortelėje matytųsi ir iššūkio rezultatas.

    site/g/lt/1.html      – lygis be rezultato
    site/g/lt/1-4.html    – „įveikta per 4 žingsnius"
    site/g/lt/r.html      – atsitiktinis režimas

Vardas (?n=) lieka tik nuorodoje – jį parodo pats žaidimas, į meta žymas jis patekti
negali. Paleidžiama po 11_levels.py:

    python scraper/12_game_pages.py
"""
import html
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
DATA = os.path.join(SITE, "data")
OUT = os.path.join(SITE, "g")
BASE = "https://garbana.github.io/conspiracy-map"

PAGE = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · {site}</title>
<meta name="description" content="{desc}">
<meta name="theme-color" content="#07080d">
<link rel="icon" href="../../favicon.svg" type="image/svg+xml">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{site}">
<meta property="og:url" content="{url}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="{base}/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<script>
// Žmogų vedam tiesiai į žaidimą, pasiimdami iššūkio parametrus (vardą, žingsnius);
// robotui užtenka viršuje esančių meta žymų.
(function(){{var q=new URLSearchParams(location.search);q.set("game","{game}");
if(!q.get("lang"))q.set("lang","{lang}");location.replace("../../?"+q);}})();
</script>
<meta http-equiv="refresh" content="1;url=../../?lang={lang}&amp;game={game}">
</head>
<body style="background:#07080d;color:#8d8a82;font:15px/1.6 system-ui,sans-serif;padding:24px">
<h1 style="color:#e6e3da;font:600 20px system-ui">{title}</h1>
<p>{desc}</p>
<p><a href="../../?lang={lang}&amp;game={game}" style="color:#f0cf82">{go} →</a></p>
</body>
</html>
"""

TXT = {
    "lt": {
        "site": "Kelias pas Anunakius",
        "go": "Žaisti",
        # Wikidata etiketė yra „Anunaki" – tekstuose vartojam tas pačias formas,
        # kaip ir pats žaidimas: „Anunakiai" / „pasiek anunakius".
        "target": ("Anunakiai", "anunakius"),
        "lvl": lambda i, start, target: f"{i} lygis: {start} → {target}",
        "rnd": lambda target: f"Atsitiktinis iššūkis: pasiek {target}",
        "plain": lambda start, target, dist, budget:
            f"Pradžia – {start}. Pasiek {target} eidamas vien tikromis nuorodomis: "
            f"trumpiausias kelias – {dist} žingsniai, daugiausia leidžiama {budget}. "
            f"Be paieškos ir be filtrų.",
        "beat": lambda start, target, dist, m:
            f"Iššūkis: šis lygis įveiktas per {m} žingsnius (trumpiausias kelias – {dist}). "
            f"Pradžia – {start}; pasiek {target} eidamas vien tikromis nuorodomis. Ar pralenksi?",
        "rnd_desc": lambda target:
            f"Atsitiktinė pradžia, o tikslas visada tas pats – {target}. "
            f"Eik vien tikromis nuorodomis, be paieškos ir be filtrų.",
    },
    "en": {
        "site": "Road to the Anunnaki",
        "go": "Play",
        "target": ("the Anunnaki", "the Anunnaki"),
        "lvl": lambda i, start, target: f"Level {i}: {start} → {target}",
        "rnd": lambda target: f"Random challenge: reach {target}",
        "plain": lambda start, target, dist, budget:
            f"Start at {start} and reach {target} using nothing but real links: "
            f"the shortest route is {dist} moves, {budget} allowed. No search, no filters.",
        "beat": lambda start, target, dist, m:
            f"Challenge: this level was finished in {m} moves (shortest route: {dist}). "
            f"Start at {start} and reach {target} using nothing but real links. Can you beat it?",
        "rnd_desc": lambda target:
            f"A random start, always the same destination – {target}. "
            f"Real links only, no search and no filters.",
    },
}


def main():
    with open(os.path.join(DATA, "graph.json"), encoding="utf-8") as f:
        nodes = {n["id"]: n for n in json.load(f)["nodes"]}
    with open(os.path.join(DATA, "levels.json"), encoding="utf-8") as f:
        lv = json.load(f)

    def name(node_id, lang):
        n = nodes[node_id]
        t = (n.get("lt") or "").strip() if lang == "lt" else ""
        t = t or n["t"]
        return t[:1].upper() + t[1:]

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    made = 0
    for lang, t in TXT.items():
        os.makedirs(os.path.join(OUT, lang))
        target, target_acc = t["target"]

        def write(fname, game, title, desc):
            nonlocal made
            page = PAGE.format(
                lang=lang, site=t["site"], go=t["go"], game=game,
                title=html.escape(title, quote=True),
                desc=html.escape(desc, quote=True),
                url=f"{BASE}/g/{lang}/{fname}", base=BASE)
            with open(os.path.join(OUT, lang, fname), "w", encoding="utf-8") as fh:
                fh.write(page)
            made += 1

        for L in lv["levels"]:
            start = name(L["start"], lang)
            title = t["lvl"](L["lvl"], start, target)
            write(f"{L['lvl']}.html", L["lvl"], title,
                  t["plain"](start, target_acc, L["dist"], L["budget"]))
            # po puslapį kiekvienam rezultatui, kokį iššūkio autorius galėjo pasiekti
            for m in range(L["dist"], L["budget"] + 1):
                write(f"{L['lvl']}-{m}.html", L["lvl"], title,
                      t["beat"](start, target_acc, L["dist"], m))

        write("r.html", "r", t["rnd"](target_acc), t["rnd_desc"](target))

    print(f"Žaidimo dalinimosi puslapių: {made} ({len(TXT)} kalbos)")


if __name__ == "__main__":
    main()
