"""8 etapas: Claude vertimai (data/i18n/done/*.json) → svetainės duomenys.

Paleidžiama po 07_lt.py. Lietuviškų pavadinimų ir santraukų pirmenybė:
  1. straipsnis lietuviškoje Vikipedijoje (07_lt.py jau įrašė santrauką);
  2. Claude vertimas iš data/i18n/done/ (santrauka pažymima mazgo lauku "ltm": 1,
     svetainė prie jos rodo pastabą, kad tai ne Vikipedijos tekstas);
  3. Wikidata lietuviška etiketė (jau yra lauke "lt");
  4. originalus pavadinimas.
Vertimų pavadinimas ("t") visada pakeičia Wikidata etiketę – jis parinktas rankiniu būdu.
"""
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site", "data")


def main():
    tr = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "i18n", "done", "*.json"))):
        with open(p, encoding="utf-8") as f:
            tr.update(json.load(f))

    with open(os.path.join(SITE, "graph.json"), encoding="utf-8") as f:
        g = json.load(f)
    sp = os.path.join(SITE, "summaries_lt.json")
    with open(sp, encoding="utf-8") as f:
        sums = json.load(f)

    titles = summaries = 0
    missing = []
    for n in g["nodes"]:
        n.pop("ltm", None)
        d = tr.get(n["id"])
        if not d:
            if n["k"] == "theory":
                missing.append(n["id"])
            continue
        if d.get("t"):
            n["lt"] = d["t"]
            titles += 1
        # Vikipedijos santrauka svarbesnė už mūsų vertimą
        if d.get("s") and not sums.get(n["id"]):
            sums[n["id"]] = d["s"]
            n["ltm"] = 1
            summaries += 1

    with open(os.path.join(SITE, "graph.json"), "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, separators=(",", ":"))
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(sums, f, ensure_ascii=False)
    print(f"Vertimų: {len(tr)} | pritaikyta pavadinimų: {titles}, santraukų: {summaries}")
    if missing:
        print(f"Teorijos be vertimo ({len(missing)}): {' '.join(missing[:20])}")


if __name__ == "__main__":
    main()
