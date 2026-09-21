"""1 etapas: surasti visas sąmokslo teorijas.

Šaltiniai:
  A) Vikipedijos kategorijų medis nuo 'Category:Conspiracy theories'
  B) Wikidata: instance of (P31) / subclass of (P279) -> conspiracy theory (Q17379835)
  C) Nuorodos iš 'List of conspiracy theories'

Rezultatas: data/export/theories_candidates.json ir data/export/categories.json
"""
import json
import os
import sys
from collections import deque

sys.path.insert(0, os.path.dirname(__file__))
from wiki import sparql, wp_query  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "export")

ROOT_CAT = "Category:Conspiracy theories"
MAX_DEPTH = 4
# Kategorijos, kurios ne teorijos, o apie jas (žmonės, filmai, knygos...) – nenusileidžiam gilyn
NOISE = ("theorists", "films", "books", "novels", "television", "video games", "songs",
         "albums", "websites", "podcasts", "writers", "promoters", "fiction", "comics",
         "organizations", "people", "debunkers", "skeptics", "stubs", "wikipedia")


STATE = os.path.join(RAW, "crawl_state.json")
SAVE_EVERY = 20  # kategorijų


def save_state(cats, pages, q, done=False):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"cats": cats, "queue": list(q), "done": done,
                   "pages": {t: {"pageid": p["pageid"], "categories": sorted(p["categories"])}
                             for t, p in pages.items()}}, f, ensure_ascii=False)
    os.replace(tmp, STATE)  # atominis įrašymas – nutrūkus failas nesugadinamas


def load_state():
    if not os.path.exists(STATE):
        return None
    with open(STATE, encoding="utf-8") as f:
        s = json.load(f)
    pages = {t: {"pageid": p["pageid"], "categories": set(p["categories"])}
             for t, p in s["pages"].items()}
    return s["cats"], pages, deque(s["queue"]), s["done"]


def crawl_categories():
    print(f"[A] Kategorijų medis nuo {ROOT_CAT} (gylis {MAX_DEPTH})")
    st = load_state()
    if st:
        cats, pages, q, done = st
        print(f"   Tęsiu: {len(cats)} kat., {len(pages)} psl., eilėje {len(q)}")
        if done:
            return cats, pages
    else:
        cats = {ROOT_CAT: {"depth": 0, "parents": [], "noise": False}}
        pages = {}  # title -> {pageid, categories:set}
        q = deque([ROOT_CAT])
    n = 0
    while q:
        cat = q[0]  # iš eilės išimam tik apdoroję – taip nutrūkus kategorija bus kartojama
        info = cats[cat]
        for data in wp_query({"list": "categorymembers", "cmtitle": cat,
                              "cmtype": "page|subcat", "cmlimit": "500",
                              "cmnamespace": "0|14"}):
            for m in data["query"]["categorymembers"]:
                t = m["title"]
                if m["ns"] == 14:
                    if t not in cats:
                        noise = info["noise"] or any(n in t.lower() for n in NOISE)
                        cats[t] = {"depth": info["depth"] + 1, "parents": [cat], "noise": noise}
                        if cats[t]["depth"] < MAX_DEPTH and not noise:
                            q.append(t)
                    elif cat not in cats[t]["parents"]:
                        cats[t]["parents"].append(cat)
                else:
                    p = pages.setdefault(t, {"pageid": m["pageid"], "categories": set()})
                    p["categories"].add(cat)
        q.popleft()
        n += 1
        print(f"   {len(cats):5d} kat. | {len(pages):5d} psl. | eilėje {len(q):4d} | {cat}")
        if n % SAVE_EVERY == 0:
            save_state(cats, pages, q)
    save_state(cats, pages, q, done=True)
    return cats, pages


def from_wikidata():
    print("[B] Wikidata SPARQL")
    # Paprasčiausia užklausa (tik tiesioginis P31). Wikidata dažnai perkrauta – jei nepavyksta,
    # žingsnį praleidžiam: QID visiems straipsniams gausim 2 etape per MediaWiki pageprops.
    try:
        rows = sparql("""
        SELECT ?item ?enwiki WHERE {
          ?item wdt:P31 wd:Q17379835 .
          ?enwiki schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> .
        }""", retries=4)
    except RuntimeError as e:
        print(f"   ! Wikidata nepasiekiama, praleidžiu ({e})")
        return []
    out = []
    for r in rows:
        out.append({
            "qid": r["item"]["value"].rsplit("/", 1)[-1],
            "label": None,
            "enwiki": r.get("enwiki", {}).get("value"),
            "ltwiki": None,
        })
    print(f"   {len(out)} įrašų Wikidatoje")
    return out


def from_list_page():
    print("[C] 'List of conspiracy theories' nuorodos")
    links = set()
    for data in wp_query({"titles": "List of conspiracy theories", "prop": "links",
                          "plnamespace": "0", "pllimit": "max"}):
        for p in data["query"]["pages"]:
            for l in p.get("links", []):
                links.add(l["title"])
    print(f"   {len(links)} nuorodų")
    return links


def title_from_url(u):
    import urllib.parse
    return urllib.parse.unquote(u.rsplit("/wiki/", 1)[-1]).replace("_", " ")


def main():
    os.makedirs(RAW, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    cats, pages = crawl_categories()
    wd = from_wikidata()
    listed = from_list_page()

    cand = {}
    for t, p in pages.items():
        clean = [c for c in p["categories"] if not cats[c]["noise"]]
        c = cand.setdefault(t, {"title": t, "sources": [], "categories": []})
        c["categories"] = sorted(p["categories"])
        c["sources"].append("category" if clean else "category_noise")
    for w in wd:
        if not w["enwiki"]:
            continue
        t = title_from_url(w["enwiki"])
        c = cand.setdefault(t, {"title": t, "sources": [], "categories": []})
        c["sources"].append("wikidata")
        c["qid"] = w["qid"]
        if w["ltwiki"]:
            c["lt_title"] = title_from_url(w["ltwiki"])
    for t in listed:
        c = cand.setdefault(t, {"title": t, "sources": [], "categories": []})
        c["sources"].append("list_page")

    # Patikimumo balas: kiek šaltinių patvirtina
    for c in cand.values():
        s = set(c["sources"])
        c["confidence"] = (("category" in s) * 2 + ("wikidata" in s) * 2 + ("list_page" in s))

    cats_out = {k: {**v} for k, v in cats.items()}
    with open(os.path.join(OUT, "categories.json"), "w", encoding="utf-8") as f:
        json.dump(cats_out, f, ensure_ascii=False, indent=1)
    with open(os.path.join(RAW, "wikidata_conspiracy.json"), "w", encoding="utf-8") as f:
        json.dump(wd, f, ensure_ascii=False, indent=1)
    items = sorted(cand.values(), key=lambda c: (-c["confidence"], c["title"]))
    with open(os.path.join(OUT, "theories_candidates.json"), "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)

    print("\n=== SANTRAUKA ===")
    print(f"Kategorijų: {len(cats)} (triukšmo: {sum(v['noise'] for v in cats.values())})")
    print(f"Kandidatų iš viso: {len(cand)}")
    for lvl in range(5, -1, -1):
        n = sum(1 for c in cand.values() if c["confidence"] == lvl)
        if n:
            print(f"  patikimumas {lvl}: {n}")


if __name__ == "__main__":
    main()
