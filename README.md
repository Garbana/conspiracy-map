# Conspiracy Map

Open-source interactive map of conspiracy theories built from Wikipedia and Wikidata.
Theories, the people, places, organizations and events they mention, and how they connect.

Each theory keeps a link to its source article. The map shows what is *claimed*, not what is true.

## Current dataset

- 371 conspiracy theories (every one reviewed: 291 debunked, 50 disputed, 30 confirmed),
  ~1,500 related articles
- 4,334 reviewed roles linking theories to people, organizations, places and events:
  accused, promoter, victim/target, subject, event, place, debunker/investigator, related theory
- ~9,400 nodes, ~74,000 links (core layer ≈ 21,000 links; the rest is an optional "all mentions" layer)
- 12 themes, ~20 automatically detected clusters

## Pipeline

Python (standard library + `truststore`) and Node.js.

| Step | Script | Output |
|---|---|---|
| 1. Discover theories (category tree, Wikidata, list page) | `scraper/01_discover.py` | `data/export/theories_candidates.json` |
| 2. Summaries, Wikidata IDs, types | `scraper/02_enrich.py` | `data/export/items.json` |
| 3. Links from article text → entities | `scraper/03_links.py` | `data/export/entities.json`, `mentions.json` |
| 4. Type hierarchy, themes, weights, database | `scraper/04_build.py` | `data/conspiracy.db`, `data/export/graph.json` |
| 5. Relevance score (optional, ranks the extended layer) | `scraper/05_relevance.py` | `mentions.score/tier` |
| 6. Merge reviewed roles and statuses | `scraper/06_roles.py` | `data/conspiracy.db`, `graph.json` |
| 7. Layout + clusters for the website | `layout/layout.mjs` | `site/data/graph.json`, `summaries.json` |
| 8. Lithuanian summaries and links (lt.wikipedia.org) | `scraper/07_lt.py` | `site/data/summaries_lt.json`, `graph.json` |
| 9. Lithuanian theory titles and summaries (translations) | `scraper/08_i18n.py` | `site/data/summaries_lt.json`, `graph.json` |
| 10. Sharing image (optional, after a re-layout) | `layout/og.mjs` | `site/og.png` |

Manual corrections live in `data/overrides.json`; role reviews in `data/roles/` (see its README);
Lithuanian translations of all theories in `data/i18n/done/` (written by Claude from the English
Wikipedia intro, checked with `scraper/check_i18n.py NN`; the site labels them as such);
cluster names in `data/cluster_names.json` (keyed by each cluster's main theory, so they survive re-layout —
the layout uses a fixed random seed).

Every step saves progress to `data/raw/` and resumes where it stopped.

```bash
pip install truststore
python scraper/01_discover.py
python scraper/02_enrich.py
python scraper/03_links.py
python scraper/04_build.py
python scraper/06_roles.py
cd layout && npm install && node layout.mjs && cd ..
python scraper/07_lt.py
python scraper/08_i18n.py
python -m http.server 8765 --directory site
```

## Website

`site/` is a static site (Sigma.js + graphology, WebGL): search, theme and type filters,
cluster/type/theme coloring, a card with summary and all connections for each node,
shareable links (`#Q815614`). It can be hosted for free on GitHub Pages —
live at [garbana.github.io/conspiracy-map](https://garbana.github.io/conspiracy-map/).

Selecting a node (by search, by click or by tap) lights it up with all of its direct connections and
quiets the rest of the map: unrelated nodes stop reacting to the cursor, so the selection holds still.
Clicking a connected node steps across that link — the walked **trail** stays drawn as a gold line with
numbered steps and can branch, the trail bar at the top jumps back to any step, and × or Esc ends it.
On phones the card is a bottom sheet (with a grab handle to collapse it), so the map stays visible.

An **About** panel (the link at the bottom of the left panel, Esc to close) explains where the data
comes from, what the statuses and roles mean, and the limitations. Its numbers are read from the
loaded graph, so they never go stale. Shared links carry an Open Graph card: `site/og.png` is a real
screenshot of the map, regenerated with `node layout/og.mjs` (needs Playwright and a local server).

The interface is bilingual (English / Lithuanian). The language comes from `?lang=en` / `?lang=lt`,
then the visitor's saved choice, then the browser language. All interface strings live in one
`I18N` dictionary in `site/index.html`. Lithuanian content priority: lt.wikipedia article →
reviewed translation → Wikidata label → original English title.

## Data license

Text from Wikipedia is licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/);
Wikidata is CC0.
