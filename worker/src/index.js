/**
 * „Kelias pas anunakius“ – rezultatų lentelė.
 *
 * GET  /top?lvl=3&limit=20   geriausi to lygio rezultatai (po vieną kiekvienam vardui)
 * GET  /top?lvl=all          bendra suma pagal vardą
 * POST /run                  {lvl, nick, path:[...], hints, secs}
 *
 * Atsiųstą kelią serveris patikrina pats: ar prasideda to lygio startu, ar baigiasi
 * anunakiais ir ar kiekvienas žingsnis yra tikra grafo briauna (lentelė `edges`).
 * Todėl žingsnių skaičiaus suklastoti negalima – tik laiką ir „be užuominų“.
 */

const TARGET = "Q676379";
const MAX_PATH = 40;

// Lygiai – tie patys, ką siunčia site/data/levels.json (įrašomi seed.sql metu).
async function levelRow(env, lvl) {
  return env.DB.prepare("SELECT lvl, start, dist, budget FROM levels WHERE lvl = ?").bind(lvl).first();
}

const json = (data, status, origin) =>
  new Response(JSON.stringify(data), {
    status: status || 200,
    headers: { "content-type": "application/json; charset=utf-8", ...cors(origin) },
  });

// Iš kur leidžiam kreiptis. Kilmę nešiojamės per argumentus, o ne env – tas pats env
// objektas aptarnauja kelias užklausas vienu metu, tad įrašyta reikšmė sumaišytų atsakymus.
const allowed = (env, origin) =>
  [env.ALLOW_ORIGIN, env.ALLOW_ORIGIN_DEV].includes(origin) ? origin : env.ALLOW_ORIGIN;

const cors = (origin) => ({
  "access-control-allow-origin": origin,
  "access-control-allow-methods": "GET,POST,OPTIONS",
  "access-control-allow-headers": "content-type",
  "access-control-max-age": "86400",
});

const clean = (s, n) => String(s == null ? "" : s).replace(/[\u0000-\u001f<>]/g, "").trim().slice(0, n);

// Taškai skaičiuojami serveryje – klientas savo skaičiaus atsiųsti negali
const points = (moves, dist, hints) => Math.max(100, 1000 - 120 * (moves - dist) - 100 * hints);

// Paprasčiausias greitkelio ribotuvas: kiek rezultatų per minutę priimam iš vieno adreso.
// Skaičiai laikomi atmintyje, o ji gyva tik kol gyvas izoliatas, tad tai ne apsauga nuo
// užsispyrusio užpuoliko – tik nuo netyčinio ar naivaus užtvindymo. Rimtesnei apsaugai
// Cloudflare skydelyje užtenka įjungti nemokamą „Rate limiting“ taisyklę šiam adresui.
const RATE = { max: 20, windowMs: 60000, seen: new Map() };
function tooFast(ip) {
  const now = Date.now();
  if (RATE.seen.size > 5000) RATE.seen.clear();
  const e = RATE.seen.get(ip);
  if (!e || now - e.t > RATE.windowMs) { RATE.seen.set(ip, { n: 1, t: now }); return false; }
  e.n += 1;
  return e.n > RATE.max;
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const origin = allowed(env, req.headers.get("origin") || "");

    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(origin) });

    try {
      if (url.pathname === "/health" && req.method === "GET") return await health(env, origin);
      if (url.pathname === "/top" && req.method === "GET") return await top(env, url, origin);
      if (url.pathname === "/run" && req.method === "POST") return await run(req, env, origin);
      return json({ error: "not_found" }, 404, origin);
    } catch (e) {
      return json({ error: "server", detail: String(e && e.message || e) }, 500, origin);
    }
  },
};

// Ar duombazė paruošta: be briaunų ir lygių rezultatų priimti neįmanoma, o įdiegus
// norisi tai patikrinti vienu paspaudimu, o ne žaidžiant.
async function health(env, origin) {
  const [lv, ed, rn] = await env.DB.batch([
    env.DB.prepare("SELECT COUNT(*) AS n FROM levels"),
    env.DB.prepare("SELECT COUNT(*) AS n FROM edges"),
    env.DB.prepare("SELECT COUNT(*) AS n FROM runs"),
  ]);
  const n = (r) => (r.results && r.results[0] && r.results[0].n) || 0;
  const levels = n(lv), edges = n(ed);
  return json({ ok: levels > 0 && edges > 0, levels, edges, runs: n(rn) }, 200, origin);
}

