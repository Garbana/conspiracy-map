"""5 etapas: ryšių aktualumo balas + bylos vaidmenų peržiūrai.

Kiekvienam paminėjimui (straipsnis -> subjektas) skaičiuojamas balas iš signalų:
  - įžanga (x2) ir paminėjimų skaičius
  - specifiškumas mūsų korpuse (kiek teorijų straipsnių mini subjektą)
  - specifiškumas visoje Vikipedijoje (kiek straipsnių nurodo subjektą – cirrusdoc incoming_links)
  - abipusė nuoroda (subjekto straipsnis pats nurodo teoriją)
  - subjekto tipas (asmuo/organizacija/įvykis > vieta > kūrinys > sąvoka > žiniasklaida)
  - subjekto aprašyme yra "conspiracy/hoax/UFO..." žodžių
Rezultatas:
  - mentions.score + mentions.tier ('core' / 'extended') duomenų bazėje
  - data/roles/todo/batch_NNN.json – bylos vaidmenų peržiūrai (santrauka + top kandidatai)

Tarpinis progresas: data/raw/relevance_state.json
"""
import json
import math
import os
import re
import sqlite3
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from wiki import wp_query  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
DB = os.path.join(ROOT, "data", "conspiracy.db")
STATE = os.path.join(RAW, "relevance_state.json")
ROLES = os.path.join(ROOT, "data", "roles")

CAND_PER_THEORY = 40   # kiek kandidatų į bylą vaidmenų peržiūrai
CORE_PER_THEORY = 20   # automatinis branduolys (kol nėra vaidmenų)
BATCH = 20             # teorijų vienoje byloje
TYPE_PRIOR = {"person": 1.0, "organization": 1.0, "event": 1.0, "theory": 1.2, "theory?": 1.1,
              "place": 0.8, "work": 0.6, "concept": 0.5, "media": 0.2}
TOPICAL = re.compile(r"conspir|hoax|ufo|extraterrestrial|paranormal|cult|occult|propagand|"
                     r"disinformation|pseudo|denial|intelligence|covert|secret|assassinat|"
                     r"cryptid|fringe|esoteric|antisemit|far-right|militia", re.I)


def load_state():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {"cirrus": {}}


def save_state(s):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False)
    os.replace(tmp, STATE)


