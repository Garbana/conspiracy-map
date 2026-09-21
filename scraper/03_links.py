"""3 etapas: ryšiai teorija <-> subjektas (asmenys, vietos, organizacijos, įvykiai...).

  A) Teorijų straipsnių wikitext (po 50) -> [[nuorodos]] tekste.
     Šablonų ({{navbox}} ir pan.) ir <ref> nuorodos neįtraukiamos – jos kurtų netikrus ryšius.
  B) Nuorodų tikslai, paminėti >= MIN_THEORIES teorijose -> kanoninis pavadinimas + Wikidata ID
  C) Wikidata: tipas, koordinatės, datos (pernaudojama iš 02_enrich)

Tarpinis progresas: data/raw/links_state.json
Rezultatas: data/export/entities.json, data/export/mentions.json
"""
import importlib.util
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from wiki import wp_query  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "enrich", os.path.join(os.path.dirname(__file__), "02_enrich.py"))
enrich = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(enrich)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "export")
STATE = os.path.join(RAW, "links_state.json")

HUB_TYPES = ("theory", "theory?", "other", "event")  # iš kurių straipsnių renkam nuorodas
MIN_THEORIES = 2
SKIP_NS = ("file:", "image:", "category:", "wikipedia:", "wp:", "help:", "template:",
           "portal:", "wikt:", "wiktionary:", "s:", "commons:", "special:", "media:", ":")

LINK_RE = re.compile(r"\[\[([^\[\]|#]+)(?:#[^\[\]|]*)?(?:\|[^\[\]]*)?\]\]")
REF_RE = re.compile(r"<ref[^>/]*/>|<ref[^>]*>.*?</ref>", re.S | re.I)
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


def strip_templates(text):
    """Pašalina {{...}} (su įdėjimais) – ten navboxai, infobox'ai, citavimai."""
    out, depth, i = [], 0, 0
    while i < len(text):
        if text.startswith("{{", i):
            depth += 1
            i += 2
        elif text.startswith("}}", i) and depth:
            depth -= 1
            i += 2
        else:
            if not depth:
                out.append(text[i])
            i += 1
    return "".join(out)


def parse_links(wikitext):
    t = COMMENT_RE.sub("", wikitext)
    t = REF_RE.sub("", t)
    t = strip_templates(t)
    # Galinės sekcijos – nuorodų sąrašai, ne turinys
    t = re.split(r"\n==\s*(See also|References|Notes|Further reading|External links|"
                 r"Bibliography|Sources|Citations)\s*==", t, flags=re.I)[0]
    lead = re.split(r"\n==[^=]", t, maxsplit=1)[0]
    counts, in_lead = Counter(), set()
    for part, is_lead in ((lead, True), (t[len(lead):], False)):
        for m in LINK_RE.finditer(part):
            target = m.group(1).strip().replace("_", " ")
            if not target or target.lower().startswith(SKIP_NS):
                continue
            target = target[0].upper() + target[1:]
            counts[target] += 1
            if is_lead:
                in_lead.add(target)
    return counts, in_lead


def load_state():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {"links": {}, "resolve": {}, "wd": {}, "classes": {}}


def save_state(s):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False)
    os.replace(tmp, STATE)


def fetch_links(hubs, s):
    todo = [h for h in hubs if h not in s["links"]]
    print(f"[A] Wikitext: {len(hubs) - len(todo)} jau turima, liko {len(todo)}")
    t0 = time.time()
    for i, batch in enumerate(enrich.chunks(todo, 50), 1):
        for data in wp_query({"titles": "|".join(batch), "prop": "revisions",
                              "rvprop": "content", "rvslots": "main"}):
            for p in data.get("query", {}).get("pages", []):
                revs = p.get("revisions")
                if not revs:
                    continue
                c, lead = parse_links(revs[0]["slots"]["main"].get("content", ""))
                s["links"][p["title"]] = {"counts": dict(c), "lead": sorted(lead)}
        for t in batch:
            s["links"].setdefault(t, {"counts": {}, "lead": []})
        if i % 5 == 0:
            save_state(s)
        rate = i * 50 / (time.time() - t0)
        print(f"   {min(i * 50, len(todo)):5d}/{len(todo)} | ~{max(0, len(todo) - i * 50) / rate / 60:4.1f} min liko")
    save_state(s)


def resolve_titles(titles, s):
    todo = [t for t in titles if t not in s["resolve"]]
    print(f"[B] Nuorodų tikslai -> Wikidata ID: liko {len(todo)}")
    t0 = time.time()
    for i, batch in enumerate(enrich.chunks(todo, 50), 1):
        for data in wp_query({"titles": "|".join(batch), "redirects": "1", "prop": "pageprops",
                              "ppprop": "wikibase_item|wikibase-shortdesc|disambiguation"}):
            q = data.get("query", {})
            back = {n["to"]: n["from"] for n in q.get("normalized", [])}
            for r in q.get("redirects", []):
                back[r["to"]] = back.get(r["from"], r["from"])
            for p in q.get("pages", []):
                orig = back.get(p["title"], p["title"])
                pp = p.get("pageprops", {})
                if p.get("missing") or p.get("invalid") or "disambiguation" in pp:
                    s["resolve"][orig] = None
                else:
                    s["resolve"][orig] = {"title": p["title"], "qid": pp.get("wikibase_item"),
                                          "shortdesc": pp.get("wikibase-shortdesc")}
        for t in batch:
            s["resolve"].setdefault(t, None)
        if i % 10 == 0:
            save_state(s)
        rate = i * 50 / (time.time() - t0)
        print(f"   {min(i * 50, len(todo)):6d}/{len(todo)} | ~{max(0, len(todo) - i * 50) / rate / 60:4.1f} min liko")
    save_state(s)