async function top(env, url, origin) {
  const limit = Math.min(50, Math.max(1, parseInt(url.searchParams.get("limit") || "20", 10)));
  const lvl = url.searchParams.get("lvl") || "all";
  if (lvl === "all") {
    // Bendra suma: kiekvieno vardo geriausias rezultatas kiekviename lygyje
    const r = await env.DB.prepare(
      `SELECT nick, SUM(best) AS score, COUNT(*) AS levels FROM (
         SELECT nick, lvl, MAX(score) AS best FROM runs GROUP BY nick, lvl
       ) GROUP BY nick ORDER BY score DESC, levels DESC LIMIT ?`).bind(limit).all();
    return json({ lvl: "all", rows: r.results || [] }, 200, origin);
  }
  const n = parseInt(lvl, 10);
  if (!(n >= 1 && n <= 99)) return json({ error: "bad_level" }, 400, origin);
  const r = await env.DB.prepare(
    `SELECT nick, MAX(score) AS score, MIN(moves) AS moves, MIN(secs) AS secs
       FROM runs WHERE lvl = ? GROUP BY nick ORDER BY score DESC, moves ASC, secs ASC LIMIT ?`)
    .bind(n, limit).all();
  return json({ lvl: n, rows: r.results || [] }, 200, origin);
}

async function run(req, env, origin) {
  if (tooFast(req.headers.get("cf-connecting-ip") || "?")) return json({ error: "too_many" }, 429, origin);
  let body;
  try { body = await req.json(); } catch (e) { return json({ error: "bad_json" }, 400, origin); }

  const lvl = parseInt(body.lvl, 10);
  const nick = clean(body.nick, 20);
  const path = Array.isArray(body.path) ? body.path.map((x) => clean(x, 24)) : [];
  const hints = Math.max(0, Math.min(99, parseInt(body.hints, 10) || 0));
  const secs = Math.max(0, Math.min(86400, parseInt(body.secs, 10) || 0));

  if (!nick) return json({ error: "no_nick" }, 400, origin);
  if (!(lvl >= 1 && lvl <= 99)) return json({ error: "bad_level" }, 400, origin);
  if (path.length < 2 || path.length > MAX_PATH) return json({ error: "bad_path" }, 400, origin);

  const L = await levelRow(env, lvl);
  if (!L) return json({ error: "no_level" }, 404, origin);
  if (path[0] !== L.start) return json({ error: "wrong_start" }, 400, origin);
  if (path[path.length - 1] !== TARGET) return json({ error: "not_finished" }, 400, origin);

  const moves = path.length - 1;
  if (moves > L.budget) return json({ error: "over_budget" }, 400, origin);

  // Kiekvienas žingsnis turi būti tikra briauna
  const pairs = [];
  for (let i = 1; i < path.length; i++) {
    const a = path[i - 1], b = path[i];
    if (a === b) return json({ error: "repeat", step: i }, 400, origin);
    pairs.push([a, b]);
  }
  const found = await env.DB.batch(pairs.map(([a, b]) => {
    const [x, y] = a < b ? [a, b] : [b, a];      // briaunos saugomos viena kryptimi
    return env.DB.prepare("SELECT 1 AS ok FROM edges WHERE a = ? AND b = ?").bind(x, y);
  }));
  const badStep = found.findIndex((r) => !(r.results && r.results.length));
  if (badStep >= 0) return json({ error: "no_such_link", step: badStep + 1 }, 400, origin);

  const score = points(moves, L.dist, hints);
  const ts = Date.now();
  await env.DB.prepare(
    "INSERT INTO runs (lvl, nick, moves, hints, secs, score, path, ts) VALUES (?,?,?,?,?,?,?,?)")
    .bind(lvl, nick, moves, hints, secs, score, path.join(","), ts).run();

  // Lentelė neauga be galo: kiekvienam vardui kiekviename lygyje laikom tik geriausią bandymą
  await env.DB.prepare(
    `DELETE FROM runs WHERE lvl = ? AND nick = ? AND id NOT IN (
       SELECT id FROM runs WHERE lvl = ? AND nick = ?
        ORDER BY score DESC, moves ASC, secs ASC, id ASC LIMIT 1)`)
    .bind(lvl, nick, lvl, nick).run();

  // Vieta skaičiuojama pagal geriausią šio žaidėjo rezultatą, o ne pagal ką tik atsiųstą:
  // pakartojus lygį prasčiau, vieta lentelėje nuo to nenukrenta.
  const mine = await env.DB.prepare(
    "SELECT MAX(score) AS best FROM runs WHERE lvl = ? AND nick = ?").bind(lvl, nick).first();
  const best = (mine && mine.best) || score;
  const better = await env.DB.prepare(
    `SELECT COUNT(*) AS n FROM (SELECT nick AS nk, MAX(score) AS s FROM runs WHERE lvl = ? GROUP BY nick)
      WHERE s > ? AND nk <> ?`).bind(lvl, best, nick).first();

  return json({ ok: true, lvl, moves, dist: L.dist, hints, score, best, rank: (better.n || 0) + 1 }, 200, origin);
}
