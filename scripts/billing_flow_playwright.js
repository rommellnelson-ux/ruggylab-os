/**
 * E2E navigateur — parcours facturation bout-en-bout (Playwright).
 *
 * Login -> prescription d'examens -> "Générer la facture" -> Facturation ->
 * reçu PDF -> encaissement. Vérifie le flux UI réel (au-delà du smoke API).
 *
 * Prérequis : instance lancée (UI_CHECK_BASE_URL, défaut http://127.0.0.1:8000),
 *   `npm install -D playwright && npx playwright install chromium`.
 * Identifiants : process.env.FIRST_SUPERUSER_PASSWORD, sinon .env local.
 * Sort 0 si tout passe, non-zéro sinon. Capture dans artifacts/e2e/.
 */
const fs = require("fs");
const path = require("path");

let chromium;
try {
  ({ chromium } = require("playwright"));
} catch {
  console.error("Playwright requis : npm install -D playwright && npx playwright install chromium");
  process.exit(1);
}

const root = path.resolve(__dirname, "..");
function loadEnv() {
  const envPath = path.join(root, ".env");
  const fromFile = {};
  if (fs.existsSync(envPath)) {
    for (const line of fs.readFileSync(envPath, "utf8").split(/\r?\n/)) {
      if (!line || line.trim().startsWith("#") || !line.includes("=")) continue;
      const i = line.indexOf("=");
      fromFile[line.slice(0, i)] = line.slice(i + 1);
    }
  }
  return {
    user: process.env.FIRST_SUPERUSER || fromFile.FIRST_SUPERUSER || "admin",
    password: process.env.FIRST_SUPERUSER_PASSWORD || fromFile.FIRST_SUPERUSER_PASSWORD || "",
  };
}

const baseUrl = process.env.UI_CHECK_BASE_URL || "http://127.0.0.1:8000";
const creds = loadEnv();
const outDir = path.join(root, "artifacts", "e2e");
fs.mkdirSync(outDir, { recursive: true });

function assert(cond, msg) {
  if (!cond) throw new Error("ECHEC: " + msg);
  console.log("  [OK] " + msg);
}

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  try {
    // 1. Connexion
    await page.goto(`${baseUrl}/app`, { waitUntil: "domcontentloaded" });
    await page.fill("#username", creds.user);
    await page.fill("#password", creds.password);
    await page.click('button:has-text("Connexion")');
    await page.waitForSelector("#appView:not(.hidden)", { timeout: 15000 });
    assert(true, "connexion + cockpit affiché");

    // 2. Données de prérequis via l'API applicative (depuis le contexte page)
    const seed = await page.evaluate(async () => {
      await api("/api/v1/tariffs/seed-defaults", { method: "POST", headers: headers() });
      const ipp = "E2E-" + Math.random().toString(36).slice(2, 8).toUpperCase();
      const p = await api("/api/v1/patients", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({
          ipp_unique_id: ipp, first_name: "E2e", last_name: "Test",
          birth_date: "1990-01-01", sex: "F",
        }),
      });
      const o = await api("/api/v1/exam-orders", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({
          patient_id: p.id, prescriber: "Dr E2E",
          exams: [{ exam_code: "NFS" }, { exam_code: "GE" }],
        }),
      });
      return { orderId: o.id };
    });
    assert(Number.isInteger(seed.orderId), "prescription créée (#" + seed.orderId + ")");

    // 3. Vue prescriptions + génération de la facture depuis le fil
    await page.evaluate((oid) => { showView("prescription"); openOrderThread(oid); }, seed.orderId);
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(outDir, "01-prescription.png") });
    const inv = await page.evaluate(async (oid) => {
      return api(`/api/v1/exam-orders/${oid}/invoice`, { method: "POST", headers: headers(), body: "{}" });
    }, seed.orderId);
    assert(inv.invoice_number && Number(inv.patient_due_xof) === 7500, "facture générée (7 500 FCFA)");

    // 4. Vue facturation : la facture apparaît
    await page.evaluate(() => { showView("invoices"); loadInvoices(); loadFinanceSummary(); });
    await page.waitForTimeout(800);
    await page.waitForSelector(`#invoicesTable tbody tr`, { timeout: 10000 });
    const shown = await page.evaluate(() => document.getElementById("invoicesTable").innerText);
    assert(shown.includes(inv.invoice_number), "facture visible dans le journal");
    await page.screenshot({ path: path.join(outDir, "02-facturation.png") });

    // 5. Reçu PDF servi avec authentification
    const pdf = await page.evaluate(async (id) => {
      const r = await fetch(`/api/v1/invoices/${id}/receipt.pdf`, { headers: headers(false) });
      const b = new Uint8Array(await r.arrayBuffer());
      return { status: r.status, type: r.headers.get("content-type"), magic: String.fromCharCode(...b.slice(0, 5)) };
    }, inv.id);
    assert(pdf.status === 200 && pdf.type === "application/pdf" && pdf.magic === "%PDF-", "reçu PDF servi");

    // 6. Encaissement intégral -> facture payée
    const paid = await page.evaluate(async (id) => {
      return api(`/api/v1/invoices/${id}/payments`, {
        method: "POST", headers: headers(), body: JSON.stringify({ amount_xof: "7500" }),
      });
    }, inv.id);
    assert(paid.status === "paid" && Number(paid.balance_xof) === 0, "encaissement -> payée, solde 0");

    console.log("\nE2E facturation : OK");
  } finally {
    await browser.close();
  }
}

main().catch((e) => {
  console.error("\n" + e.message);
  process.exit(1);
});
