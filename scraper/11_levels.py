#!/usr/bin/env python3
"""Žaidimo „Kelias pas anunakius“ lygiai → site/data/levels.json.

Žaidimo grafas – tas pats, kurį žaidėjas mato žemėlapyje su numatytais filtrais:
esminiai ryšiai, be bendrinių mazgų ir žiniasklaidos, tik mazgai su bent 2 esminiais
ryšiais. Tai svarbu: jei skaičiuotume kitaip, „trumpiausias kelias“ nesutaptų su tuo,
ką žaidėjas gali nueiti.

Startai parinkti rankomis – atpažįstami ir įvairūs; skriptas tik patikrina, ar jų
atstumas iki anunakių toks, kokio tikimasi, ir įrašo trumpiausio kelio ilgį.

    python scraper/11_levels.py
"""
import collections
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site", "data")
TARGET = "Q676379"          # Anunnaki / Anunakiai

# (lygis, starto ID, laukiamas atstumas, kiek papildomų žingsnių leidžiama)
LEVELS = [
    ("Q421",         2, 3),   # Neatpažintas skraidantis objektas
    ("Q11704324",    2, 2),   # Sąmokslo teorijos apie masonus
    ("Q1931364",     3, 3),   # Klimato kaitos neigimas
    ("Q1268748",     3, 2),   # Satanistinių ritualų mitas
    ("Q68090786",    4, 3),   # Clintonų „lavonų sąrašas“
    ("Q737979",      4, 2),   # Eurabijos sąmokslo teorija
    ("Q160944",      4, 1),   # Durklo į nugarą mitas
    ("Q1073494",     5, 2),   # Muilas iš žmonių lavonų
    ("Q104423071",   5, 1),   # Kurdų neigimas Turkijoje
    ("Q56064174",    6, 1),   # Straightwashing – vienintelis 6 žingsnių mazgas žemėlapyje
]


# Mazgo tipas – lygiai taip pat, kaip svetainės kindOf(): teorijoms ir susijusiems
# straipsniams Wikidata tipas neturi reikšmės, „media“ filtras galioja tik esybėms.
def kind_of(n):
    if n["k"] == "theory":
        return "theory"
    if n["k"] == "related":
        return "related"
    return n.get("ty") or "concept"


def game_graph(g):
    """Ryšiai, kuriais žaidėjas gali eiti (tas pats, ką rodo žemėlapis be filtrų).

    Svarbu sutapti su naršykle: ji dubliuotas briaunas sulieja į vieną, todėl ir čia
    skaičiuojam unikalius kaimynus, o ne eilutes.
    """
    nodes = {n["id"]: n for n in g["nodes"]}
    core_nb = collections.defaultdict(set)
    for e in g["edges"]:
        if (e[4] if len(e) > 4 else 1) and e[0] != e[1]:
            core_nb[e[0]].add(e[1])
            core_nb[e[1]].add(e[0])

    def ok(i):
        n = nodes[i]
        return not n.get("g") and kind_of(n) != "media" and (len(core_nb[i]) >= 2 or i == TARGET)

    adj = collections.defaultdict(set)
    for i, nb in core_nb.items():
        if not ok(i):
            continue
        for j in nb:
            if ok(j):
                adj[i].add(j)
                adj[j].add(i)
    return nodes, adj


def distances(adj, src):
    d = {src: 0}
    q = collections.deque([src])
    while q:
        u = q.popleft()
        for v in adj[u]:
            if v not in d:
                d[v] = d[u] + 1
                q.append(v)
    return d


def main():
    with open(os.path.join(SITE, "graph.json"), encoding="utf-8") as f:
        g = json.load(f)
    nodes, adj = game_graph(g)
    dist = distances(adj, TARGET)

    out, bad = [], []
    for i, (start, want, slack) in enumerate(LEVELS, 1):
        if start not in nodes:
            bad.append(f"{i}: nėra mazgo {start}")
            continue
        got = dist.get(start)
        if got is None:
            bad.append(f"{i}: {nodes[start]['t']} – anunakių nepasiekia")
            continue
        if got != want:
            bad.append(f"{i}: {nodes[start]['t']} – tikėtasi {want}, gauta {got} ž.")
        out.append({"lvl": i, "start": start, "dist": got, "budget": got + slack})

    reach = collections.Counter(dist.values())
    data = {
        "target": TARGET,
        "levels": out,
        # atsitiktiniam režimui: kiek mazgų yra kiekvienu atstumu (informacijai)
        "reach": {str(k): v for k, v in sorted(reach.items())},
        "built": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
    }
    with open(os.path.join(SITE, "levels.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    for lv in out:
        n = nodes[lv["start"]]
        print(f"  {lv['lvl']:2d}. {lv['dist']} ž. (biudžetas {lv['budget']}) – {n.get('lt') or n['t']}")
    print(f"\nPasiekiama iš viso: {len(dist)} mazgų; atstumai: {dict(sorted(reach.items()))}")
    if bad:
        print("\nPROBLEMOS:")
        for b in bad:
            print("  -", b)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
