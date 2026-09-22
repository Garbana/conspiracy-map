"""Patikrina vertimų bylą: kiekviena teorija išversta, pavadinimas yra, santrauka – jei nėra LT straipsnio.

Naudojimas: python scraper/check_i18n.py 01
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
n = sys.argv[1]
cases = json.load(open(os.path.join(ROOT, "data", "i18n", "cases", f"batch_{n}.json"), encoding="utf-8"))
done = json.load(open(os.path.join(ROOT, "data", "i18n", "done", f"batch_{n}.json"), encoding="utf-8"))
err = 0
for c in cases:
    d = done.get(c["id"])
    if not d or not d.get("t"):
        print(f"! {c['id']} {c['title']}: nėra pavadinimo"); err += 1; continue
    if not c["has_lt_article"] and not d.get("s"):
        print(f"! {c['id']} {c['title']}: nėra santraukos"); err += 1
    if len(d.get("s", "")) > 700:
        print(f"! {c['id']}: santrauka per ilga ({len(d['s'])})"); err += 1
extra = set(done) - {c["id"] for c in cases}
if extra:
    print(f"! Nežinomi ID: {sorted(extra)}"); err += 1
print(f"{len(done)} vertimų, klaidų: {err}")
