"""Patikrina vaidmenų peržiūros failą: ID turi būti iš tos teorijos kandidatų, kodai – leistini.

Naudojimas: python scraper/check_roles.py 001
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROLES = {"acc", "pro", "vic", "sub", "evt", "loc", "deb", "rel"}
STATUS = {"confirmed", "debunked", "disputed", "not_theory"}

n = sys.argv[1]
todo = json.load(open(os.path.join(ROOT, "data", "roles", "cases", f"batch_{n}.json"), encoding="utf-8"))
done = json.load(open(os.path.join(ROOT, "data", "roles", "done", f"batch_{n}.json"), encoding="utf-8"))
cands = {c["id"]: {x[0] for x in c["candidates"]} for c in todo}
errors = 0
for tid, r in done.items():
    if tid not in cands:
        print(f"! {tid}: teorijos nėra byloje"); errors += 1; continue
    if r.get("status") not in STATUS:
        print(f"! {tid}: blogas statusas {r.get('status')}"); errors += 1
    for eid, role in r.get("roles", {}).items():
        if eid not in cands[tid]:
            print(f"! {tid}: {eid} nėra kandidatų sąraše"); errors += 1
        if role not in ROLES:
            print(f"! {tid}: {eid} blogas vaidmuo {role}"); errors += 1
missing = set(cands) - set(done)
if missing:
    print(f"! Neperžiūrėta: {sorted(missing)}"); errors += 1
n_roles = sum(len(r.get("roles", {})) for r in done.values())
print(f"{len(done)} teorijų, {n_roles} vaidmenų, klaidų: {errors}")
