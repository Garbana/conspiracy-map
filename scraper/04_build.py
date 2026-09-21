"""4 etapas: valymas, tipai, temos, svoriai -> SQLite + JSON svetainei.

  A) Wikidata klasių medis (P279) -> tipas pagal artimiausią žinomą šaknį
  B) Kurie įrašai yra teorijos, kurie – susiję subjektai, kurie – triukšmas
  C) Temos (kategorijų sistema) ir regionai iš Vikipedijos kategorijų
  D) Ryšių svoriai (bendri mazgai – JAV, NYT ir pan. – gauna mažą svorį)
  E) data/conspiracy.db + data/export/graph.json

Tarpinis progresas: data/raw/build_state.json
"""
import importlib.util
import json
import math
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict, deque

sys.path.insert(0, os.path.dirname(__file__))
from wiki import get_json  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "enrich", os.path.join(os.path.dirname(__file__), "02_enrich.py"))
enrich = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(enrich)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "export")
STATE = os.path.join(RAW, "build_state.json")
WD_API = "https://www.wikidata.org/w/api.php"
MAX_UP = 6  # kiek lygių kilti klasių medžiu

# Tipų šaknys. Tipas = šaknis, pasiekiama mažiausiu atstumu; lygiu atveju laimi ankstesnė.
ROOTS = [
    # conspiracy theory, hoax, misinformation, disinformation, pseudoscience (ID patikrinti)
    ("theory", ["Q159535", "Q190084", "Q13579947", "Q189656", "Q483677"]),
    ("person", ["Q5", "Q15632617", "Q95074", "Q20643955"]),
    ("media", ["Q11032", "Q1002697", "Q35127", "Q1153191", "Q17232649", "Q3220391",
               "Q1254874", "Q1616075", "Q192283", "Q15265344", "Q41298", "Q11033",
               "Q2001305", "Q15416", "Q1110794", "Q561068"]),
    ("event", ["Q1190554", "Q1656682", "Q198", "Q178561", "Q3199915", "Q2223653",
               "Q273120", "Q41397", "Q10931", "Q124734", "Q8465", "Q21480300", "Q750215"]),
    ("work", ["Q17537576", "Q7725634", "Q11424", "Q47461344", "Q5398426", "Q386724",
              "Q116476516", "Q2188189"]),
    ("place", ["Q2221906", "Q17334923", "Q618123", "Q486972", "Q56061", "Q6256", "Q41176",
               "Q515", "Q82794", "Q839954", "Q3024240", "Q1620908", "Q23442", "Q4022"]),
    ("organization", ["Q43229", "Q7278", "Q327333", "Q4830453", "Q163740", "Q47913",
                      "Q17127659", "Q176799", "Q37726", "Q7210356", "Q155271", "Q2738074",
                      "Q49773", "Q9174"]),
    ("concept", ["Q151885", "Q7257", "Q12909644", "Q11862829", "Q1047113", "Q17737",
                 "Q2135465", "Q23847174", "Q33104279", "Q33104069", "Q1127759",
                 "Q31338769", "Q112193867", "Q16521", "Q12737077", "Q28640", "Q34770"]),
]
ROOT_OF = {q: (i, t) for i, (t, qs) in enumerate(ROOTS) for q in qs}

TITLE_THEORY = re.compile(r"\b(conspiracy|conspiracies|hoax|denial|denialism|cover-?up|"
                          r"theories|myth|false flag|allegations?)\b", re.I)

# Temos: raktažodžiai kategorijų pavadinimuose (ir pavadinime/aprašyme kaip atsarginis variantas)
THEMES = {
    "politics": r"politic|election|government|deep state|new world order|white genocide|"
                r"great replacement|coup|president|communis|fascis|nazi|stolen election|qanon",
    "health": r"vaccin|covid|health|medic|aids|hiv|disease|pharma|cancer|fluorid|pandemic|"
              r"virus|autism|epidemic|drug",
    "ufo": r"ufo|extraterrestrial|alien|ancient astronaut|flying saucer|roswell|area 51|"
           r"reptilian|nibiru",
    "science_tech": r"5g|technolog|space|moon landing|flat earth|scien|nuclear|haarp|"
                    r"chemtrail|internet|artificial|surveillance|computer",
    "history": r"negationism|historical|history|holocaust|genocide denial|pseudohistory|"
               r"revisionis|ancient|medieval|tartar",
    "ethnic_religious": r"antisemit|jewish|jews|zionis|islamophob|muslim|racis|ethnic|"
                        r"anti-catholic|christian|religio|blood libel|satan|occult|"
                        r"freemason|illuminati|secret societ|esoteric",
    "deaths": r"assassination|death|murder|killing|disappearance|suicide|shooting|"
              r"poisoning|crash",
    "war_terror": r"terror|9/11|september 11|war\b|false flag|military|bombing|attack|"
                  r"weapon|army",
    "finance": r"econom|financ|bank|money|federal reserve|gold|currency|debt|rothschild|"
               r"corporat|oil",
    "media_disinfo": r"disinformation|propaganda|fake news|misinformation|hoax|media|"
                     r"censorship|information war|troll|psyop",
    "intelligence": r"\bcia\b|intelligence|espionage|covert|kgb|fsb|mkultra|mossad|"
                    r"\bnsa\b|spy|spies|cointelpro|secret service",
    "environment": r"climate|environment|weather|global warming|ozone|geoengineering|"
                   r"chemtrail",
}
THEME_RE = {k: re.compile(v, re.I) for k, v in THEMES.items()}
REGION_RE = re.compile(r"(?:conspiracy theories|conspiracy theory|misinformation|"
                       r"propaganda|hoaxes|disinformation) (?:in|about|of|involving) (.+)$", re.I)


