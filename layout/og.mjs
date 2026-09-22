/**
 * site/og.png – bendrinimo paveikslėlis (1200×630): tikras žemėlapio vaizdas su antrašte.
 * Skaičiai imami iš gyvų duomenų, todėl perskaičiavus žemėlapį verta paleisti iš naujo.
 *
 *   python -m http.server 8765 --directory site &
 *   NODE_PATH=$(npm root -g) node layout/og.mjs
 *
 * Reikia Playwright su Chromium (`npm i -g playwright && npx playwright install chromium`).
 */
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";

const SRC = process.env.OG_URL || "http://localhost:8765/?lang=en";
const OUT = fileURLToPath(new URL("../site/og.png", import.meta.url));
const ZOOM = Number(process.env.OG_ZOOM || 0.72);   // < 1 – arčiau, > 1 – toliau

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
await page.goto(SRC, { waitUntil: "load", timeout: 120000 });
await page.waitForFunction(() => !document.getElementById("loader"), null, { timeout: 120000 });
await page.waitForTimeout(2500);   // šriftai ir pirmasis piešimas

await page.evaluate((zoom) => {
  for (const id of ["side", "card", "zoom", "legend", "tooltip", "about"]) {
    const el = document.getElementById(id);
    if (el) el.style.display = "none";
  }
  // Mazgų pavadinimai tokiame mastelyje susilieja – paliekam tik klasterių etiketes
  renderer.setSetting("labelRenderedSizeThreshold", 1e9);
  renderer.getCamera().setState({ x: 0.5, y: 0.47, ratio: zoom, angle: 0 });
  renderer.refresh();

  const s = aboutStats();
  const bar = document.createElement("div");
  bar.style.cssText = "position:fixed;left:0;right:0;bottom:0;z-index:50;padding:40px 56px 44px;" +
    "background:linear-gradient(transparent,rgba(7,8,13,.5) 30%,rgba(7,8,13,.94) 72%);font-family:Inter,system-ui,sans-serif";
  bar.innerHTML =
    `<div style="font:700 58px/1 'Cormorant Garamond',serif;color:#e6e3da;letter-spacing:.01em">` +
    `Conspiracy <span style="color:#d4a84a">Map</span></div>` +
    `<div style="margin-top:14px;color:#8d8a82;font-size:20px;line-height:1.35">` +
    `${s.th} conspiracy theories · ${s.nodes} nodes · ${s.edges} links<br>` +
    `<span style="color:#5b5a56;font-size:18px">Built from Wikipedia and Wikidata — it shows what is claimed, not what is true.</span></div>`;
  document.body.appendChild(bar);
}, ZOOM);

await page.waitForTimeout(1500);
// Klasterių etiketės, patenkančios po antrašte, tik trukdo – jas išimam
await page.evaluate(() => {
  for (const el of [...document.getElementById("clabels").children]) {
    const r = el.getBoundingClientRect();
    if (r.bottom > innerHeight - 165 && r.left < innerWidth * 0.62) el.remove();
  }
});
await page.screenshot({ path: OUT });
await browser.close();
console.log("→", OUT);
