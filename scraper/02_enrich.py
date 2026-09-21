"""2 etapas: praturtinti kandidatus ir nustatyti jų tipą.

  A) Vikipedija (po 20 psl.): peradresavimai, santrauka (intro), trumpas aprašymas, Wikidata ID
  B) Wikidata wbgetentities (po 50): P31 (instance of), koordinatės, datos, šalis, LT pavadinimas
  C) P31 klasių pavadinimai -> mūsų tipas (theory / person / place / organization / work / event / other)

Tarpinis progresas: data/raw/enrich_state.json (tęsiama nuo sustojimo vietos).
Rezultatas: data/export/items.json
"""
import json
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
from wiki import get_json, wp_query  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "export")
STATE = os.path.join(RAW, "enrich_state.json")
WD_API = "https://www.wikidata.org/w/api.php"


def load_state():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {"wp": {}, "wd": {}, "classes": {}}


def save_state(s):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False)
    os.replace(tmp, STATE)


def chunks(xs, n):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


# ---------- A: Vikipedija ----------
def fetch_wikipedia(titles, s):
    todo = [t for t in titles if t not in s["wp"]]
    print(f"[A] Vikipedija: {len(titles) - len(todo)} jau turima, liko {len(todo)}")
    t0 = time.time()
    for i, batch in enumerate(chunks(todo, 20), 1):
        got = {}
        for data in wp_query({"titles": "|".join(batch), "redirects": "1",
                              "prop": "extracts|pageprops|info", "exintro": "1",
                              "explaintext": "1", "exlimit": "20", "inprop": "url",
                              "ppprop": "wikibase_item|wikibase-shortdesc|disambiguation"}):
            q = data.get("query", {})
            back = {}
            for n in q.get("normalized", []):
                back[n["to"]] = n["from"]
            for r in q.get("redirects", []):
                back[r["to"]] = back.get(r["from"], r["from"])
            for p in q.get("pages", []):
                orig = back.get(p["title"], p["title"])
                rec = got.setdefault(orig, {"title": p["title"]})
                if p.get("missing"):
                    rec["missing"] = True
                    continue
                pp = p.get("pageprops", {})
                rec["pageid"] = p.get("pageid")
                rec["url"] = p.get("fullurl")
                rec["qid"] = pp.get("wikibase_item", rec.get("qid"))
                rec["shortdesc"] = pp.get("wikibase-shortdesc", rec.get("shortdesc"))
                rec["disambiguation"] = "disambiguation" in pp
                if p.get("extract"):
                    rec["extract"] = p["extract"]
        for t in batch:
            s["wp"][t] = got.get(t, {"title": t, "missing": True})
        if i % 10 == 0:
            save_state(s)
        done = len(titles) - len(todo) + i * 20
        rate = i * 20 / (time.time() - t0)
        print(f"   {min(done, len(titles)):5d}/{len(titles)} | ~{(len(todo) - i * 20) / rate / 60:4.1f} min liko")
    save_state(s)


# ---------- B: Wikidata ----------
def claim_ids(ent, prop):
    out = []
    for c in ent.get("claims", {}).get(prop, []):
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(v, dict) and "id" in v:
            out.append(v["id"])
    return out


def claim_time(ent, prop):
    for c in ent.get("claims", {}).get(prop, []):
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(v, dict) and "time" in v:
            return v["time"].lstrip("+")[:10]
    return None


def fetch_wikidata(qids, s, key, full=True, save=None):
    save = save or save_state
    todo = [q for q in qids if q not in s[key]]
    print(f"[{'B' if full else 'C'}] Wikidata ({key}): liko {len(todo)}")
    for i, batch in enumerate(chunks(todo, 50), 1):
        props = "labels|descriptions|claims|sitelinks" if full else "labels"
        for attempt in range(6):
            data = get_json(WD_API, {"action": "wbgetentities", "ids": "|".join(batch),
                                     "props": props, "languages": "en|lt", "format": "json",
                                     "sitefilter": "enwiki|ltwiki"})
            if "error" not in data:
                break
            print(f"  ! Wikidata klaida: {data['error'].get('info', data['error'])} – kartoju")
            time.sleep(10 * (attempt + 1))
        else:
            raise RuntimeError("Wikidata nuolat grąžina klaidas – sustoju (progresas išsaugotas)")
        for q, ent in data.get("entities", {}).items():
            lab = ent.get("labels", {})
            rec = {"label_en": lab.get("en", {}).get("value"),
                   "label_lt": lab.get("lt", {}).get("value")}
            if full:
                coord = None
                for c in ent.get("claims", {}).get("P625", []):
                    v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
                    if v:
                        coord = [v["latitude"], v["longitude"]]
                        break
                rec.update({
                    "desc_en": ent.get("descriptions", {}).get("en", {}).get("value"),
                    "p31": claim_ids(ent, "P31"),
                    "country": claim_ids(ent, "P17")[:3],
                    "coord": coord,
                    "date": claim_time(ent, "P585") or claim_time(ent, "P580")
                            or claim_time(ent, "P571") or claim_time(ent, "P569"),
                    "ltwiki": ent.get("sitelinks", {}).get("ltwiki", {}).get("title"),
                })
            s[key][q] = rec
        for q in batch:
            s[key].setdefault(q, {"missing": True})
        if i % 10 == 0:
            save(s)
        print(f"   {min(i * 50, len(todo)):5d}/{len(todo)}")
    save(s)