def fetch_cirrus(titles, theory_titles, s):
    """incoming_links + kurios iš mūsų teorijų yra subjekto išeinančiose nuorodose."""
    todo = [t for t in titles if t not in s["cirrus"]]
    print(f"[A] Vikipedijos nuorodų statistika: liko {len(todo)}")
    tt = {t.replace(" ", "_"): t for t in theory_titles}
    for i in range(0, len(todo), 20):
        batch = todo[i:i + 20]
        for data in wp_query({"titles": "|".join(batch), "prop": "cirrusdoc", "redirects": "1"}):
            q = data.get("query", {})
            back = {n["to"]: n["from"] for n in q.get("normalized", [])}
            for r in q.get("redirects", []):
                back[r["to"]] = back.get(r["from"], r["from"])
            for p in q.get("pages", []):
                docs = p.get("cirrusdoc") or [{}]
                src = docs[0].get("source", {})
                out = [tt[l] for l in src.get("outgoing_link", []) if l in tt]
                s["cirrus"][back.get(p["title"], p["title"])] = {
                    "in": src.get("incoming_links"), "th": out}
        for t in batch:
            s["cirrus"].setdefault(t, {"in": None, "th": []})
        if (i // 20) % 25 == 0:
            save_state(s)
            print(f"   {min(i + 20, len(todo))}/{len(todo)}")
    save_state(s)


def main():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    items = {r["id"]: dict(r) for r in db.execute("SELECT * FROM items")}
    ents = {r["id"]: dict(r) for r in db.execute("SELECT * FROM entities")}
    mentions = [dict(r) for r in db.execute("SELECT * FROM mentions")]
    hubs = {i for i, r in items.items() if r["role"] in ("theory", "related")}
    theory_titles = [r["title"] for r in items.values() if r["role"] == "theory"]
    title_of = {**{k: v["title"] for k, v in ents.items()}, **{k: v["title"] for k, v in items.items()}}

    # Kandidatai statistikai: subjektai, kurie patenka į kurios nors teorijos top-60 pagal bazinį balą
    df = defaultdict(int)
    for m in mentions:
        if m["source"] in hubs:
            df[m["target"]] += 1
    n_hubs = len(hubs)

    def base(m):
        e = ents.get(m["target"]) or items.get(m["target"]) or {}
        idf = math.log((n_hubs + 1) / (df[m["target"]] + 1))
        return (math.sqrt(min(m["count"], 5)) * (2 if m["in_lead"] else 1) * idf
                * TYPE_PRIOR.get(e.get("type"), 0.7))

    by_src = defaultdict(list)
    for m in mentions:
        if m["source"] in hubs:
            m["base"] = base(m)
            by_src[m["source"]].append(m)
    # Vikipedijos statistika brangi (~2 psl./s) – imam tik teorijų top kandidatus
    need = set()
    for src, ms in by_src.items():
        ms.sort(key=lambda m: -m["base"])
        if items[src]["role"] == "theory":
            need.update(m["target"] for m in ms[:CAND_PER_THEORY])
    # PRELIM=1: tik bylos pagal bazinį balą (be Vikipedijos statistikos, DB nekeičiama)
    prelim = bool(os.environ.get("PRELIM"))
    s = {"cirrus": {}} if prelim else load_state()
    if not prelim:
        fetch_cirrus(sorted({title_of[t] for t in need if t in title_of}), theory_titles, s)

    # ---- galutinis balas ----
    for src, ms in by_src.items():
        src_title = items[src]["title"]
        for m in ms:
            e = ents.get(m["target"]) or items.get(m["target"]) or {}
            c = s["cirrus"].get(title_of.get(m["target"], ""), {})
            inc = c.get("in")
            # Visuotinis specifiškumas: 100 nuorodų -> ~1.4, 10 tūkst. -> ~0.7, >100 tūkst. -> ~0.5
            spec = 1.0 if inc is None and m["target"] not in need else \
                max(0.4, min(1.8, math.log(20000) / math.log(20 + (inc if inc is not None else 500000))))
            mutual = 1.5 if src_title in c.get("th", []) else 1.0
            topical = 1.3 if TOPICAL.search((e.get("shortdesc") or "") + " " + (e.get("title") or "")) else 1.0
            m["score"] = round(m["base"] * spec * mutual * topical, 3)
        ms.sort(key=lambda m: -m["score"])
        for rank, m in enumerate(ms):
            m["rank"] = rank
            m["tier"] = "core" if rank < CORE_PER_THEORY and m["score"] >= 1.0 else "extended"

    if prelim:
        for ms in by_src.values():
            ms.sort(key=lambda m: -m["base"])
    cols = [r[1] for r in db.execute("PRAGMA table_info(mentions)")] if not prelim else None
    for col, typ in (("score", "REAL"), ("rank", "INT"), ("tier", "TEXT")):
        if not prelim and col not in cols:
            db.execute(f"ALTER TABLE mentions ADD COLUMN {col} {typ}")
    if not prelim:
      db.executemany("UPDATE mentions SET score=?, rank=?, tier=? WHERE source=? AND target=?",
                   [(m["score"], m["rank"], m["tier"], m["source"], m["target"])
                    for ms in by_src.values() for m in ms])
      db.commit()

    # ---- bylos vaidmenų peržiūrai (tik teorijos, dar neperžiūrėtos) ----
    os.makedirs(os.path.join(ROLES, "todo"), exist_ok=True)
    os.makedirs(os.path.join(ROLES, "done"), exist_ok=True)
    done = set()
    for f in os.listdir(os.path.join(ROLES, "done")):
        if f.endswith(".json"):
            done.update(json.load(open(os.path.join(ROLES, "done", f), encoding="utf-8")).keys())
    for f in os.listdir(os.path.join(ROLES, "todo")):
        os.remove(os.path.join(ROLES, "todo", f))
    theories = sorted((i for i in items.values() if i["role"] == "theory" and i["id"] not in done),
                      key=lambda i: -len(by_src.get(i["id"], [])))
    cases = []
    for t in theories:
        summ = (t["summary"] or "").strip()
        if len(summ) > 900:
            summ = summ[:900].rsplit(". ", 1)[0] + "."
        cands = []
        for m in by_src.get(t["id"], [])[:CAND_PER_THEORY]:
            e = ents.get(m["target"]) or items.get(m["target"]) or {}
            cands.append([m["target"], e.get("title"), e.get("type"), (e.get("shortdesc") or "")[:80],
                          ("L" if m["in_lead"] else "") + str(m["count"])])
        cases.append({"id": t["id"], "title": t["title"], "summary": summ, "candidates": cands})
    for n, i in enumerate(range(0, len(cases), BATCH), 1):
        with open(os.path.join(ROLES, "todo", f"batch_{n:03d}.json"), "w", encoding="utf-8") as f:
            json.dump(cases[i:i + BATCH], f, ensure_ascii=False, indent=0)

    core = sum(1 for ms in by_src.values() for m in ms if m["tier"] == "core")
    core_ents = {m["target"] for ms in by_src.values() for m in ms if m["tier"] == "core"}
    print("\n=== SANTRAUKA ===")
    print(f"Paminėjimų: {sum(len(v) for v in by_src.values())} | branduolyje: {core} "
          f"| branduolio subjektų: {len(core_ents)} (iš {len(ents)})")
    print(f"Bylų vaidmenų peržiūrai: {len(cases)} teorijų -> {math.ceil(len(cases) / BATCH)} failų "
          f"(jau peržiūrėta: {len(done)})")
    for tid in ("Q815614", "Q211036"):
        if tid in by_src:
            print(f"\n{items[tid]['title']} – top 12:")
            for m in by_src[tid][:12]:
                print(f"  {m['score']:6.2f}  {title_of.get(m['target'])}")


if __name__ == "__main__":
    main()