def main():
    with open(os.path.join(OUT, "items.json"), encoding="utf-8") as f:
        items = json.load(f)
    by_title = {i["title"]: i for i in items}
    hubs = [i["title"] for i in items if i["type"] in HUB_TYPES]
    s = load_state()
    fetch_links(hubs, s)

    # Kiek skirtingų teorijų (hub'ų) mini kiekvieną tikslą
    df = Counter()
    for h in hubs:
        for t in s["links"].get(h, {}).get("counts", {}):
            df[t] += 1
    targets = sorted(t for t, n in df.items() if n >= MIN_THEORIES)
    print(f"   Unikalių nuorodų: {len(df)}, iš jų >= {MIN_THEORIES} teorijose: {len(targets)}")
    resolve_titles(targets, s)

    qids = sorted({r["qid"] for r in s["resolve"].values() if r and r.get("qid")})
    enrich.fetch_wikidata(qids, s, "wd", full=True)
    classes = sorted({c for q in qids for c in s["wd"].get(q, {}).get("p31", [])})
    enrich.fetch_wikidata(classes, s, "classes", full=False)

    def clabel(q):
        return s["classes"].get(q, {}).get("label_en") or q

    # ---- subjektai ----
    item_by_id = {i["id"]: i for i in items}
    entities = {}
    for t in targets:
        r = s["resolve"].get(t)
        if not r:
            continue
        eid = r.get("qid") or r["title"]
        if eid in entities:
            continue
        if eid in item_by_id:  # jau turim iš 2 etapo – imam jo tipą
            it = item_by_id[eid]
            entities[eid] = {"id": eid, "title": it["title"], "type": it["type"],
                             "shortdesc": it["shortdesc"], "coord": it["coord"],
                             "date": it["date"], "label_lt": it["label_lt"], "is_item": True}
            continue
        wd = s["wd"].get(r.get("qid"), {})
        p31 = [clabel(q) for q in wd.get("p31", [])]
        entities[eid] = {"id": eid, "title": r["title"],
                         "type": enrich.classify(p31, r.get("shortdesc"), False, ""),
                         "instance_of": p31, "shortdesc": r.get("shortdesc") or wd.get("desc_en"),
                         "coord": wd.get("coord"), "date": wd.get("date"),
                         "label_lt": wd.get("label_lt"), "is_item": False}

    # ---- paminėjimai ----
    mentions = []
    resolved_id = {}
    for t in targets:
        r = s["resolve"].get(t)
        if r:
            resolved_id[t] = r.get("qid") or r["title"]
    for h in hubs:
        src = by_title[h]["id"]
        L = s["links"].get(h, {})
        lead = set(L.get("lead", []))
        agg = defaultdict(lambda: [0, False])
        for t, n in L.get("counts", {}).items():
            eid = resolved_id.get(t)
            if not eid or eid == src:
                continue
            agg[eid][0] += n
            agg[eid][1] |= t in lead
        for eid, (n, in_lead) in agg.items():
            mentions.append({"source": src, "target": eid, "count": n, "in_lead": in_lead})

    deg = Counter(m["target"] for m in mentions)
    for e in entities.values():
        e["n_theories"] = deg.get(e["id"], 0)
    ents = sorted((e for e in entities.values() if e["n_theories"] >= MIN_THEORIES),
                  key=lambda e: -e["n_theories"])
    keep = {e["id"] for e in ents}
    mentions = [m for m in mentions if m["target"] in keep]

    with open(os.path.join(OUT, "entities.json"), "w", encoding="utf-8") as f:
        json.dump(ents, f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "mentions.json"), "w", encoding="utf-8") as f:
        json.dump(mentions, f, ensure_ascii=False)

    print("\n=== SANTRAUKA ===")
    print(f"Straipsnių (hub'ų) analizuota: {len(hubs)}")
    print(f"Subjektų (>= {MIN_THEORIES} straipsniuose): {len(ents)}")
    for t, n in Counter(e["type"] for e in ents).most_common():
        print(f"  {t:13s} {n}")
    print(f"Paminėjimų (ryšių): {len(mentions)}, iš jų įžangoje: {sum(m['in_lead'] for m in mentions)}")
    print("Dažniausiai minimi:")
    for e in ents[:30]:
        print(f"  {e['n_theories']:4d}  [{e['type']}] {e['title']}")


if __name__ == "__main__":
    main()
