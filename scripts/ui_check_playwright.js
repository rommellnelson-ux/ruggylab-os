const fs = require("fs");
const path = require("path");
let chromium;

try {
  ({ chromium } = require("playwright"));
} catch (error) {
  console.error(
    "Playwright is required for this visual check. Install it with `npm install -D playwright` and run `npx playwright install chromium`.",
  );
  process.exit(1);
}

const root = path.resolve(__dirname, "..");
const envPath = path.join(root, ".env");
const env = Object.fromEntries(
  fs
    .readFileSync(envPath, "utf8")
    .split(/\r?\n/)
    .filter((line) => line && !line.trim().startsWith("#") && line.includes("="))
    .map((line) => {
      const idx = line.indexOf("=");
      return [line.slice(0, idx), line.slice(idx + 1)];
    }),
);

const outDir = path.join(root, "artifacts", "ui-check");
fs.mkdirSync(outDir, { recursive: true });

async function login(page) {
  await page.goto("http://127.0.0.1:8010/app", { waitUntil: "domcontentloaded" });
  await page.fill("#username", env.FIRST_SUPERUSER || "admin");
  await page.fill("#password", env.FIRST_SUPERUSER_PASSWORD || "");
  await page.click('button:has-text("Connexion")');
  await page.waitForSelector("#appView:not(.hidden)", { timeout: 15000 });
  await page.waitForTimeout(500);
}

async function visibleOverflow(page) {
  return page.evaluate(() => {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    return Array.from(document.querySelectorAll("body *"))
      .map((el) => {
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        if (
          style.display === "none" ||
          style.visibility === "hidden" ||
          rect.right <= 1 ||
          rect.left >= vw - 1 ||
          rect.width < 4 ||
          rect.height < 4
        ) {
          return null;
        }
        const overRight = rect.right - vw;
        const overLeft = -rect.left;
        const overBottom = rect.bottom - vh;
        if (overRight > 2 || overLeft > 2 || overBottom > 2000) {
          return {
            tag: el.tagName,
            id: el.id || "",
            cls: String(el.className || "").slice(0, 80),
            text: (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 80),
            rect: {
              left: Math.round(rect.left),
              right: Math.round(rect.right),
              width: Math.round(rect.width),
              bottom: Math.round(rect.bottom),
            },
            overRight: Math.round(overRight),
            overLeft: Math.round(overLeft),
          };
        }
        return null;
      })
      .filter(Boolean)
      .slice(0, 40);
  });
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const results = {};

  const desktop = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await login(desktop);
  await desktop.screenshot({ path: path.join(outDir, "desktop-dashboard.png"), fullPage: true });
  results.desktopOverflow = await visibleOverflow(desktop);

  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await login(mobile);
  await mobile.screenshot({ path: path.join(outDir, "mobile-dashboard-closed.png"), fullPage: true });
  await mobile.click(".sidebar-toggle");
  await mobile.waitForTimeout(300);
  await mobile.screenshot({ path: path.join(outDir, "mobile-dashboard-menu.png"), fullPage: true });
  results.mobileOpenOverflow = await visibleOverflow(mobile);
  await mobile.click('button[data-view="stocks"]');
  await mobile.waitForTimeout(700);
  await mobile.screenshot({ path: path.join(outDir, "mobile-stocks.png"), fullPage: true });
  results.mobileStocksOverflow = await visibleOverflow(mobile);

  await browser.close();
  fs.writeFileSync(path.join(outDir, "ui-check.json"), JSON.stringify(results, null, 2));
  console.log(JSON.stringify(results, null, 2));
})();
