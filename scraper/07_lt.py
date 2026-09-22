"""7 etapas: lietuviškos santraukos ir nuorodos iš lt.wikipedia.org.

Paleidžiama po layout/layout.mjs (papildo site/data/graph.json):
  - mazgams, turintiems straipsnį lietuviškoje Vikipedijoje, pridedamas laukas "lw" (LT straipsnio pavadinimas)
  - site/data/summaries_lt.json – LT santraukos (įžangos)
Tarpinis progresas: data/raw/lt_state.json
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from wiki import get_json  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
STATE = os.path.join(RAW, "lt_state.json")
GRAPH = os.path.join(ROOT, "site", "data", "graph.json")
LT_API = "https://lt.wikipedia.org/w/api.php"


def load(p, default):
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return default


def main():
    items = load(os.path.join(ROOT, "data", "export", "items.json"), [])
    links = load(os.path.join(RAW, "links_state.json"), {"wd": {}})
    ltwiki = {i["id"]: i["ltwiki"] for i in items if i.get("ltwiki")}
    for q, v in links.get("wd", {}).items():
        if v.get("ltwiki"):
            ltwiki.setdefault(q, v["ltwiki"])

    g = load(GRAPH, None)
    node_ids = {n["id"] for n in g["nodes"]}
    want = {q: t for q, t in ltwiki.items() if q in node_ids}
    s = load(STATE, {"extract": {}})
    todo = [t for t in sorted(set(want.values())) if t not in s["extract"]]
    print(f"LT straipsnių žemėlapio mazgams: {len(want)} | reikia parsiųsti: {len(todo)}")
    t0 = time.time()
    for i in range(0, len(todo), 20):
        batch = todo[i:i + 20]
        cont = {}
        while True:
            d = get_json(LT_API, {"action": "query", "format": "json", "formatversion": "2",
                                  "titles": "|".join(batch), "prop": "extracts", "exintro": "1",
                                  "explaintext": "1", "exlimit": "20", "redirects": "1", **cont})
            q = d.get("query", {})
            back = {r["to"]: r["from"] for r in q.get("redirects", [])}
            back.update({n["to"]: n["from"] for n in q.get("normalized", [])})
            for p in q.get("pages", []):
                if p.get("extract"):
                    s["extract"][back.get(p["title"], p["title"])] = p["extract"].strip()
            if "continue" not in d:
                break
            cont = d["continue"]
        for t in batch:
            s["extract"].setdefault(t, "")
        if (i // 20) % 10 == 0:
            with open(STATE, "w", encoding="utf-8") as f:
                json.dump(s, f, ensure_ascii=False)
            print(f"   {min(i + 20, len(todo))}/{len(todo)} ({time.time() - t0:.0f}s)")
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False)

    sums = {}
    for n in g["nodes"]:
        t = want.get(n["id"])
        if not t:
            continue
        n["lw"] = t
        if s["extract"].get(t):
            sums[n["id"]] = s["extract"][t]
    with open(GRAPH, "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(ROOT, "site", "data", "summaries_lt.json"), "w", encoding="utf-8") as f:
        json.dump(sums, f, ensure_ascii=False)
    kinds = {}
    for n in g["nodes"]:
        if n["id"] in sums:
            kinds[n["k"]] = kinds.get(n["k"], 0) + 1
    print(f"LT santraukų: {len(sums)} | pagal rūšį: {kinds} | "
          f"LT pavadinimų iš viso: {sum(1 for n in g['nodes'] if n.get('lt'))}")


if __name__ == "__main__":
    main()
