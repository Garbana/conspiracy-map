// 5 etapas: iš anksto apskaičiuoja grafo išdėstymą ir klasterius.
//
// Du žingsniai (kad žemėlapis turėtų aiškius "žemynus"):
//   1) Karkasas: tik teorijos + susiję straipsniai. Du straipsniai jungiami, jei mini tuos pačius
//      subjektus (retesnis bendras subjektas = stipresnė trauka) arba tiesiogiai vienas kitą.
//      Išdėstoma ForceAtlas2, klasteriai – Louvain.
//   2) Subjektai (asmenys, vietos...) padedami į jas minančių straipsnių svorinį centrą.
//
// Įvestis:  data/export/graph.json, data/export/items.json
// Išvestis: site/data/graph.json (su x, y, cm), site/data/summaries.json
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import louvain from "graphology-communities-louvain";
import { random } from "graphology-layout";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const src = JSON.parse(fs.readFileSync(path.join(ROOT, "data/export/graph.json"), "utf8"));
// Išdėstymui naudojami tik branduolio kraštai (5-as elementas = 1); seni duomenys be jo – visi
const layoutEdges = src.edges.filter((e) => e.length < 5 || e[4] === 1);
const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/export/items.json"), "utf8"));
const ITER = +(process.env.ITER || 2000);
const TOP_K = +(process.env.TOP_K || 8);         // kiek stipriausių kaimynų pasilieka kiekvienas karkaso mazgas
const MAX_SHARED = 60;     // subjektai, minimi daugiau straipsnių, karkaso nekuria (per bendri)

const byId = new Map(src.nodes.map((n) => [n.id, n]));
const isHub = (id) => { const n = byId.get(id); return n && (n.k === "theory" || n.k === "related"); };

// ---------- 1) karkaso svoriai ----------
const hubsOf = new Map();               // subjektas -> [[straipsnis, svoris]]
const pair = new Map();                 // "a|b" -> svoris
const addPair = (a, b, w) => {
  if (a === b) return;
  const k = a < b ? a + "|" + b : b + "|" + a;
  pair.set(k, (pair.get(k) || 0) + w);
};
for (const [s, t, w] of layoutEdges) {
  if (!isHub(s)) continue;
  if (isHub(t)) { addPair(s, t, 3 * w); continue; }          // tiesioginė nuoroda
  const e = byId.get(t);
  if (!e || e.g) continue;
  if (!hubsOf.has(t)) hubsOf.set(t, []);
  hubsOf.get(t).push([s, w]);
}
for (const [, hs] of hubsOf) {
  if (hs.length < 2 || hs.length > MAX_SHARED) continue;
  const idf = Math.log(1 + MAX_SHARED / hs.length);
  for (let i = 0; i < hs.length; i++)
    for (let j = i + 1; j < hs.length; j++)
      addPair(hs[i][0], hs[j][0], idf * Math.sqrt(hs[i][1] * hs[j][1]));
}
// Retinimas: kiekvienam mazgui – TOP_K stipriausių ryšių
const nbrs = new Map();
for (const [k, w] of pair) {
  const [a, b] = k.split("|");
  (nbrs.get(a) || nbrs.set(a, []).get(a)).push([b, w]);
  (nbrs.get(b) || nbrs.set(b, []).get(b)).push([a, w]);
}
const g = new Graph({ type: "undirected" });
for (const n of src.nodes) if (isHub(n.id)) g.addNode(n.id);
for (const [a, list] of nbrs) {
  list.sort((x, y) => y[1] - x[1]);
  for (const [b, w] of list.slice(0, TOP_K)) if (!g.hasEdge(a, b)) g.addEdge(a, b, { weight: w });
}
// Normalizuojam svorius (vidurkis = 1), kad trauka ir stūmimas būtų subalansuoti
let sw = 0; g.forEachEdge((e, a) => (sw += a.weight));
const mean = sw / Math.max(1, g.size);
g.forEachEdge((e, a) => g.setEdgeAttribute(e, "weight", a.weight / mean));
const lonely = g.filterNodes((n) => g.degree(n) === 0);
lonely.forEach((n) => g.dropNode(n));
console.log(`Karkasas: ${g.order} straipsnių, ${g.size} ryšių (be ryšių: ${lonely.length})`);

