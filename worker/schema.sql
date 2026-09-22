-- Rezultatai. Vienas įrašas – vienas įveiktas lygis.
CREATE TABLE IF NOT EXISTS runs (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  lvl    INTEGER NOT NULL,
  nick   TEXT    NOT NULL,
  moves  INTEGER NOT NULL,
  hints  INTEGER NOT NULL DEFAULT 0,
  secs   INTEGER NOT NULL DEFAULT 0,
  score  INTEGER NOT NULL,
  path   TEXT    NOT NULL,
  ts     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS runs_board ON runs (lvl, score DESC, moves ASC, secs ASC);
CREATE INDEX IF NOT EXISTS runs_nick  ON runs (nick, lvl);

-- Žaidimo grafo briaunos: pagal jas serveris patikrina, ar atsiųstas kelias tikras.
-- Saugom viena kryptimi (a < b), tad įrašų perpus mažiau.
CREATE TABLE IF NOT EXISTS edges (
  a TEXT NOT NULL,
  b TEXT NOT NULL,
  PRIMARY KEY (a, b)
);

-- Lygiai: startas, trumpiausias kelias ir žingsnių biudžetas (iš site/data/levels.json).
CREATE TABLE IF NOT EXISTS levels (
  lvl    INTEGER PRIMARY KEY,
  start  TEXT NOT NULL,
  dist   INTEGER NOT NULL,
  budget INTEGER NOT NULL
);
