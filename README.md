# Conspiracy Map

Open-source interactive map of conspiracy theories built from Wikipedia and Wikidata.
Theories, the people, places, organizations and events they mention, and how they connect.

Each theory keeps a link to its source article. The map shows what is *claimed*, not what is true.

## Current dataset

A snapshot; the site's **About** panel counts the graph it has loaded, so its figures are never stale.

- 597 conspiracy theories (every one reviewed: 493 debunked, 63 disputed, 41 confirmed),
  ~1,700 related articles
- ~4,300 reviewed roles linking theories to people, organizations, places and events:
  accused, promoter, victim/target, subject, event, place, debunker/investigator, related theory
- ~11,500 nodes, ~92,000 links (core layer ≈ 22,600 links; the rest is an optional "all mentions" layer)
- 12 themes, 19 automatically detected clusters

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
| 9. Lithuanian titles and summaries (translations) | `scraper/08_i18n.py` | `site/data/summaries_lt.json`, `graph.json` |
| 10. Which language's summary each node has | `scraper/09_sumflags.py` | `site/data/graph.json` (`se` / `sl`) |
| 11. A share page per node (title, summary, status in its meta) | `scraper/10_share_pages.py` | `site/t/*.html`, `graph.json` (`sg`) |
| 12. Game levels (start nodes, shortest distances, budgets) | `scraper/11_levels.py` | `site/data/levels.json` |
| 13. A share page per game level (its name and result in its meta) | `scraper/12_game_pages.py` | `site/g/<lang>/*.html` |
| 14. Sharing image (optional, after a re-layout) | `layout/og.mjs` | `site/og.png` |

Manual corrections live in `data/overrides.json`; role reviews in `data/roles/` (see its README);
Lithuanian translations of all theories in `data/i18n/done/` (written by Claude from the English
Wikipedia intro, checked with `scraper/check_i18n.py NN`; the site labels them as such), and of the
400 most-linked organizations, events, concepts and works in `data/i18n/done_ents/` (`{"keep": 1}`
marks a name reviewed and deliberately left in the original; personal names are never translated,
checked with `scraper/check_i18n_ents.py NN`);
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
python scraper/09_sumflags.py
python scraper/10_share_pages.py
python scraper/11_levels.py
python scraper/12_game_pages.py
python -m http.server 8765 --directory site
```

## Website

`site/` is a static site (Sigma.js + graphology, WebGL): search, theme and type filters,
cluster/type/theme coloring, a card with summary and all connections for each node,
shareable links (`#Q815614`). Search ignores diacritics (`samokslo` finds `sąmokslo`) and also looks
at the short descriptions. Only the summaries of the language being read are downloaded (~1 MB each),
the other only when the reader asks for the original. It can be hosted for free on GitHub Pages —
live at [garbana.github.io/conspiracy-map](https://garbana.github.io/conspiracy-map/).

Selecting a node (by search, by click or by tap) lights it up with all of its direct connections and
quiets the rest of the map: unrelated nodes stop reacting to the cursor, so the selection holds still.
Clicking a connected node steps across that link — the walked **trail** stays drawn as a gold line with
numbered steps and can branch, the trail bar at the top jumps back to any step, and × or Esc ends it.
On phones the card is a bottom sheet (with a grab handle to collapse it), so the map stays visible.

Chat apps and crawlers do not run JavaScript, and a `#fragment` never reaches the server, so a link
into the map could only ever show the site's own title. Each node therefore has its own small page,
`site/t/<slug>-<id>.html`, whose meta tags carry *that* node's name, status and summary ("Paneigta /
Debunked · …") and which immediately forwards a human to the map — language and trail included
(`?lang=lt&p=Q51213808,Q1658150`). Selecting a node rewrites the address bar to exactly that URL, so a
link copied from the browser previews correctly too, not only one taken from the card's **share**
button. Older `#Q51213808` links keep working.

**Road to the Anunnaki** is a game built on the same trail: you are dropped on a theory and have to
reach the Anunnaki article using nothing but real connections — no search, no filters, a limited move
budget, and hints that cost points. Ten fixed levels (everyone plays the same starts, so scores compare)
plus a random mode. `scraper/11_levels.py` computes each level's shortest distance; it rebuilds exactly
the graph the player can walk, and the page recomputes the same one in the browser — if the two ever
disagree, "shortest route" would be a lie. Results are kept in the browser, and a shared leaderboard
is ready to switch on (see below). While a level is running nothing outside the game can disturb it: a stray
click on the map, Esc or closing the card leave the walked route alone, and only real moves (or
steps back onto the route) change it — a misplaced click used to wipe the run.

A **Scores** window (the link in the left panel's footer, or the button in the game's menu) holds what
came of all that playing: levels done, points, perfect routes, games played and won, then a row per
level with the best score, the moves against the shortest route, hints and time, and a **Route** link
that draws that saved run back onto the map. Below it the shared leaderboard, by level or by total,
with your own row marked.

A finished level produces a challenge link, and for the same reason as the node pages it is a real file:
`g/lt/7-5.html?lang=lt&n=…&m=5` carries that level's own meta tags ("7 lygis: … → Anunakiai", "įveiktas
per 5 žingsnius"), so a link dropped into a chat says which level it is instead of repeating the site's
title. `scraper/12_game_pages.py` writes one page per level and one per possible result (between the
shortest route and the budget), in both languages; the challenger's name stays in the query, since a
static file cannot carry it. The address bar holds the same link while playing, and older
`?game=7&n=…&m=…` links keep working.

### Shared leaderboard (optional)

`worker/` is a Cloudflare Worker with a D1 database: `POST /run` takes a finished level and
`GET /top?lvl=3` returns the best result per player. The server verifies the submitted route itself —
it must start at that level's node, end at the Anunnaki, and every step must be a real edge (the
`edges` table) — and it computes the score, so only the clock and the "no hints" flag are worth
faking. Each player keeps one row per level, so the table cannot grow without limit.