const comm = louvain(g, { getEdgeWeight: "weight", resolution: 1.2 });
console.log(`Klasterių: ${new Set(Object.values(comm)).size}`);

// Klasterio vidaus ryšiai traukia stipriau, tarp klasterių – silpniau: aiškesni "žemynai"
const INTRA = +(process.env.INTRA || 5), INTER = +(process.env.INTER || 0.2);
g.forEachEdge((e, a, s, t) => g.setEdgeAttribute(e, "weight", a.weight * (comm[s] === comm[t] ? INTRA : INTER)));
random.assign(g, { scale: 1000, center: 0 });
const settings = { ...forceAtlas2.inferSettings(g), barnesHutOptimize: true, barnesHutTheta: 0.5,
  linLogMode: false, scalingRatio: 10, gravity: 1, strongGravityMode: false,
  edgeWeightInfluence: 1, outboundAttractionDistribution: false, adjustSizes: false, slowDown: 3,
  ...JSON.parse(process.env.FA2 || "{}") };
const t0 = Date.now();
for (let i = 0; i < ITER; i += 250) {
  forceAtlas2.assign(g, { iterations: 250, settings, getEdgeWeight: "weight" });
  let ext = 0; g.forEachNode((n, a) => (ext = Math.max(ext, Math.hypot(a.x, a.y))));
  console.log(`  FA2 ${i + 250}/${ITER} | spindulys ${ext.toFixed(0)} | ${((Date.now() - t0) / 1000).toFixed(0)}s`);
}

// Kokybės matas: klasterio vidinė sklaida / bendra sklaida (mažiau = geriau atskirti)
{
  const by = {}; let all = 0, n = 0, mx = 0, my = 0;
  g.forEachNode((id, a) => { mx += a.x; my += a.y; n++; });
  mx /= n; my /= n;
  g.forEachNode((id, a) => { all += (a.x - mx) ** 2 + (a.y - my) ** 2; (by[comm[id]] ||= []).push(a); });
  let within = 0;
  for (const c of Object.values(by)) {
    const cx = c.reduce((s, a) => s + a.x, 0) / c.length, cy = c.reduce((s, a) => s + a.y, 0) / c.length;
    within += c.reduce((s, a) => s + (a.x - cx) ** 2 + (a.y - cy) ** 2, 0);
  }
  console.log(`Atskyrimo rodiklis: ${Math.sqrt(within / all).toFixed(3)} (0 = idealiai atskirti, 1 = sumaišyti)`);
}
if (process.env.ONLY_METRIC) process.exit(0);

// ---------- normalizavimas ----------
const pos = {};
g.forEachNode((n, a) => (pos[n] = [a.x, a.y]));
const P = Object.values(pos);
const cx = P.reduce((s, p) => s + p[0], 0) / P.length, cy = P.reduce((s, p) => s + p[1], 0) / P.length;
P.forEach((p) => { p[0] -= cx; p[1] -= cy; });
const radii = P.map((p) => Math.hypot(p[0], p[1])).sort((a, b) => a - b);
const R = radii[Math.floor(radii.length * 0.98)] || 1;
P.forEach((p) => {                      // skalė -> ~1000; išsišokėlius pritraukiam
  const d = Math.hypot(p[0], p[1]);
  const f = (d > R ? R * (1 + Math.log(d / R) * 0.15) / d : 1) * (1000 / R);
  p[0] *= f; p[1] *= f;
});

// Straipsniai be karkaso ryšių padedami kaip subjektai – šalia teorijų, su kuriomis susiję (žr. žemiau)
let k = 0;

