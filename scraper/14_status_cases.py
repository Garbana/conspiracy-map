#!/usr/bin/env python3
"""Paruošia bylas teorijų būsenoms peržiūrėti (paneigta / ginčijama / įrodyta).

Praplėtus paiešką atsirado šimtai naujų teorijų, mistifikacijų ir miesto legendų,
kurios dar neturi būsenos. Skriptas surenka tas, kurioms jos trūksta, ir kiekvienai
duoda pavadinimą, trumpą Wikidata aprašymą bei pirmus santraukos sakinius – iš jų
matyti, ką apie teiginį sako pati Vikipedija.

    python scraper/14_status_cases.py

Rezultatas: data/status/cases/batch_NN.json
Peržiūrėta būsena rašoma į data/roles/done/batch_NNN.json ({"Q123": {"status": "debunked"}}),
nes tą patį failų rinkinį jau skaito scraper/06_roles.py.
"""
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site", "data")
CASES = os.path.join(ROOT, "data", "status", "cases")
PER_BATCH = 45


def main():
    with open(os.path.join(SITE, "graph.json"), encoding="utf-8") as f:
        g = json.load(f)
    with open(os.path.join(SITE, "summaries.json"), encoding="utf-8") as f:
        sums = json.load(f)
    done = set()
    for p in glob.glob(os.path.join(ROOT, "data", "roles", "done", "*.json")):
        with open(p, encoding="utf-8") as f:
            done |= {k for k, v in json.load(f).items() if v.get("status")}

    todo = [n for n in g["nodes"] if n["k"] == "theory" and not n.get("st") and n["id"] not in done]
    todo.sort(key=lambda n: -(n.get("dg") or 0))
    os.makedirs(CASES, exist_ok=True)
    for old in glob.glob(os.path.join(CASES, "*.json")):
        os.remove(old)
    for i in range(0, len(todo), PER_BATCH):
        rows = []
        for n in todo[i:i + PER_BATCH]:
            s = (sums.get(n["id"]) or "").replace("\n", " ")
            rows.append({"id": n["id"], "title": n["t"], "sd": n.get("sd") or "",
                         "intro": " ".join(s.split(". ")[:2])[:300]})
        with open(os.path.join(CASES, f"batch_{i // PER_BATCH + 1:02d}.json"), "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
    print(f"Be būsenos: {len(todo)} | paketų: {(len(todo) + PER_BATCH - 1) // PER_BATCH}")


if __name__ == "__main__":
    main()
