"""1b etapas: praplėsti paiešką už „Conspiracy theories“ kategorijos ribų.

Pirmasis etapas ėmė tik angliškos Vikipedijos kategorijų medį nuo „Conspiracy theories“,
Wikidata tipą „conspiracy theory“ ir vieną sąrašo puslapį. Todėl pro šalį praėjo viskas,
kas surašyta po gretimomis kategorijomis (pseudoistorija, miesto legendos, mistifikacijos,
ufologija, slaptos draugijos) ir viskas, ko angliškoje Vikipedijoje nėra kategorizuota,
bet yra kitų kalbų sąmokslo teorijų kategorijose.

Šaltiniai:
  A) papildomi angliškų kategorijų medžiai (negilūs – po jais daug ne teorijų)
  B) kitų kalbų Vikipedijų sąmokslo teorijų kategorijos → Wikidata → angliškas straipsnis
  C) Wikidata: P31 = miesto legenda / moralinė panika / pseudoistorija / mistifikacija
     (ieškoma per CirrusSearch „haswbstatement“ – patikimiau nei SPARQL)

Rezultatas:
  data/export/theories_candidates.json  – papildomas naujais kandidatais (senieji nekeičiami)
  data/export/candidates_more.json      – tik naujieji, su šaltiniais (kad matytųsi, iš kur)
  data/export/nonen_candidates.json     – rasti straipsniai BE angliško atitikmens (pvz., vien
                                          lietuviški): pipeline'as jų kol kas neapdoroja, bet
                                          juos galima įtraukti rankomis per data/overrides.json

Tarpinis progresas: data/raw/expand_state.json – nutrūkus tęsia nuo tos pačios vietos.
"""
import json
import os
import re
import sys
from collections import deque

sys.path.insert(0, os.path.dirname(__file__))
from wiki import get_json, wp_query  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "export")
STATE = os.path.join(RAW, "expand_state.json")

# Kategorijos ir gylis. Kuo platesnė kategorija, tuo negiliau leidžiamės.
EN_ROOTS = [
    ("Category:Pseudohistory", 2),
    ("Category:Urban legends", 2),
    ("Category:Hoaxes", 2),
    ("Category:Ufology", 2),
    ("Category:Secret societies", 2),
    ("Category:Moral panics", 2),
    ("Category:Cover-ups", 2),
    ("Category:Disinformation operations", 2),
    ("Category:Fake news", 2),
    ("Category:Pseudoscience", 1),
    ("Category:Paranormal", 1),
    ("Category:Propaganda", 1),
]

# Kitų kalbų sąmokslo teorijų kategorijos. Pirmas tinkamas variantas ir naudojamas.
LANG_CATS = {
    "lt": ["Kategorija:Sąmokslo teorijos"],
    "pl": ["Kategoria:Teorie spiskowe"],
    "ru": ["Категория:Теории заговора", "Категория:Конспирология"],
    "de": ["Kategorie:Verschwörungstheorie", "Kategorie:Verschwörungstheorien"],
    "fr": ["Catégorie:Théorie du complot", "Catégorie:Théories du complot"],
    "es": ["Categoría:Teorías conspirativas", "Categoría:Teorías de la conspiración"],
    "uk": ["Категорія:Теорії змови"],
}
LANG_DEPTH = 2

# Wikidata tipai (patikrinta wbsearchentities): miesto legenda, moralinė panika,
# pseudoistorija, mistifikacija, sąmokslo teorija (pakartotinai – galėjo atsirasti naujų).
WD_CLASSES = {
    "Q189349": "urban legend", "Q2914277": "moral panic", "Q11146759": "pseudohistory",
    "Q190084": "hoax", "Q159535": "conspiracy theory",
}

NOISE = ("theorists", "films", "films by", "books", "novels", "television", "video games", "songs",
         "albums", "websites", "podcasts", "writers", "promoters", "fiction", "comics",
         "organizations", "people", "debunkers", "skeptics", "stubs", "wikipedia",
         "journals", "magazines", "characters", "episodes", "музыка", "фильмы")
# Straipsnių pavadinimai, kurių aiškiai nereikia
SKIP_TITLE = ("list of", "index of", "outline of", "timeline of", "category:", "template:")


def load(p, d):
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return d


def save_state(s):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False)
    os.replace(tmp, STATE)


