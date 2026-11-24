// deck-geometry.mjs — the rendered half of tests/test_deck_geometry.py.
// Reads the deck from a live gateway (URL in argv[2]) and prints one JSON row per
// viewport: how far each neighbour card edge sits past #cardwrap, and the sliver
// it shows past the main card. The python side judges the numbers, so a CSS
// tweak can never hide a bad row. Always exits 0.
import { execSync } from "node:child_process";
import { existsSync } from "node:fs";
import { createRequire } from "node:module";

const url = process.argv[2] || "http://127.0.0.1:18090/";
const widths = (process.env.GW_DECK_WIDTHS || "1440,1120,900,700,380").split(",").map(Number);

function requirePlaywright() {
  const req = createRequire(process.cwd() + "/");
  try { return req("playwright"); } catch (e) { /* not under this cwd */ }
  let g = "";
  try { g = execSync("npm root -g", { encoding: "utf8" }).trim(); } catch (e) { /* no npm */ }
  for (const root of [process.env.HOME + "/node_modules", g]) {
    if (root && existsSync(root + "/playwright")) {
      try { return req(root + "/playwright"); } catch (e) { /* stale link */ }
    }
  }
  return null;
}

const pw = requirePlaywright();
if (!pw) { console.log("NEED-PLAYWRIGHT"); process.exit(0); }

const fmt = (v) => Number(v).toFixed(1);
const browser = await pw.chromium.launch();
const rows = [];
for (const vw of widths) {
  const page = await browser.newPage({ viewport: { width: vw, height: 900 } });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#cards .page.on .card", { timeout: 25000 });
  await page.waitForTimeout(900);            // deck transition + deckHeight()
  const geo = await page.evaluate(() => {
    const wrap = document.getElementById("cardwrap").getBoundingClientRect();
    const mainEl = document.querySelector("#cards .page.on .card");
    const on = mainEl.getBoundingClientRect();
    const probe = (cls) => {
      const el = document.querySelector("#cards .page." + cls + " .card");
      if (!el) return null;
      const box = el.getBoundingClientRect();
      return { right: box.right, overWrap: box.right - wrap.right, pastOn: box.right - on.right };
    };
    return { wrapWidth: wrap.width, mainWidth: mainEl.offsetWidth, n1: probe("n1"), n2: probe("n2") };
  });
  const tidy = (o) => o && ({ right: fmt(o.right), overWrap: fmt(o.overWrap), pastOn: fmt(o.pastOn) });
  rows.push({ width: vw, wrapWidth: fmt(geo.wrapWidth), mainWidth: geo.mainWidth,
              n1: tidy(geo.n1), n2: tidy(geo.n2) });
  await page.close();
}
await browser.close();
console.log(JSON.stringify(rows));
