const fs = require("fs");
const path = require("path");
let chromium;

try {
  ({ chromium } = require("playwright"));
} catch {
  console.error("Playwright is required. Use the bundled Codex Node runtime or install it with `npm install -D playwright`.");
  process.exit(1);
}

const root = path.resolve(__dirname, "..");
const envPath = path.join(root, ".env");
const outDir = path.join(root, "artifacts", "critical-workflow-uat");
fs.mkdirSync(outDir, { recursive: true });

function cleanEnvValue(value) {
  return String(value || "").trim().replace(/^['"]|['"]$/g, "");
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

function fail(message, details) {
  console.error(JSON.stringify({ ok: false, message, details }, null, 2));
  process.exit(1);
}

const fileEnv = readEnvFile();
const username = process.env.UAT_USERNAME || fileEnv.FIRST_SUPERUSER || "admin";
const password = process.env.UAT_PASSWORD || fileEnv.FIRST_SUPERUSER_PASSWORD || "";
const baseUrl = process.env.UAT_BASE_URL || "http://127.0.0.1:8000";

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    acceptDownloads: true,
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
    await page.waitForFunction(() => Boolean(localStorage.getItem("ruggylab_token")), null, { timeout: 15000 });
  }

  const setup = await page.evaluate(async () => {
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
      if (!response.ok) throw new Error(`${response.status} ${url}: ${await response.text()}`);
      return response.json();
    };
    const suffix = String(Date.now()).slice(-8);
    const unit = `UAT-Qualite-${suffix}`;
    const patient = await request("/api/v1/patients", {
      method: "POST",
      body: JSON.stringify({
        ipp_unique_id: `UAT-CRIT-${suffix}`,
        first_name: "UAT",
        last_name: "Critique",
        birth_date: "1986-02-03",
        sex: "F",
        rank: "Test",
        unit,
      }),
    });
    const sample = await request("/api/v1/samples", {
      method: "POST",
      body: JSON.stringify({ barcode: `UAT-CRIT-SAMPLE-${suffix}`, patient_id: patient.id, status: "Recu" }),
    });
    const oldDate = new Date(Date.now() - 45 * 60 * 1000).toISOString();
    const handled = await request("/api/v1/results", {
      method: "POST",
      body: JSON.stringify({
        sample_id: sample.id,
        data_points: { K: 7.2 },
        exam_code: "IONO",
        is_critical: true,
      }),
    });
    const pending = await request("/api/v1/results", {
      method: "POST",
      body: JSON.stringify({
        sample_id: sample.id,
        analysis_date: oldDate,
        data_points: { CRP: 330 },
        exam_code: "CRP",
        is_critical: true,
      }),
    });
    await request(`/api/v1/results/${handled.id}/ack-critical`, { method: "PATCH" });
    return { handledId: handled.id, pendingId: pending.id, barcode: sample.barcode, patientIpp: patient.ipp_unique_id, unit };
  });

  await page.evaluate(() => window.showView("results"));
  await page.waitForFunction(() => document.querySelector("#resultSearch"), null, { timeout: 15000 });
  await page.fill("#resultSearch", setup.barcode);
  await page.waitForTimeout(400);
  await page.evaluate((handledId) => {
    const row = Array.from(document.querySelectorAll("#resultsTable tbody tr")).find((item) =>
      item.textContent.includes(`#${handledId}`),
    );
    const auditButton = Array.from(row?.querySelectorAll("button") || []).find((button) =>
      button.textContent.includes("Audit"),
    );
    if (!auditButton) throw new Error(`Bouton Audit introuvable pour résultat ${handledId}`);
    auditButton.click();
  }, setup.handledId);
  await page.waitForFunction(() => getComputedStyle(document.querySelector("#resultDetailPanel")).display !== "none", null, {
    timeout: 15000,
  });

  await page.evaluate(() => window.showView("reports"));
  await page.fill("#criticalComplianceTarget", "30");
  await page.fill("#criticalComplianceExam", "CRP");
  await page.fill("#criticalComplianceUnit", setup.unit);
  await page.evaluate(() => window.loadCriticalCompliance());
  await page.waitForFunction(() => document.querySelector("#criticalComplianceTable tbody tr"), null, { timeout: 15000 });

  const csvDownload = page.waitForEvent("download", { timeout: 15000 });
  await page.click('#reports .panel:has(#criticalComplianceTable) button:has-text("Exporter CSV")');
  const download = await csvDownload;
  const downloadPath = path.join(outDir, await download.suggestedFilename());
  await download.saveAs(downloadPath);

  const result = await page.evaluate((setupArg) => {
    const text = (selector) => document.querySelector(selector)?.textContent?.trim() || "";
    return {
      viewTitle: text("#viewTitle"),
      audit: text("#resultDetailAudit"),
      total: text("#critCompTotal"),
      late: text("#critCompLate"),
      hint: text("#criticalComplianceHint"),
      table: text("#criticalComplianceTable"),
      hasHandledRow: text("#criticalComplianceTable").includes(`#${setupArg.handledId}`),
      hasPendingRow: text("#criticalComplianceTable").includes(`#${setupArg.pendingId}`),
      hasAgent: text("#criticalComplianceTable").includes("RuggyLab Administrator"),
      hasLate: text("#criticalComplianceTable").includes("Hors délai"),
      hasFilteredOutHandledIonogram: !text("#criticalComplianceTable").includes(`#${setupArg.handledId}`),
      summary: text("#criticalComplianceSummary"),
      horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 1,
    };
  }, setup);

  await page.screenshot({ path: path.join(outDir, "critical-workflow-uat.png"), fullPage: true });
  await browser.close();

  if (!result.audit.includes("result.critical_ack") || !result.hasPendingRow || !result.hasFilteredOutHandledIonogram || !result.hasLate || !result.summary.includes("Synthèse qualité") || result.horizontalOverflow) {
    fail("UAT valeurs critiques incomplète", { setup, result, logs: logs.slice(-8) });
  }

  console.log(JSON.stringify({ ok: true, baseUrl, username, setup, csv: downloadPath, result, logs: logs.slice(-8) }, null, 2));
})();
