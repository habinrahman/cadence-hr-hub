// Checks WCAG contrast for the text/background pairs used by the design tokens.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const css = readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), "../app/globals.css"), "utf8");
const root = css.slice(css.indexOf(":root"), css.indexOf("@theme"));
const vars = {};
for (const m of root.matchAll(/--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})/g)) vars[m[1]] = m[2];
vars.white = "#ffffff";

function lum(hex) {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const l = c.map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * l[0] + 0.7152 * l[1] + 0.0722 * l[2];
}
function ratio(a, b) {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

const pairs = [
  ["ink", "canvas", 4.5], ["ink", "panel", 4.5], ["ink", "inset", 4.5],
  ["mut", "canvas", 4.5], ["mut", "panel", 4.5], ["mut", "inset", 4.5],
  ["human-ink", "panel", 4.5], ["human-ink", "human-bg", 4.5], ["human-ink", "canvas", 4.5],
  ["prop-ink", "prop-bg", 4.5], ["prop-ink", "panel", 4.5],
  ["ok-ink", "panel", 4.5], ["ok-ink", "ok-bg", 4.5],
  ["bad-ink", "panel", 4.5], ["bad-ink", "bad-bg", 4.5],
  ["ev-ink", "panel", 4.5],
  ["white", "human", 4.5], ["white", "ok-ink", 4.5], ["white", "bad-ink", 4.5],
  ["nav-ink", "nav", 4.5], ["white", "nav", 4.5], ["nav-mut", "nav", 4.5], ["nav-ink", "nav-active", 4.5], ["white", "nav-active", 4.5],
  ["t-rel-ink", "t-rel-bg", 4.5], ["t-req-ink", "t-req-bg", 4.5], ["t-match-ink", "t-match-bg", 4.5], ["t-share-ink", "t-share-bg", 4.5],
  ["human-ink", "inset", 4.5], ["mut", "canvas", 4.5],
  ["t-rel-ink", "panel", 4.5], ["t-req-ink", "panel", 4.5], ["t-match-ink", "panel", 4.5], ["t-share-ink", "panel", 4.5],
  // UI edges (3:1)
  ["rule-strong", "panel", 3], ["human", "canvas", 3], ["prop", "panel", 3],
];

let failed = 0;
for (const [fg, bg, min] of pairs) {
  if (!vars[fg] || !vars[bg]) {
    console.log(`MISSING ${fg}/${bg}`);
    failed++;
    continue;
  }
  const r = ratio(vars[fg], vars[bg]);
  const ok = r >= min;
  if (!ok) failed++;
  console.log(`${ok ? "PASS" : "FAIL"} ${fg} on ${bg}: ${r.toFixed(2)} (min ${min})`);
}
if (failed) {
  console.error(`${failed} pair(s) failed`);
  process.exit(1);
}
console.log("All contrast pairs pass");
