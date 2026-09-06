import { chromium } from "@playwright/test";

const args = new Map();
for (let index = 2; index < process.argv.length; index += 2) {
  args.set(process.argv[index], process.argv[index + 1]);
}
const phase = args.get("--phase");
const debugPort = args.get("--debug-port");
const expectedVersion = args.get("--expected-version");
if (!["valid", "durable"].includes(phase) || !debugPort || !expectedVersion) {
  throw new Error(
    "usage: windows_packaged_smoke.mjs --phase valid|durable --debug-port PORT --expected-version VERSION",
  );
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

async function waitForStatus(statusNode, predicate, message) {
  const until = Date.now() + 30_000;
  let text = "";
  while (Date.now() < until) {
    text = await statusNode.innerText();
    if (predicate(text)) return text;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`${message}: ${text}`);
}

async function assertSidecarHealth(page, sidecarInfo) {
  const health = await page.evaluate(async ({ port, token }) => {
    const response = await fetch(`http://127.0.0.1:${port}/health`, {
      headers: { "X-BL-Token": token },
    });
    return response.ok ? response.json() : null;
  }, { port: sidecarInfo.port, token: sidecarInfo.token });
  if (!health || health.status !== "ok" && health.status !== "degraded") {
    throw new Error("authenticated sidecar health was not retained");
  }
}

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
  if (
    !sidecarInfo ||
    typeof sidecarInfo.port !== "number" ||
    typeof sidecarInfo.token !== "string" ||
    sidecarInfo.token.length < 32 ||
    sidecarInfo.token.toLowerCase() === "dev"
  ) {
    throw new Error("webview could not observe an authenticated sidecar handshake");
  }
  if (sidecarInfo.port < 1 || sidecarInfo.port > 65535 || sidecarInfo.port === 23110) {
    throw new Error(`sidecar did not use an ephemeral port: ${sidecarInfo.port}`);
  }
  if (!["ok", "degraded"].includes(sidecarInfo.status)) {
    throw new Error(`unexpected sidecar health status: ${String(sidecarInfo.status)}`);
  }

  await page.getByTestId("sidecar-dot").waitFor({ state: "visible", timeout: 15_000 });
  if ((await page.getByTestId("sidecar-dot").getAttribute("title")) !== "sidecar connected") {
    throw new Error("webview did not report an authenticated sidecar connection");
  }
  const connectionStatus = page.getByRole("status");
  await connectionStatus.waitFor({ state: "visible", timeout: 15_000 });
  if (!(await connectionStatus.innerText()).includes("sidecar · connected")) {
    throw new Error("sidecar health was not observable in the webview");
  }
  const activePack = await page.evaluate(async ({ port, token }) => {
    const until = Date.now() + 20_000;
    while (Date.now() < until) {
      try {
        const response = await fetch(`http://127.0.0.1:${port}/health`, {
          headers: { "X-BL-Token": token },
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
  }, { port: sidecarInfo.port, token: sidecarInfo.token });
  if (!activePack) throw new Error("active Findings Pack release was not loaded");

  const updaterStatus = page.getByTestId("updater-status");
  await updaterStatus.waitFor({ state: "visible", timeout: 15_000 });
  if (phase === "valid") {
    const install = page.getByRole("button", { name: "Install update", exact: true });
    await install.waitFor({ state: "visible", timeout: 30_000 });
    await install.click();
    const text = await waitForStatus(
      updaterStatus,
      (value) => value.includes(`Version ${expectedVersion} is ready to restart`),
      "valid signed update did not reach ready-to-restart",
    );
    if (!/ready to restart/i.test(text)) {
      throw new Error(`valid update did not expose ready-to-restart state: ${text}`);
    }
    await assertSidecarHealth(page, sidecarInfo);
    console.log(
      JSON.stringify({
        phase,
        updater: "signed-download-ready-to-restart",
        version: expectedVersion,
        sidecar_port: sidecarInfo.port,
        sidecar_status: sidecarInfo.status,
      }),
    );
  } else {
    const install = page.getByRole("button", { name: "Install update", exact: true });
    await install.waitFor({ state: "visible", timeout: 30_000 });
    await install.click();
    const text = await waitForStatus(
      updaterStatus,
      (value) => /signature|verification|could not be verified/i.test(value),
      "mismatched-signature update was not rejected",
    );
    if (/ready to restart|Restart app/i.test(text)) {
      throw new Error(`mismatched-signature update reached restart state: ${text}`);
    }
    await assertSidecarHealth(page, sidecarInfo);
    console.log(
      JSON.stringify({
        phase,
        updater: "mismatched-signature-rejected",
        version: expectedVersion,
        sidecar_port: sidecarInfo.port,
        sidecar_status: sidecarInfo.status,
      }),
    );
  }
} finally {
  await browser.close();
}
