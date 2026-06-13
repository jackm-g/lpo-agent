// Capture the three LPO Agent screens (Describe → Review → Solution) at a mobile
// viewport, in Demo mode (the Bradley 2-variable example, no backend needed).
//
//   npm run build && node scripts/screenshots.mjs [baseURL]
//
// Outputs PNGs into docs/screenshots/.
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const BASE = process.argv[2] ?? "http://localhost:4173";
const here = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(here, "../../docs/screenshots"); // repo-root docs/screenshots

const browser = await chromium.launch({
  args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
});
const page = await browser.newPage({
  viewport: { width: 414, height: 896 }, // phone portrait
  deviceScaleFactor: 2, // retina-crisp PNGs
});

async function shot(name) {
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
  console.log("wrote", `${OUT}/${name}.png`);
}

await page.goto(BASE, { waitUntil: "networkidle" });

// --- Screen 1: Describe ---------------------------------------------------- //
await page.getByRole("button", { name: "Load example" }).click();
await page.waitForTimeout(250);
await shot("1-describe");

// --- Screen 2: Review elements -------------------------------------------- //
await page.getByRole("button", { name: /Formulate/ }).click();
await page.getByText("How your prompt became a model").waitFor();
await page.waitForTimeout(350);
await shot("2-review-elements");

// --- Screen 3: Solution (graph + answer) ---------------------------------- //
await page.getByRole("button", { name: /solve it/ }).click();
await page.getByText("The optimization, solved").waitFor();
await page.locator("svg.lp-graph polygon").waitFor();
await page.waitForTimeout(400);
await shot("3-solution");

await browser.close();
console.log("done");