def load_state():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {"items_wd": {}, "cls": {}}


def save_state(s):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False)
    os.replace(tmp, STATE)


def wbget(ids, props):
    for attempt in range(6):
        d = get_json(WD_API, {"action": "wbgetentities", "ids": "|".join(ids),
                              "props": props, "languages": "en", "format": "json"})
        if "error" not in d:
            return d.get("entities", {})
        print(f"  ! Wikidata: {d['error'].get('info')} – kartoju")
        import time
        time.sleep(10 * (attempt + 1))
    raise RuntimeError("Wikidata nuolat grąžina klaidas (progresas išsaugotas)")


def fetch_items_p31(qids, s):
    todo = [q for q in qids if q not in s["items_wd"]]
    print(f"[A1] Įrašų P31: liko {len(todo)}")
    for i, b in enumerate(enrich.chunks(todo, 50), 1):
        for q, e in wbget(b, "claims").items():
            s["items_wd"][q] = enrich.claim_ids(e, "P31")
        for q in b:
            s["items_wd"].setdefault(q, [])
        if i % 10 == 0:
            save_state(s)
            print(f"   {i * 50}/{len(todo)}")
    save_state(s)


def fetch_class_tree(start, s):
    """Kyla P279 medžiu iki MAX_UP lygių; kiekvienai klasei saugo label ir tėvus."""
    frontier = [q for q in start]
    for level in range(MAX_UP + 1):
        todo = sorted({q for q in frontier if q not in s["cls"]})
        print(f"[A2] Klasių medis, lygis {level}: naujų {len(todo)}")
        for i, b in enumerate(enrich.chunks(todo, 50), 1):
            for q, e in wbget(b, "labels|claims").items():
                s["cls"][q] = {"label": e.get("labels", {}).get("en", {}).get("value"),
                               "p279": enrich.claim_ids(e, "P279")}
            for q in b:
                s["cls"].setdefault(q, {"label": None, "p279": []})
            if i % 20 == 0:
                save_state(s)
                print(f"   {i * 50}/{len(todo)}")
        save_state(s)
        frontier = [p for q in frontier for p in s["cls"].get(q, {}).get("p279", [])]
        if not frontier:
            break


def type_of(p31, s, memo={}):
    best = None  # (atstumas, prioritetas, tipas)
    for c in p31:
        if c not in memo:
            r, seen, dq = None, {c}, deque([(c, 0)])
            while dq:
                q, d = dq.popleft()
                if q in ROOT_OF:
                    cand = (d, ROOT_OF[q][0], ROOT_OF[q][1])
                    r = cand if r is None or cand < r else r
                    continue  # aukščiau nekylam – artimesnė šaknis tikslesnė
                if d < MAX_UP:
                    for p in s["cls"].get(q, {}).get("p279", []):
                        if p not in seen:
                            seen.add(p)
                            dq.append((p, d + 1))
            memo[c] = r
        if memo[c] and (best is None or memo[c] < best):
            best = memo[c]
    return best[2] if best else None


def themes_for(texts):
    out = set()
    for t in texts:
        for k, rx in THEME_RE.items():
            if rx.search(t or ""):
                out.add(k)
    return sorted(out)


