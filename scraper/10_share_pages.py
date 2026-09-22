#!/usr/bin/env python3
"""Kiekvienam mazgui – po mažą puslapį site/t/, kad pasidalinta nuoroda pokalbyje
rodytų konkrečios teorijos pavadinimą, o ne bendrą žemėlapio antraštę.

Pokalbių programėlės ir paieškos robotai JavaScript nevykdo, tad dinamiškai pakeistų
`og:` žymų jie nemato – reikia tikro failo su savo meta duomenimis. Puslapis pats
nieko nerodo: jis iškart permeta į žemėlapį ties tuo mazgu (ir, jei nuorodoje yra,
atstato nueitą kelią).

Nuorodos pavidalas:  site/t/holocaust-denial-Q151296.html?lang=lt&p=Q1,Q2
Mazgo trumpinys įrašomas ir į graph.json ("sg"), kad svetainė žinotų adresą.

Paleidžiama po 09_sumflags.py:
    python scraper/10_share_pages.py
"""
import html
import json
import os
import re
import shutil
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
DATA = os.path.join(SITE, "data")
OUT = os.path.join(SITE, "t")
BASE = "https://garbana.github.io/conspiracy-map"
STATUS_LT = {"debunked": "Paneigta", "disputed": "Ginčijama", "confirmed": "Įrodyta"}
STATUS_EN = {"debunked": "Debunked", "disputed": "Disputed", "confirmed": "Confirmed"}


def slug(title, node_id):
    """Skaitomas failo vardas: pavadinimas be diakritikos + mazgo ID (kad būtų unikalus)."""
    s = unicodedata.normalize("NFD", title)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60].strip("-")
    return f"{s}-{node_id}" if s else node_id


def snippet(text, limit=190):
    """Pirmieji sakiniai vienoje eilutėje – tiek, kiek telpa į pokalbio kortelę."""
    t = " ".join((text or "").split())
    if len(t) <= limit:
        return t
    cut = t[:limit]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > limit * 0.6 else cut).rstrip(" .,;:") + "…"


PAGE = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Conspiracy Map</title>
<meta name="description" content="{desc}">
<meta name="theme-color" content="#07080d">
<link rel="icon" href="../favicon.svg" type="image/svg+xml">
<link rel="canonical" href="{url}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Conspiracy Map">
<meta property="og:url" content="{url}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="{base}/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<script>
// Žmogų vedam į žemėlapį (su keliu, jei nuorodoje jis yra); robotui užtenka meta žymų.
(function(){{var q=new URLSearchParams(location.search),l=q.get("lang");
location.replace("../"+(l?"?lang="+encodeURIComponent(l):"")+"#"+(q.get("p")||"{id}"));}})();
</script>
<meta http-equiv="refresh" content="1;url=../#{id}">
</head>
<body style="background:#07080d;color:#8d8a82;font:15px/1.6 system-ui,sans-serif;padding:24px">
<h1 style="color:#e6e3da;font:600 20px system-ui">{title}</h1>
<p><a href="../#{id}" style="color:#f0cf82">Conspiracy Map →</a></p>
</body>
</html>
"""


def main():
    with open(os.path.join(DATA, "graph.json"), encoding="utf-8") as f:
        g = json.load(f)
    def load(name):
        path = os.path.join(DATA, name)
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    en, lt = load("summaries.json"), load("summaries_lt.json")

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)          # seni failai su pasikeitusiais pavadinimais nekaupiami
    os.makedirs(OUT)

    used, total = set(), 0
    for n in g["nodes"]:
        sg = slug(n["t"], n["id"])
        if sg in used:              # teoriškai neįmanoma (ID gale), bet tegul
            sg = n["id"]
        used.add(sg)
        n["sg"] = sg

        # Antraštė: lietuviškas pavadinimas pirma, angliškas šalia (jei skiriasi)
        name_lt = (n.get("lt") or "").strip()
        title = f"{name_lt[:1].upper()}{name_lt[1:]} · {n['t']}" if name_lt and name_lt.lower() != n["t"].lower() else n["t"]
        # Aprašymas: teorijos būsena + santrauka (lietuviškai, jei yra)
        text = lt.get(n["id"]) or en.get(n["id"]) or n.get("sd") or ""
        desc = snippet(text)
        if n.get("st"):
            mark = STATUS_LT.get(n["st"], "")
            mark_en = STATUS_EN.get(n["st"], "")
            desc = f"{mark} / {mark_en} · {desc}" if desc else f"{mark} / {mark_en}"
        if not desc:
            desc = "Sąmokslo teorijų žemėlapis · Conspiracy Map"

        page = PAGE.format(
            lang="lt" if name_lt else "en",
            title=html.escape(title, quote=True),
            desc=html.escape(desc, quote=True),
            url=f"{BASE}/t/{sg}.html",
            base=BASE,
            id=html.escape(n["id"], quote=True),
        )
        with open(os.path.join(OUT, sg + ".html"), "w", encoding="utf-8") as fh:
            fh.write(page)
        total += len(page.encode("utf-8"))

    with open(os.path.join(DATA, "graph.json"), "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Dalinimosi puslapių: {len(used)} ({total / 1048576:.1f} MB), graph.json papildytas „sg“")


if __name__ == "__main__":
    main()
