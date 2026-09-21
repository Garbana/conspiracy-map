"""6 etapas: vaidmenų peržiūros rezultatai -> duomenų bazė ir graph.json.

Paleidžiama po 04_build.py ir 05_relevance.py.
  - data/roles/done/*.json: {teorija: {"status": ..., "roles": {subjektas: vaidmuo}}}
  - Peržiūrėta teorija: branduolys = ryšiai su vaidmeniu. Kiti ryšiai – išplėstinis sluoksnis.
  - Neperžiūrėta teorija: branduolys = automatinis (mentions.tier == 'core' iš 05).
  - status 'not_theory' -> įrašas tampa 'related'; kiti statusai įrašomi į items.status
    (rankiniai data/overrides.json statusai turi pirmenybę).
Išvestis: DB lentelė roles, atnaujinti items/mentions, data/export/graph.json (kraštai su vaidmeniu ir sluoksniu).
"""
import json
import os
import sqlite3
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "conspiracy.db")
DONE = os.path.join(ROOT, "data", "roles", "done")
GRAPH = os.path.join(ROOT, "data", "export", "graph.json")


def main():
    reviewed = {}
    for f in sorted(os.listdir(DONE)):
        if f.endswith(".json"):
            reviewed.update(json.load(open(os.path.join(DONE, f), encoding="utf-8")))
    ov = json.load(open(os.path.join(ROOT, "data", "overrides.json"), encoding="utf-8"))
    manual_status = {k for k in list(ov.get("status", {})) + list(ov.get("add", {})) if not k.startswith("_")}

    db = sqlite3.connect(DB)
    db.execute("DROP TABLE IF EXISTS roles")
    db.execute("CREATE TABLE roles(theory TEXT, entity TEXT, role TEXT)")
    db.executemany("INSERT INTO roles VALUES(?,?,?)",
                   [(t, e, r) for t, v in reviewed.items() for e, r in v.get("roles", {}).items()])
    db.execute("CREATE INDEX IF NOT EXISTS idx_mentions_st ON mentions(source, target)")
    cols = [r[1] for r in db.execute("PRAGMA table_info(mentions)")]
    if "role" not in cols:
        db.execute("ALTER TABLE mentions ADD COLUMN role TEXT")
    if "tier" not in cols:
        db.execute("ALTER TABLE mentions ADD COLUMN tier TEXT")
    db.execute("UPDATE mentions SET role = NULL")
    # Jei 05 dar nepaleistas (tier nėra) – neperžiūrėtų teorijų visi ryšiai laikomi branduoliu
    db.execute("UPDATE mentions SET tier = 'core' WHERE tier IS NULL")
    titles = dict(db.execute("SELECT id, title FROM items"))
    n_status = n_not = 0
    for tid, v in reviewed.items():
        st = v.get("status")
        if st == "not_theory":
            db.execute("UPDATE items SET role='related' WHERE id=? AND role='theory'", (tid,))
            n_not += 1
        elif st and titles.get(tid) not in manual_status:
            db.execute("UPDATE items SET status=? WHERE id=?", (st, tid))
            n_status += 1
        db.execute("UPDATE mentions SET tier='extended' WHERE source=?", (tid,))
        for eid, role in v.get("roles", {}).items():
            db.execute("UPDATE mentions SET role=?, tier='core' WHERE source=? AND target=?", (role, tid, eid))

    # Neperžiūrėti straipsniai (susiję, ne teorijos): branduolys = ryšiai su teorijomis ir su subjektais,
    # kurie jau yra kurios nors teorijos branduolyje. Visa kita – išplėstinis sluoksnis.
    theory_ids = {i for (i,) in db.execute("SELECT id FROM items WHERE role='theory'")}
    core_targets = {t for (t,) in db.execute(
        "SELECT DISTINCT target FROM mentions WHERE tier='core' AND role IS NOT NULL")}
    rows = db.execute("SELECT source, target FROM mentions").fetchall()
    upd = []
    for s, t in rows:
        if s in reviewed:
            continue
        upd.append(("core" if (t in theory_ids or t in core_targets) else "extended", s, t))
    db.executemany("UPDATE mentions SET tier=? WHERE source=? AND target=?", upd)
    db.commit()

    # ---- graph.json: kraštai [šaltinis, tikslas, svoris, įžanga, branduolys(1/0), vaidmuo] ----
    g = json.load(open(GRAPH, encoding="utf-8"))
    info = {(s, t): (tier, role) for s, t, tier, role in
            db.execute("SELECT source, target, tier, role FROM mentions")}
    item_meta = {i: (role, status) for i, role, status in db.execute("SELECT id, role, status FROM items")}
    for n in g["nodes"]:
        if n["id"] in item_meta:
            role, status = item_meta[n["id"]]
            n["k"] = role
            if status:
                n["st"] = status
    edges = []
    for s, t, w, lead, *_ in g["edges"]:
        tier, role = info.get((s, t), (None, None))
        e = [s, t, w, lead, 1 if tier == "core" else 0]
        if role:
            e.append(role)
        edges.append(e)
    g["edges"] = edges
    g["reviewed"] = len(reviewed)
    with open(GRAPH, "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, separators=(",", ":"))

    core = sum(1 for e in edges if e[4])
    print(f"Peržiūrėta teorijų: {len(reviewed)} | statusų: {n_status} | ne teorijos: {n_not}")
    print(f"Kraštų: {len(edges)} | branduolyje: {core} ({core / max(1, len(edges)):.0%})")
    print("Vaidmenys:", Counter(e[5] for e in edges if len(e) > 5).most_common())
    print("Statusai:", Counter(st for (st,) in db.execute(
        "SELECT status FROM items WHERE role='theory' AND status IS NOT NULL")).most_common())
    db.close()


if __name__ == "__main__":
    main()