def main():
    items = json.load(open(os.path.join(OUT, "items.json"), encoding="utf-8"))
    ents = json.load(open(os.path.join(OUT, "entities.json"), encoding="utf-8"))
    mentions = json.load(open(os.path.join(OUT, "mentions.json"), encoding="utf-8"))
    cats = json.load(open(os.path.join(OUT, "categories.json"), encoding="utf-8"))
    L = json.load(open(os.path.join(RAW, "links_state.json"), encoding="utf-8"))
    s = load_state()

    # ---------- A: tipai ----------
    item_q = [i["id"] for i in items if i["id"].startswith("Q")]
    fetch_items_p31(item_q, s)
    p31_of = dict(s["items_wd"])
    for q, v in L["wd"].items():
        p31_of.setdefault(q, v.get("p31", []))
    fetch_class_tree(sorted({c for v in p31_of.values() for c in v}), s)

    def new_type(eid, title, shortdesc, old):
        if TITLE_THEORY.search(title or ""):
            return "theory"
        t = type_of(p31_of.get(eid, []), s)
        if t:
            return t
        if old == "theory?":
            return "theory?"
        return "concept" if old == "other" else old

    for i in items:
        i["type_old"] = i["type"]
        i["type"] = new_type(i["id"], i["title"], i.get("shortdesc"), i["type"])
    for e in ents:
        e["type"] = new_type(e["id"], e["title"], e.get("shortdesc"), e["type"])
    print("Įrašų tipai:", Counter(i["type"] for i in items).most_common())
    print("Subjektų tipai:", Counter(e["type"] for e in ents).most_common())

    # ---------- B: kurie įrašai lieka ----------
    item_by_id = {i["id"]: i for i in items}
    theory_ids = {i["id"] for i in items if i["type"] in ("theory", "theory?")}
    # Kiek teorijų mini įrašą ir kiek teorijų įrašas mini
    mentioned_by = Counter(m["target"] for m in mentions if m["source"] in theory_ids)
    mentions_th = Counter(m["source"] for m in mentions if m["target"] in theory_ids)
    kept = []
    for i in items:
        clean_cat = any(not cats.get(c, {}).get("noise") for c in i["categories"])
        score = mentioned_by[i["id"]] + mentions_th[i["id"]]
        if i["title"].startswith(("List of", "Lists of", "Index of", "Timeline of")):
            i["role"] = "dropped"  # sąrašų puslapiai – ne teorijos, jų ryšiai klaidintų
        elif i["type"] == "theory":
            i["role"] = "theory"
        elif i["type"] == "theory?" and (clean_cat or score >= 1):
            i["role"] = "theory"
        elif i["confidence"] >= 3 and i["type"] in ("concept", "event", "theory?"):
            i["role"] = "theory"
        elif score >= 2 or (clean_cat and score >= 1):
            i["role"] = "related"
        else:
            i["role"] = "dropped"
        if i["role"] != "dropped":
            kept.append(i)
    print("Įrašų rolės:", Counter(i["role"] for i in items).most_common())
    theory_ids = {i["id"] for i in kept if i["role"] == "theory"}

    # ---------- C: temos ir regionai ----------
    def cat_chain(c, depth=2):
        out, fr = [c], [c]
        for _ in range(depth):
            fr = [p for x in fr for p in cats.get(x, {}).get("parents", [])]
            out += fr
        return out

    for i in kept:
        chain = {x for c in i["categories"] for x in cat_chain(c)}
        chain.discard("Category:Conspiracy theories")
        names = [c.replace("Category:", "") for c in chain]
        th = themes_for(names)
        if not th:
            th = themes_for([i["title"], i.get("shortdesc") or ""])
        i["themes"] = th
        regions = set()
        for n in names:
            m = REGION_RE.search(n)
            if m and not m.group(1).lower().startswith(("the united states by", "popular")):
                regions.add(m.group(1).strip())
        i["regions"] = sorted(regions)
    print("Temos:", Counter(t for i in kept if i["role"] == "theory" for t in i["themes"]).most_common())
    print("Teorijų be temos:", sum(1 for i in kept if i["role"] == "theory" and not i["themes"]))

    # ---------- D: svoriai ----------
    kept_ids = {i["id"] for i in kept}
    ent_by_id = {e["id"]: e for e in ents}
    mentions = [m for m in mentions if m["source"] in kept_ids]
    df = Counter(m["target"] for m in mentions if m["source"] in theory_ids)
    n_th = max(1, len(theory_ids))
    for m in mentions:
        idf = math.log((n_th + 1) / (df.get(m["target"], 0) + 1)) + 0.1
        m["weight"] = round(min(m["count"], 5) ** 0.5 * (2 if m["in_lead"] else 1) * idf, 3)
    for e in ents:
        e["n_theories"] = df.get(e["id"], 0)
        # Bendri mazgai: media visada, kiti – jei minimi > 5 % teorijų
        e["generic"] = e["type"] == "media" or e["n_theories"] > 0.05 * n_th
    print(f"Bendrų (nuslopintų) mazgų: {sum(e['generic'] for e in ents)}")

    # ---------- E: SQLite ----------
    db_path = os.path.join(ROOT, "data", "conspiracy.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    db = sqlite3.connect(db_path)
    db.executescript("""
    CREATE TABLE items(id TEXT PRIMARY KEY, title TEXT, role TEXT, type TEXT, shortdesc TEXT,
        summary TEXT, url TEXT, label_lt TEXT, ltwiki TEXT, date TEXT, lat REAL, lon REAL,
        confidence INT);
    CREATE TABLE entities(id TEXT PRIMARY KEY, title TEXT, type TEXT, shortdesc TEXT,
        label_lt TEXT, date TEXT, lat REAL, lon REAL, n_theories INT, generic INT, is_item INT);
    CREATE TABLE mentions(source TEXT, target TEXT, count INT, in_lead INT, weight REAL);
    CREATE TABLE item_categories(item TEXT, category TEXT);
    CREATE TABLE item_themes(item TEXT, theme TEXT);
    CREATE TABLE item_regions(item TEXT, region TEXT);
    CREATE TABLE categories(name TEXT PRIMARY KEY, depth INT, noise INT, parents TEXT);
    """)
    for i in kept:
        c = i.get("coord") or [None, None]
        db.execute("INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (i["id"], i["title"], i["role"], i["type"], i.get("shortdesc"),
                    i.get("summary"), i.get("url"), i.get("label_lt"), i.get("ltwiki"),
                    i.get("date"), c[0], c[1], i["confidence"]))
        db.executemany("INSERT INTO item_categories VALUES(?,?)", [(i["id"], x) for x in i["categories"]])
        db.executemany("INSERT INTO item_themes VALUES(?,?)", [(i["id"], x) for x in i["themes"]])
        db.executemany("INSERT INTO item_regions VALUES(?,?)", [(i["id"], x) for x in i["regions"]])
    for e in ents:
        c = e.get("coord") or [None, None]
        db.execute("INSERT INTO entities VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (e["id"], e["title"], e["type"], e.get("shortdesc"), e.get("label_lt"),
                    e.get("date"), c[0], c[1], e["n_theories"], int(e["generic"]),
                    int(e.get("is_item", False))))
    db.executemany("INSERT INTO mentions VALUES(?,?,?,?,?)",
                   [(m["source"], m["target"], m["count"], int(m["in_lead"]), m["weight"])
                    for m in mentions])
    db.executemany("INSERT INTO categories VALUES(?,?,?,?)",
                   [(k, v["depth"], int(v["noise"]), json.dumps(v["parents"], ensure_ascii=False))
                    for k, v in cats.items()])
    db.commit()
    db.close()

    # ---------- E: graph.json (kompaktiškas svetainei) ----------
    nodes, node_ids = [], set()
    for i in kept:
        nodes.append({"id": i["id"], "t": i["title"], "k": i["role"], "ty": i["type"],
                      "th": i["themes"], "rg": i["regions"], "d": i.get("date"),
                      "c": i.get("coord"), "sd": i.get("shortdesc"),
                      "lt": i.get("label_lt"), "u": i.get("url")})
        node_ids.add(i["id"])
    for e in ents:
        if e["id"] in node_ids or e["n_theories"] < 2:
            continue
        nodes.append({"id": e["id"], "t": e["title"], "k": "entity", "ty": e["type"],
                      "n": e["n_theories"], "g": int(e["generic"]), "d": e.get("date"),
                      "c": e.get("coord"), "sd": e.get("shortdesc"), "lt": e.get("label_lt")})
        node_ids.add(e["id"])
    edges = [[m["source"], m["target"], m["weight"], int(m["in_lead"])]
             for m in mentions if m["source"] in node_ids and m["target"] in node_ids]
    graph = {"nodes": nodes, "edges": edges, "themes": list(THEMES)}
    with open(os.path.join(OUT, "graph.json"), "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, separators=(",", ":"))

    print("\n=== SANTRAUKA ===")
    print(f"Teorijų: {len(theory_ids)} | susijusių straipsnių: "
          f"{sum(1 for i in kept if i['role'] == 'related')} | "
          f"atmesta: {sum(1 for i in items if i['role'] == 'dropped')}")
    print(f"Grafe: {len(nodes)} mazgų, {len(edges)} ryšių "
          f"({os.path.getsize(os.path.join(OUT, 'graph.json')) / 1e6:.1f} MB)")
    print(f"Duomenų bazė: {os.path.getsize(db_path) / 1e6:.1f} MB")
    print("Top teorijos pagal ryšių skaičių:")
    deg = Counter(m["source"] for m in mentions if m["source"] in theory_ids)
    for q, n in deg.most_common(15):
        print(f"  {n:4d}  {item_by_id[q]['title']}  {item_by_id[q]['themes']}")
    print("Top subjektai (ne bendri):")
    for e in sorted((e for e in ents if not e["generic"]), key=lambda e: -e["n_theories"])[:20]:
        print(f"  {e['n_theories']:4d}  [{e['type']}] {e['title']}")


if __name__ == "__main__":
    main()
