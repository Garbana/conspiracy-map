"""Patikrina subjektų vertimus: kiekvienas atvejis peržiūrėtas (išverstas arba pažymėtas "keep").

Naudojimas: python scraper/check_i18n_ents.py 01
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
n = sys.argv[1]
cases = json.load(open(os.path.join(ROOT, "data", "i18n", "cases_ents", f"batch_{n}.json"), encoding="utf-8"))
done = json.load(open(os.path.join(ROOT, "data", "i18n", "done_ents", f"batch_{n}.json"), encoding="utf-8"))
err = 0
for c in cases:
    d = done.get(c["id"])
    if d is None:
        print(f"! {c['id']} {c['title']}: nepersvarstyta"); err += 1
    elif not d.get("t") and not d.get("keep"):
        print(f"! {c['id']} {c['title']}: tuščias vertimas"); err += 1
extra = set(done) - {c["id"] for c in cases}
if extra:
    print(f"! Nežinomi ID: {sorted(extra)}"); err += 1
kept = sum(1 for d in done.values() if d.get("keep"))
print(f"{len(done) - kept} vertimų, {kept} palikta originalo kalba, klaidų: {err}")