# ---------- C: tipo klasifikacija ----------
# Tikrinama pagal P31 klasės pavadinimą (en), pirmas atitikmuo laimi – tvarka svarbi.
TYPE_RULES = [
    ("theory", ("conspiracy theor", "hoax", "urban legend", "misinformation", "disinformation",
                "pseudoscience", "pseudohistory", "denial", "moral panic", "fringe theory",
                "hypothesis", "canard", "myth", "trope", "allegation", "legend", "propaganda",
                "false claim", "fake news", "cover-up", "theory")),
    ("person", ("human", "fictional human", "fictional character")),
    ("work", ("film", "book", "novel", "television", "episode", "album", "song", "single",
              "video game", "documentary", "literary work", "written work", "podcast",
              "web series", "comic", "magazine", "newspaper", "website", "periodical",
              "publication", "painting", "musical", "play", "series")),
    ("event", ("event", "attack", "shooting", "assassination", "killing", "murder", "death",
               "disaster", "crash", "accident", "war", "battle", "election", "incident",
               "massacre", "bombing", "riot", "protest", "trial", "scandal", "affair",
               "operation", "pandemic", "epidemic", "outbreak", "genocide", "persecution",
               "purge", "hijacking", "disappearance", "explosion", "fire", "coup", "crisis")),
    ("organization", ("organization", "organisation", "company", "political party", "agency",
                      "movement", "group", "society", "association", "foundation", "business",
                      "enterprise", "institute", "broadcaster", "network", "club", "union",
                      "religious", "sect", "cult", "order", "lodge", "army", "unit", "service",
                      "militia", "government", "ministry", "council", "committee", "program",
                      "project", "channel", "station")),
    ("place", ("city", "town", "village", "country", "state", "island", "mountain", "building",
               "region", "province", "municipality", "site", "location", "base", "facility",
               "structure", "monument", "lake", "river", "area", "district", "county",
               "archaeological", "cave", "pyramid", "crater", "sovereign")),
]


TITLE_THEORY = ("conspiracy", "hoax", "denial", "cover-up", "allegations", "myth", "theories")


def classify(p31_labels, shortdesc, in_theory_cat, title=""):
    if any(k in title.lower() for k in TITLE_THEORY):
        return "theory"
    labels = [l.lower() for l in p31_labels if l]
    for typ, keys in TYPE_RULES:
        if any(k in l for l in labels for k in keys):
            return typ
    sd = (shortdesc or "").lower()
    if any(k in sd for k in ("conspiracy", "hoax", "theory", "claim", "allegation")):
        return "theory"
    if not labels and in_theory_cat:
        return "theory?"
    return "other"


def main():
    with open(os.path.join(OUT, "theories_candidates.json"), encoding="utf-8") as f:
        cands = json.load(f)
    s = load_state()
    fetch_wikipedia([c["title"] for c in cands], s)

    qids = sorted({r["qid"] for r in s["wp"].values() if r.get("qid")})
    fetch_wikidata(qids, s, "wd", full=True)

    classes = sorted({c for q in qids for c in s["wd"].get(q, {}).get("p31", [])})
    fetch_wikidata(classes, s, "classes", full=False)

    def clabel(q):
        return s["classes"].get(q, {}).get("label_en") or q

    items, seen = [], {}
    for c in cands:
        wp = s["wp"].get(c["title"], {})
        if wp.get("missing") or wp.get("disambiguation"):
            continue
        key = wp.get("qid") or wp["title"]
        if key in seen:  # du kandidatai nukreipia į tą patį straipsnį
            prev = seen[key]
            prev["sources"] = sorted(set(prev["sources"]) | set(c["sources"]))
            prev["categories"] = sorted(set(prev["categories"]) | set(c["categories"]))
            continue
        wd = s["wd"].get(wp.get("qid"), {})
        p31 = [clabel(q) for q in wd.get("p31", [])]
        in_cat = "category" in c["sources"]
        it = {
            "id": key, "title": wp["title"], "url": wp.get("url"),
            "type": classify(p31, wp.get("shortdesc"), in_cat, wp["title"]),
            "instance_of": p31, "shortdesc": wp.get("shortdesc") or wd.get("desc_en"),
            "summary": wp.get("extract"),
            "label_lt": wd.get("label_lt"), "ltwiki": wd.get("ltwiki"),
            "coord": wd.get("coord"), "date": wd.get("date"), "country": wd.get("country", []),
            "categories": c["categories"], "sources": c["sources"],
            "confidence": c["confidence"],
        }
        seen[key] = it
        items.append(it)

    with open(os.path.join(OUT, "items.json"), "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)

    print("\n=== SANTRAUKA ===")
    print(f"Įrašų: {len(items)} (be Wikidata ID: {sum(1 for i in items if not i['id'].startswith('Q'))})")
    for t, n in Counter(i["type"] for i in items).most_common():
        print(f"  {t:13s} {n}")
    print("Dažniausios neklasifikuotų ('other') P31 klasės:")
    oc = Counter(l for i in items if i["type"] == "other" for l in i["instance_of"])
    for l, n in oc.most_common(25):
        print(f"  {n:4d}  {l}")


if __name__ == "__main__":
    main()