def crawl(lang, root, max_depth, seen_cats):
    """Kategorijų medis vienoje Vikipedijoje. Grąžina {straipsnis: [kategorijos]}."""
    api = f"https://{lang}.wikipedia.org/w/api.php"
    pages, q = {}, deque([(root, 0)])
    seen_cats.add(root)
    while q:
        cat, depth = q.popleft()
        try:
            for data in wp_query({"list": "categorymembers", "cmtitle": cat, "cmtype": "page|subcat",
                                  "cmlimit": "500", "cmnamespace": "0|14"}, api=api):
                for m in data["query"]["categorymembers"]:
                    t = m["title"]
                    if m["ns"] == 14:
                        low = t.lower()
                        if t in seen_cats or any(n in low for n in NOISE) or depth + 1 > max_depth:
                            continue
                        seen_cats.add(t)
                        q.append((t, depth + 1))
                    elif not any(t.lower().startswith(s) for s in SKIP_TITLE):
                        pages.setdefault(t, []).append(cat)
        except Exception as e:                      # viena bloga kategorija nenutraukia visko
            print(f"   ! {cat}: {e}")
    return pages


def qids_for(lang, titles):
    """Straipsnių pavadinimai → Wikidata QID (per pageprops)."""
    api = f"https://{lang}.wikipedia.org/w/api.php"
    out = {}
    titles = list(titles)
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        for data in wp_query({"titles": "|".join(batch), "prop": "pageprops",
                              "ppprop": "wikibase_item", "redirects": "1"}, api=api):
            for p in data["query"].get("pages", []):
                q = (p.get("pageprops") or {}).get("wikibase_item")
                if q:
                    out[p["title"]] = q
    return out


def sitelinks(qids):
    """QID → {'en': pavadinimas, 'lt': pavadinimas} (tik šie du mums rūpi)."""
    api = "https://www.wikidata.org/w/api.php"
    out = {}
    qids = list(qids)
    for i in range(0, len(qids), 50):
        d = get_json(api, {"action": "wbgetentities", "format": "json", "ids": "|".join(qids[i:i + 50]),
                           "props": "sitelinks", "sitefilter": "enwiki|ltwiki"})
        for q, e in (d.get("entities") or {}).items():
            sl = e.get("sitelinks") or {}
            out[q] = {"en": (sl.get("enwiki") or {}).get("title"),
                      "lt": (sl.get("ltwiki") or {}).get("title")}
    return out


def by_statement(cls):
    """Wikidata CirrusSearch: visi elementai su P31 = cls (patikimiau nei SPARQL)."""
    api = "https://www.wikidata.org/w/api.php"
    found, cont = [], {}
    while True:
        d = get_json(api, {"action": "query", "format": "json", "formatversion": "2",
                           "list": "search", "srsearch": f"haswbstatement:P31={cls}",
                           "srlimit": "500", "srnamespace": "0", **cont})
        found += [r["title"] for r in d.get("query", {}).get("search", [])]
        if "continue" not in d or len(found) > 5000:
            return found
        cont = d["continue"]


