const fs = require("fs");
const path = require("path");
let chromium;

try {
  ({ chromium } = require("playwright"));
} catch {
  console.error(
    "Playwright is required. Use the bundled Codex Node runtime or install it with `npm install -D playwright`.",
  );
  process.exit(1);
}

const root = path.resolve(__dirname, "..");
const envPath = path.join(root, ".env");

function cleanEnvValue(value) {
  return String(value || "")
    .trim()
    .replace(/^['"]|['"]$/g, "");
}

function readEnvFile() {
  if (!fs.existsSync(envPath)) return {};
  return Object.fromEntries(
    fs
      .readFileSync(envPath, "utf8")
      .split(/\r?\n/)
      .filter((line) => line && !line.trim().startsWith("#") && line.includes("="))
      .map((line) => {
        const idx = line.indexOf("=");
        return [line.slice(0, idx), cleanEnvValue(line.slice(idx + 1))];
      }),
  );
}

const fileEnv = readEnvFile();
const username = process.env.UAT_USERNAME || fileEnv.FIRST_SUPERUSER || "admin";
const password = process.env.UAT_PASSWORD || fileEnv.FIRST_SUPERUSER_PASSWORD || "";
const baseUrl = process.env.UAT_BASE_URL || "http://127.0.0.1:8000";
const outDir = path.join(root, "artifacts", "results-uat");
fs.mkdirSync(outDir, { recursive: true });

function fail(message, details) {
  console.error(JSON.stringify({ ok: false, message, details }, null, 2));
  process.exit(1);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    acceptDownloads: true,
    permissions: ["clipboard-read", "clipboard-write"],
    viewport: { width: 1280, height: 900 },
  });
  const page = await context.newPage();
  const logs = [];
  page.on("pageerror", (error) => logs.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) logs.push(`${message.type()}: ${message.text()}`);
  });

  await page.goto(`${baseUrl}/app`, { waitUntil: "domcontentloaded" });
  if (await page.locator("#loginView:not(.hidden)").isVisible().catch(() => false)) {
    await page.fill("#username", username);
    await page.fill("#password", password);
    await page.click('button:has-text("Connexion")');
    try {
      await page.waitForFunction(() => Boolean(localStorage.getItem("ruggylab_token")), null, {
        timeout: 15000,
      });
    } catch {
      await browser.close();
      fail("Connexion UAT impossible. Vérifier FIRST_SUPERUSER/FIRST_SUPERUSER_PASSWORD dans .env ou UAT_USERNAME/UAT_PASSWORD.", {
        username,
        hasPassword: Boolean(password),
        logs: logs.slice(-6),
      });
    }
  }

  await page.evaluate(() => window.showView("results"));
  try {
    await page.waitForFunction(
      () => Array.from(document.querySelectorAll("#resultsTable tbody tr button")).some((button) =>
        button.textContent.includes("Détail"),
      ),
      null,
      { timeout: 15000 },
    );
  } catch {
    await page.evaluate(async () => {
      const token = localStorage.getItem("ruggylab_token");
      const request = async (url, options = {}) => {
        const response = await fetch(url, {
          ...options,
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
            ...(options.headers || {}),
          },
        });
        if (!response.ok) throw new Error(`${response.status} ${url}`);
        return response.json();
      };
      const suffix = String(Date.now()).slice(-8);
      const patient = await request("/api/v1/patients", {
        method: "POST",
        body: JSON.stringify({
          ipp_unique_id: `UAT-${suffix}`,
          first_name: "UAT",
          last_name: "Resultats",
          birth_date: "1990-01-01",
          sex: "F",
          rank: "Test",
        }),
      });
      const sample = await request("/api/v1/samples", {
        method: "POST",
        body: JSON.stringify({ barcode: `UAT-SAMPLE-${suffix}`, patient_id: patient.id, status: "Recu" }),
      });
      await request("/api/v1/results", {
        method: "POST",
        body: JSON.stringify({
          sample_id: sample.id,
          data_points: { CRP: 8.2, WBC: 6.4 },
          exam_code: "CRP",
          is_critical: false,
        }),
      });
      await window.loadResults();
    });
    await page.waitForFunction(
      () => Array.from(document.querySelectorAll("#resultsTable tbody tr button")).some((button) =>
        button.textContent.includes("Détail"),
      ),
      null,
      { timeout: 15000 },
    );
  }

  const firstContext = await page.evaluate(() => {
    const text = (selector) => document.querySelector(selector)?.textContent?.trim() || "";
    return {
      firstSampleText: document.querySelector("#resultsTable tbody tr td:nth-child(2)")?.textContent?.trim() || "",
      firstResultText: document.querySelector("#resultsTable tbody tr")?.textContent?.trim() || "",
      hint: text("#resultsListHint"),
      rowCount: document.querySelectorAll("#resultsTable tbody tr").length,
    };
  });

  if (!firstContext.firstResultText) fail("Aucune ligne résultat exploitable", firstContext);

  const searchTerm =
    firstContext.firstSampleText.match(/[A-Z0-9][A-Z0-9-]{3,}/)?.[0] ||
    firstContext.firstResultText.match(/#[0-9]+/)?.[0]?.replace("#", "") ||
    "";
  if (searchTerm) {
    await page.fill("#resultSearch", searchTerm);
    await page.waitForTimeout(300);
    const hasFilteredDetail = await page.evaluate(() =>
      Array.from(document.querySelectorAll("#resultsTable tbody tr button")).some((button) =>
        button.textContent.includes("Détail"),
      ),
    );
    if (!hasFilteredDetail) {
      await page.fill("#resultSearch", "");
      await page.waitForTimeout(300);
    }
  }
  await page.selectOption("#resultSort", "critical_first");
  await page.waitForTimeout(300);

  await page.evaluate(() => {
    const button = Array.from(document.querySelectorAll("#resultsTable tbody tr button")).find((el) =>
      el.textContent.includes("Détail"),
    );
    if (!button) throw new Error("Bouton Détail introuvable");
    button.click();
  });
  await page.waitForFunction(() => getComputedStyle(document.querySelector("#resultDetailPanel")).display !== "none", null, {
    timeout: 15000,
  });

  await page.click('button:has-text("Copier synthèse")');
  const csvDownload = page.waitForEvent("download", { timeout: 15000 });
  await page.click('button:has-text("Exporter CSV")');
  const download = await csvDownload;
  const downloadPath = path.join(outDir, await download.suggestedFilename());
  await download.saveAs(downloadPath);

  const result = await page.evaluate(() => {
    const text = (selector) => document.querySelector(selector)?.textContent?.trim() || "";
    return {
      rowCount: document.querySelectorAll("#resultsTable tbody tr").length,
      detailVisible: getComputedStyle(document.querySelector("#resultDetailPanel")).display !== "none",
      summary: text("#resultDetailClinicalSummary"),
      history: text("#resultDetailHistory"),
      audit: text("#resultDetailAudit"),
      hasBatchButton: Array.from(document.querySelectorAll("button")).some((button) =>
        button.textContent.includes("Prendre en charge affichés"),
      ),
      horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 1,
    };
  });

  await page.screenshot({ path: path.join(outDir, "results-uat.png"), fullPage: true });
  await browser.close();

  if (!result.detailVisible || !result.summary || !result.hasBatchButton || result.horizontalOverflow) {
    fail("UAT Résultats incomplète", { result, firstContext, logs: logs.slice(-8) });
  }

  console.log(
    JSON.stringify(
      {
        ok: true,
        baseUrl,
        username,
        searched: searchTerm || null,
        csv: downloadPath,
        screenshot: path.join(outDir, "results-uat.png"),
        result,
        logs: logs.slice(-8),
      },
      null,
      2,
    ),
  );
})();
