# Conspiracy Map

Open-source project that systematizes publicly available information about conspiracy theories
(starting with Wikipedia and Wikidata) into a tagged knowledge graph – theories, people,
places, organizations, projects – and visualizes it as an interactive map.

Each theory keeps a link to its source article and a status (debunked / unproven / confirmed).

## Structure

- `scraper/` – Python data collection scripts (Wikipedia MediaWiki API, Wikidata SPARQL)
- `data/export/` – processed JSON data
- `site/` – static interactive map (planned)

## Data license

Text from Wikipedia is licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/);
Wikidata is CC0.