To switch it on:

1. In Cloudflare, create an API token with **Workers Scripts: Edit** and **D1: Edit**, and copy your
   account ID.
2. Put them in the repository as `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`
   (Settings → Secrets and variables → Actions). Paste the token alone — no `Bearer`, no quotes.
3. Run the **Deploy game API** workflow. It finds the D1 database by name (creating it if missing),
   writes its id into `wrangler.toml`, creates the tables, loads levels and edges on the first run,
   deploys, and finally calls `/health`, which reports how many levels and edges are in place.
4. Put the printed `…workers.dev` address into `const GAME_API` in `site/index.html` and commit.
   While it is empty the game works exactly as before, with results kept in the browser only.

The board is live at `https://conspiracy-map-api.seimos-finansai-backend.workers.dev`
(`/health` answers with the number of levels, edges and saved runs).

Locally the whole thing runs without a Cloudflare account:
`cd worker && npx wrangler d1 execute conspiracy-map --local --file=schema.sql` (then `seed.sql`),
`npx wrangler dev --local`, and point `GAME_API` at `http://127.0.0.1:8788` while testing.

An **About** panel (the link at the bottom of the left panel, Esc to close) explains where the data
comes from, what the statuses and roles mean, and the limitations. Its numbers are read from the
loaded graph, so they never go stale. The preview image `site/og.png` is a real screenshot of the map,
regenerated with `node layout/og.mjs` (needs Playwright and a local server).

The interface is bilingual (English / Lithuanian). The language comes from `?lang=en` / `?lang=lt`,
then the visitor's saved choice, then the browser language. All interface strings live in one
`I18N` dictionary in `site/index.html`. Lithuanian content priority: lt.wikipedia article →
reviewed translation → Wikidata label → original English title.

## Data license

Text from Wikipedia is licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/);
Wikidata is CC0.
