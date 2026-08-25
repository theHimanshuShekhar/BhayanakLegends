import { chromium } from "@playwright/test";

const args = new Map();
for (let index = 2; index < process.argv.length; index += 2) {
  args.set(process.argv[index], process.argv[index + 1]);
}
const phase = args.get("--phase");
const debugPort = args.get("--debug-port");
if (!["valid", "durable"].includes(phase) || !debugPort) {
  throw new Error("usage: windows_packaged_smoke.mjs --phase valid|durable --debug-port PORT");
}

const endpoint = `http://127.0.0.1:${debugPort}`;
const deadline = Date.now() + 45_000;
let browser;
while (Date.now() < deadline) {
  try {
    const response = await fetch(`${endpoint}/json/version`);
    if (response.ok) {
      browser = await chromium.connectOverCDP(endpoint);
      break;
    }
  } catch {
    // The packaged process can take a few seconds to create its WebView2 host.
  }
  await new Promise((resolve) => setTimeout(resolve, 250));
}
if (!browser) throw new Error("packaged WebView2 CDP endpoint did not become ready");

try {
  const context = browser.contexts()[0];
  const page = context.pages()[0];
  if (!page) throw new Error("packaged app did not expose a webview page");
  await page.waitForLoadState("domcontentloaded", { timeout: 15_000 });

  const sidecarInfo = await page.evaluate(async () => {
    const internals = window.__TAURI_INTERNALS__;
    if (!internals || typeof internals.invoke !== "function") return null;
    return internals.invoke("sidecar_info");
  });
  if (!sidecarInfo || typeof sidecarInfo.port !== "number") {
    throw new Error("webview could not observe sidecar handshake state");
  }
  if (sidecarInfo.port < 1 || sidecarInfo.port > 65535 || sidecarInfo.port === 23110) {
    throw new Error(`sidecar did not use an ephemeral port: ${sidecarInfo.port}`);
  }
  if (!["ok", "degraded"].includes(sidecarInfo.status)) {
    throw new Error(`unexpected sidecar health status: ${String(sidecarInfo.status)}`);
  }

  await page.getByTestId("sidecar-dot").waitFor({ state: "visible", timeout: 15_000 });
  await page.getByTestId("sidecar-dot").waitFor({ state: "attached" });
  if ((await page.getByTestId("sidecar-dot").getAttribute("title")) !== "sidecar connected") {
    throw new Error("webview did not report an authenticated sidecar connection");
  }
  const connectionStatus = page.getByRole("status");
  await connectionStatus.waitFor({ state: "visible", timeout: 15_000 });
  if (!(await connectionStatus.innerText()).includes("sidecar · connected")) {
    throw new Error("sidecar health was not observable in the webview");
  }

  await page.getByText("Findings Pack v1", { exact: true }).waitFor({ state: "visible", timeout: 15_000 });
  const pathname = await page.evaluate(() => window.location.pathname);
  if (pathname !== "/" && pathname !== "/live") {
    throw new Error(`packaged app rendered an unexpected initial route: ${pathname}`);
  }

  const activePack = await page.evaluate(async (port) => {
    const deadline = Date.now() + 20_000;
    while (Date.now() < deadline) {
      try {
        const response = await fetch(`http://127.0.0.1:${port}/health`, {
          headers: { "X-BL-Token": "dev" },
        });
        if (response.ok) {
          const health = await response.json();
          if (health.pack_version === "v2-smoke") return health;
        }
      } catch {
        // The sidecar may still be binding or completing its startup release check.
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    return null;
  }, sidecarInfo.port);
  if (!activePack) throw new Error("active Findings Pack release was not loaded");

  await page.getByTestId("updater-status").waitFor({ state: "visible", timeout: 15_000 });
  if (phase === "valid") {
    const text = await page.getByTestId("updater-status").innerText();
    if (!/up to date/i.test(text)) throw new Error(`valid fixture was not treated as no-update: ${text}`);
  }
  console.log(JSON.stringify({ phase, sidecar_port: sidecarInfo.port, sidecar_status: sidecarInfo.status }));
} finally {
  await browser.close();
}
