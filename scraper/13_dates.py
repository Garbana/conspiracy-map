"""13 etapas: teorijų atsiradimo metai.

Wikidata datą (P571/P580/P585) turi vos kas penkta teorija – sąmokslo teorijos retai
turi „įkūrimo datą“. Todėl likusias peržiūrim: skriptas iš angliškos santraukos ištraukia
kandidatinius metus, o sprendimą priima žmogus (arba Claude), įrašydamas į data/dates/done/.
Automatiškai pasitikėti negalima: sakinyje „teorija, kilusi 2011 m., teigia, kad dainininkė
mirė 2003 m.“ ankstyviausi metai būtų klaidingi.

    python scraper/13_dates.py cases     – paruošia data/dates/cases/batch_NN.json
    python scraper/13_dates.py merge     – įrašo data/dates/done/*.json į site/data/graph.json

Formatas: {"Q123": {"y": 1947, "p": "year"}}   p: year | decade | century | none
  year    – tikslūs metai („pirmą kartą paskelbta 1947 m.“)
  decade  – dešimtmetis („9 dešimtmetyje“) → y = dešimtmečio pradžia
  century – amžius → y = amžiaus pradžia
  none    – nustatyti neįmanoma (mazgas lieka be datos)
Grafe atsiranda "d" (metai) ir "dp" (tikslumas), jei data ne iš Wikidata.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site", "data")
CASES = os.path.join(ROOT, "data", "dates", "cases")
DONE = os.path.join(ROOT, "data", "dates", "done")
PER_BATCH = 40

YEAR = r'(1[0-9]{3}|20[0-2][0-9])'
HINT = re.compile(
    r'(?:in|since|from|during|by|after|around)\s+(?:the\s+)?(?:early |mid-?|late )?' + YEAR +
    r'|' + YEAR + r's\b'
    r'|(?:first|originated|began|started|emerged|dates? back to|published|proposed)'
    r'[^.]{0,50}?' + YEAR, re.I)


def load(p, d=None):
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return d


def theories():
    g = load(os.path.join(SITE, "graph.json"))
    return g, [n for n in g["nodes"] if n["k"] == "theory"]


def make_cases():
    g, th = theories()
    sums = load(os.path.join(SITE, "summaries.json"), {})
    done = {}
    for p in glob.glob(os.path.join(DONE, "*.json")):
        done.update(load(p, {}))
    todo = [n for n in th if not n.get("d") and n["id"] not in done]
    todo.sort(key=lambda n: -(n.get("dg") or 0))
    os.makedirs(CASES, exist_ok=True)
    for i in range(0, len(todo), PER_BATCH):
        rows = []
        for n in todo[i:i + PER_BATCH]:
            s = (sums.get(n["id"]) or "").replace("\n", " ")
            intro = " ".join(s.split(". ")[:2])[:260]
            # Visi tekste minimi metai su kontekstu – sprendimą priimam iš įrodymų, ne iš atminties
            ctx, seen = [], set()
            for m in re.finditer(YEAR + r's?', s):
                y = m.group(1)
                if y in seen:
                    continue
                seen.add(y)
                ctx.append(s[max(0, m.start() - 55):m.end() + 35].strip())
                if len(ctx) >= 7:
                    break
            rows.append({"id": n["id"], "title": n["t"], "status": n.get("st"),
                         "intro": intro, "years_in_text": ctx})
        with open(os.path.join(CASES, f"batch_{i // PER_BATCH + 1:02d}.json"), "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
    print(f"Teorijų be datos: {len(todo)} | paketų: {(len(todo) + PER_BATCH - 1) // PER_BATCH}"
          f" | jau peržiūrėta: {len(done)}")


def merge():
    g, th = theories()
    done = {}
    for p in sorted(glob.glob(os.path.join(DONE, "*.json"))):
        done.update(load(p, {}))
    n_set = 0
    for n in g["nodes"]:
        d = done.get(n["id"])
        if not d or n.get("d"):
            continue
        if d.get("p") in (None, "none") or not d.get("y"):
            continue
        n["d"] = str(d["y"])
        n["dp"] = d["p"]            # year / decade / century – svetainė rodo „apie“, kai ne year
        n_set += 1
    with open(os.path.join(SITE, "graph.json"), "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, separators=(",", ":"))
    have = sum(1 for n in th if n.get("d"))
    print(f"Įrašyta datų: {n_set} | teorijų su data: {have}/{len(th)}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "cases"
    (make_cases if cmd == "cases" else merge)()
