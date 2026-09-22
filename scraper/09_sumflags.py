#!/usr/bin/env python3
"""Pažymi grafe, kurios kalbos santrauka mazgui egzistuoja: "se" (EN), "sl" (LT).

Svetainė iš to žino, kurį santraukų failą siųstis – ir siunčiasi tik vieną (kiekvienas
apie 1 MB suspausto teksto), o antrąjį tik tada, kai skaitytojas paprašo originalo.

Paleidžiama paskutinė, po 07_lt.py ir 08_i18n.py:
    python scraper/09_sumflags.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site", "data")


def ids(name):
    path = os.path.join(SITE, name)
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return set(json.load(f))


def main():
    with open(os.path.join(SITE, "graph.json"), encoding="utf-8") as f:
        g = json.load(f)
    en, lt = ids("summaries.json"), ids("summaries_lt.json")
    n_en = n_lt = 0
    for n in g["nodes"]:
        n.pop("se", None)
        n.pop("sl", None)
        if n["id"] in en:
            n["se"] = 1
            n_en += 1
        if n["id"] in lt:
            n["sl"] = 1
            n_lt += 1
    with open(os.path.join(SITE, "graph.json"), "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Santraukų žymos: EN {n_en}, LT {n_lt} (iš {len(g['nodes'])} mazgų)")


if __name__ == "__main__":
    main()