def main():
    os.makedirs(RAW, exist_ok=True)
    st = load(STATE, {"en": {}, "lang": {}, "wd": {}})
    seen_cats = set()

    # ---- A) angliškos kategorijos ----
    for cat, depth in EN_ROOTS:
        if cat in st["en"]:
            continue
        print(f"[A] {cat} (gylis {depth})")
        pages = crawl("en", cat, depth, seen_cats)
        st["en"][cat] = sorted(pages)
        print(f"   {len(pages)} straipsnių")
        save_state(st)

    # ---- B) kitų kalbų kategorijos ----
    for lang, names in LANG_CATS.items():
        if lang in st["lang"]:
            continue
        got = {}
        for name in names:
            print(f"[B] {lang}: {name}")
            pages = crawl(lang, name, LANG_DEPTH, set())
            if pages:
                got = pages
                break
        print(f"   {len(got)} straipsnių")
        qm = qids_for(lang, got) if got else {}
        st["lang"][lang] = qm            # {straipsnis: QID}
        print(f"   {len(qm)} su Wikidata ID")
        save_state(st)

    # ---- C) Wikidata tipai ----
    for cls, name in WD_CLASSES.items():
        if cls in st["wd"]:
            continue
        print(f"[C] Wikidata P31={cls} ({name})")
        st["wd"][cls] = by_statement(cls)
        print(f"   {len(st['wd'][cls])} elementų")
        save_state(st)

    # ---- sujungiam ----
    need = set()
    for qs in st["lang"].values():
        need.update(qs.values())
    for qs in st["wd"].values():
        need.update(qs)
    have = load(os.path.join(RAW, "expand_sitelinks.json"), {})
    todo = [q for q in need if q not in have]
    print(f"[D] Wikidata sąsajos: reikia {len(need)}, trūksta {len(todo)}")
    for i in range(0, len(todo), 500):
        have.update(sitelinks(todo[i:i + 500]))
        with open(os.path.join(RAW, "expand_sitelinks.json"), "w", encoding="utf-8") as f:
            json.dump(have, f, ensure_ascii=False)
        print(f"   {min(i + 500, len(todo))}/{len(todo)}")

    # Kokybės filtras. Platesnės kategorijos („Pseudohistory“, „Paranormal“) atitempia
    # tūkstančius paprastų istorijos straipsnių, todėl kandidatu laikom tik tą, kurį
    # patvirtina bent vienas rimtas požymis. Atmestieji saugomi atskirai – nieko nedingsta.
    TITLE_OK = re.compile(
        r'conspiracy|hoax|myth|denial|denialism|pseudo|urban legend|cover-?up|forgery|'
        r'plot\b|panic|truther|misinformation|disinformation|false flag|crisis actor|'
        r'blood libel|fabricat|debunk', re.I)
    wd_titles = set()                       # angliški straipsniai, kurių P31 – mūsų klasė
    for cls, qs in st["wd"].items():
        for q in qs:
            t = (have.get(q) or {}).get("en")
            if t:
                wd_titles.add(t)

    new, nonen = {}, {}
    def add(title, src, qid=None):
        c = new.setdefault(title, {"title": title, "sources": [], "categories": []})
        if src not in c["sources"]:
            c["sources"].append(src)
        if qid:
            c["qid"] = qid

    for cat, titles in st["en"].items():
        for t in titles:
            add(t, "category2")
            new[t]["categories"].append(cat)
    for lang, qs in st["lang"].items():
        for title, q in qs.items():
            sl = have.get(q) or {}
            if sl.get("en"):
                add(sl["en"], f"wiki_{lang}", q)
            else:
                nonen.setdefault(q, {"qid": q, "langs": [], "titles": {}})
                nonen[q]["langs"].append(lang)
                nonen[q]["titles"][lang] = title
                if sl.get("lt"):
                    nonen[q]["titles"]["lt"] = sl["lt"]
    for cls, qs in st["wd"].items():
        for q in qs:
            sl = have.get(q) or {}
            if sl.get("en"):
                add(sl["en"], f"wd_{cls}", q)

    old = {c["title"]: c for c in load(os.path.join(OUT, "theories_candidates.json"), [])}

    def keep(t, c):
        srcs = set(c["sources"])
        langs = [s for s in srcs if s.startswith("wiki_")]
        # Kitų kalbų kategorijų medžiai pasirodė platūs (prancūzų ir ispanų po pusantro tūkstančio
        # straipsnių: rinkimai, įžymybės, filmai), todėl vienos kalbos nepakanka – tik trijų
        # sutapimas arba nepriklausomas požymis.
        if any(s.startswith("wd_") for s in srcs) or t in wd_titles:
            return "Wikidata tipas"
        if TITLE_OK.search(t):
            return "pavadinimas"
        if len(c["categories"]) >= 2:
            return "kelios kategorijos"
        if len(langs) >= 3:
            return "kelios kalbos"
        return None

    fresh, rejected = {}, []
    for t, c in new.items():
        if t in old:
            continue
        why = keep(t, c)
        if why:
            c["why"] = why
            fresh[t] = c
        else:
            rejected.append(c)
    with open(os.path.join(OUT, "candidates_rejected.json"), "w", encoding="utf-8") as f:
        json.dump(sorted(rejected, key=lambda c: c["title"]), f, ensure_ascii=False, indent=1)
    print(f"\n=== SANTRAUKA ===")
    print(f"Rasta iš viso: {len(new)} | jau turėtų: {len(new) - len(fresh)} | NAUJŲ: {len(fresh)}")
    src_count = {}
    for c in fresh.values():
        for s in c["sources"]:
            src_count[s] = src_count.get(s, 0) + 1
    print("Naujų pagal šaltinį:", dict(sorted(src_count.items(), key=lambda x: -x[1])))
    why_count = {}
    for c in fresh.values():
        why_count[c["why"]] = why_count.get(c["why"], 0) + 1
    print("Naujų pagal požymį:", why_count)
    print(f"Atmesta kaip ne teorijos: {len(rejected)} (data/export/candidates_rejected.json)")
    print(f"Be angliško straipsnio (atskirai): {len(nonen)}")

    for t, c in fresh.items():
        c["confidence"] = 1 + len([s for s in c["sources"] if s.startswith("wiki_")])
        old[t] = c
    items = sorted(old.values(), key=lambda c: (-c.get("confidence", 0), c["title"]))
    with open(os.path.join(OUT, "theories_candidates.json"), "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "candidates_more.json"), "w", encoding="utf-8") as f:
        json.dump(sorted(fresh.values(), key=lambda c: c["title"]), f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "nonen_candidates.json"), "w", encoding="utf-8") as f:
        json.dump(sorted(nonen.values(), key=lambda c: c["qid"]), f, ensure_ascii=False, indent=1)
    print(f"Kandidatų faile dabar: {len(items)}")


if __name__ == "__main__":
    main()