// ---------- 2) subjektai – į minančių straipsnių centrą ----------
const adj = new Map();
for (const [s, t, w] of layoutEdges) {
  (adj.get(s) || adj.set(s, []).get(s)).push([t, w]);
  (adj.get(t) || adj.set(t, []).get(t)).push([s, w]);
}
let seed = 7;
const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647 - 0.5);
const entComm = {};
for (const n of src.nodes) {
  if (pos[n.id]) continue;
  const ps = (adj.get(n.id) || []).filter(([o]) => pos[o] && isHub(o));
  if (!ps.length) { const a = k++ * 2.399963; pos[n.id] = [Math.cos(a) * 1200, Math.sin(a) * 1200]; continue; }
  let sx = 0, sy = 0, sw2 = 0;
  const cc = {};
  for (const [o, w] of ps) {
    sx += pos[o][0] * w; sy += pos[o][1] * w; sw2 += w;
    if (comm[o] !== undefined) cc[comm[o]] = (cc[comm[o]] || 0) + w;
  }
  // Mažas atsitiktinis poslinkis: kuo mažiau ryšių, tuo labiau "apsupa" savo straipsnį
  const spread = 18 + 30 / Math.sqrt(ps.length);
  pos[n.id] = [sx / sw2 + rnd() * spread * 2, sy / sw2 + rnd() * spread * 2];
  const best = Object.entries(cc).sort((a, b) => b[1] - a[1])[0];
  if (best) entComm[n.id] = +best[0];
}

// ---------- išvestis ----------
const deg = {};
for (const [s, t] of src.edges) { deg[s] = (deg[s] || 0) + 1; deg[t] = (deg[t] || 0) + 1; }
// Klasterius pernumeruojam pagal dydį (0 = didžiausias) – stabilesnės spalvos
const csize = {};
for (const c of Object.values(comm)) csize[c] = (csize[c] || 0) + 1;
const cmap = Object.fromEntries(Object.entries(csize).sort((a, b) => b[1] - a[1]).map(([c], i) => [c, i]));
const r1 = (v) => Math.round(v * 10) / 10;
const nodes = src.nodes.map((n) => {
  const o = { ...n, x: r1(pos[n.id][0]), y: r1(pos[n.id][1]), dg: deg[n.id] || 0 };
  const c = comm[n.id] ?? entComm[n.id];
  if (c !== undefined) o.cm = cmap[c];
  for (const kk of Object.keys(o)) if (o[kk] == null || (Array.isArray(o[kk]) && !o[kk].length)) delete o[kk];
  return o;
});

// Klasterių pavadinimai: dažniausios temos + didžiausia teorija
const clusters = {};
for (const n of nodes) {
  if (n.cm === undefined || n.k !== "theory") continue;
  const c = (clusters[n.cm] ||= { id: n.cm, n: 0, themes: {}, top: null, x: 0, y: 0 });
  c.n++; c.x += n.x; c.y += n.y;
  for (const t of n.th || []) c.themes[t] = (c.themes[t] || 0) + 1;
  if (!c.top || n.dg > c.top.dg) c.top = { t: n.t, dg: n.dg };
}
const clusterList = Object.values(clusters).filter((c) => c.n >= 5).map((c) => ({
  id: c.id, n: c.n, x: r1(c.x / c.n), y: r1(c.y / c.n), top: c.top.t,
  themes: Object.entries(c.themes).sort((a, b) => b[1] - a[1]).slice(0, 2).map(([t]) => t),
}));
console.log("Klasteriai (>=5 teorijų):");
for (const c of clusterList.sort((a, b) => b.n - a.n)) console.log(`  #${c.id} ${c.n} teor. | ${c.themes.join(", ")} | ${c.top}`);

const out = { nodes, edges: src.edges, themes: src.themes, clusters: clusterList, built: new Date().toISOString() };
fs.writeFileSync(path.join(ROOT, "site/data/graph.json"), JSON.stringify(out));
const ids = new Set(nodes.map((n) => n.id));
const sums = {};
for (const it of items) if (ids.has(it.id) && it.summary) sums[it.id] = it.summary;
fs.writeFileSync(path.join(ROOT, "site/data/summaries.json"), JSON.stringify(sums));
const mb = (f) => (fs.statSync(path.join(ROOT, f)).size / 1e6).toFixed(1);
console.log(`Išsaugota: graph.json ${mb("site/data/graph.json")} MB, summaries.json ${mb("site/data/summaries.json")} MB`);
