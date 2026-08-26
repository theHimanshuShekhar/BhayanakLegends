import { chromium } from "@playwright/test";

// Packaged-smoke webview assertions for the signed-updater proof pipeline.
//
// Phases (driven by tools/windows_packaged_smoke.ps1):
// - update-available: the lower-version app sees the fixture's real signed
//   higher-version offer, clicks the existing "Install update" action, and
//   rides the download into either the ready-to-restart UI (clicking the
//   existing "Restart app" action) or the Windows installer self-exit, where
//   the updater plugin spawns NSIS and exits the process mid-install.
// - updated: the relaunched app reports an authenticated sidecar connection,
//   a durable Findings Pack, and "up to date" against the same fixture.
// - invalid: the app accepts the fixture's higher-version metadata whose
//   signature does not match the served bytes, clicks "Install update", and
//   must surface the signature-verification failure without any relaunch.

const args = new Map();
for (let index = 2; index < process.argv.length; index += 2) {
  args.set(process.argv[index], process.argv[index + 1]);
}
const phase = args.get("--phase");
const debugPort = args.get("--debug-port");
const expectedVersion = args.get("--expected-version");

if (!["update-available", "updated", "invalid"].includes(phase) || !debugPort) {
  throw new Error(
    "usage: windows_packaged_smoke.mjs --phase update-available|updated|invalid --debug-port PORT [--expected-version V]",
  );
}
if ((phase === "update-available" || phase === "invalid") && !expectedVersion) {
  throw new Error(`phase ${phase} requires --expected-version`);
}

const endpoint = `http://127.0.0.1:${debugPort}`;
const UPDATER_TESTID = "updater-status";

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

async function waitForCdp(deadlineMs) {
  const deadline = Date.now() + deadlineMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${endpoint}/json/version`);
      if (response.ok) return await chromium.connectOverCDP(endpoint);
    } catch {
      // The packaged process can take a few seconds to create its WebView2 host.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  return null;
}

async function debugPortAlive() {
  try {
    const response = await fetch(`${endpoint}/json/version`);
    return response.ok;
  } catch {
    return false;
  }
}

async function waitUpdaterText(page, pattern, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let last = "";
  while (Date.now() < deadline) {
    try {
      last = await page.getByTestId(UPDATER_TESTID).innerText();
      if (pattern.test(last)) return last;
    } catch {
      // The page/target can be torn down mid-poll if the app is exiting.
      return null;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`timed out waiting for updater status matching ${pattern}; last saw: ${JSON.stringify(last)}`);
}

async function assertSidecarConnected(page) {
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
  if (!sidecarInfo.token || typeof sidecarInfo.token !== "string") {
    throw new Error("webview did not observe an authenticated sidecar token");
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
  return sidecarInfo;
}

async function fetchAuthenticatedHealth(page, sidecarInfo) {
  return page.evaluate(
    async ({ port, token }) => {
      const deadline = Date.now() + 20_000;
      while (Date.now() < deadline) {
        try {
          const response = await fetch(`http://127.0.0.1:${port}/health`, {
            headers: { "X-BL-Token": token },
          });
          if (response.ok) return await response.json();
        } catch {
          // The sidecar may still be completing its startup release check.
        }
        await new Promise((resolve) => setTimeout(resolve, 250));
      }
      return null;
    },
    { port: sidecarInfo.port, token: sidecarInfo.token },
  );
}

async function runUpdateAvailablePhase(page) {
  await waitUpdaterText(page, new RegExp(`^Version ${escapeRegExp(expectedVersion)} is available\\.$`), 30_000);

  await page.getByRole("button", { name: "Install update" }).click();

  // On Windows the updater plugin spawns the NSIS installer and calls
  // std::process::exit(0) before downloadAndInstall's promise resolves, so
  // "ready to restart" is reachable only if a future plugin version restores
  // it. Tolerate both: click the existing Restart app action if it renders,
  // otherwise treat the debug port going dark as the expected self-exit.
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    let text = null;
    try {
      text = await page.getByTestId(UPDATER_TESTID).innerText();
    } catch {
      return { outcome: "self-exited" };
    }
    if (/ready to restart/i.test(text)) {
      await page.getByRole("button", { name: "Restart app" }).click();
      return { outcome: "restart-clicked" };
    }
    if (/^update unavailable\./i.test(text)) {
      throw new Error(`valid signed update was rejected: ${text}`);
    }
    if (!(await debugPortAlive())) {
      return { outcome: "self-exited" };
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("timed out waiting for the valid update to install or the app to exit");
}

async function runUpdatedPhase(page) {
  const sidecarInfo = await assertSidecarConnected(page);

  await page.getByText("Findings Pack v1", { exact: true }).waitFor({ state: "visible", timeout: 15_000 });
  const health = await fetchAuthenticatedHealth(page, sidecarInfo);
  if (!health || health.pack_version !== "v2-smoke") {
    throw new Error("active Findings Pack release did not survive the signed update and relaunch");
  }

  // Give the mount-time updater check time to land, then require the exact
  // steady-state copy: the fixture now serves same-version metadata for the
  // relaunched (higher) install, so it must read as current, not available.
  await new Promise((resolve) => setTimeout(resolve, 5_000));
  const text = await page.getByTestId(UPDATER_TESTID).innerText();
  if (text !== "Bhayanak Legends is up to date.") {
    throw new Error(`relaunched app did not settle on up-to-date status: ${text}`);
  }
  return { sidecar_port: sidecarInfo.port, sidecar_status: sidecarInfo.status, pack_version: health.pack_version };
}

async function runInvalidPhase(page) {
  const sidecarInfo = await assertSidecarConnected(page);

  await waitUpdaterText(page, new RegExp(`^Version ${escapeRegExp(expectedVersion)} is available\\.$`), 30_000);
  await page.getByRole("button", { name: "Install update" }).click();

  const failureText = await waitUpdaterText(page, /signature could not be verified/i, 120_000);
  if (!failureText) {
    throw new Error("app exited instead of rejecting the mismatched-signature update");
  }

  // The rejection must not have torn down the process or the sidecar.
  await assertSidecarConnected(page);
  return { sidecar_port: sidecarInfo.port, sidecar_status: sidecarInfo.status, rejected_message: failureText };
}

let browser = await waitForCdp(45_000);
if (!browser) throw new Error("packaged WebView2 CDP endpoint did not become ready");

try {
  const context = browser.contexts()[0];
  const page = context.pages()[0];
  if (!page) throw new Error("packaged app did not expose a webview page");
  await page.waitForLoadState("domcontentloaded", { timeout: 15_000 });

  const pathname = await page.evaluate(() => window.location.pathname);
  if (pathname !== "/" && pathname !== "/live") {
    throw new Error(`packaged app rendered an unexpected initial route: ${pathname}`);
  }

  await page.getByTestId(UPDATER_TESTID).waitFor({ state: "visible", timeout: 15_000 });

  let result;
  if (phase === "update-available") {
    await assertSidecarConnected(page);
    result = await runUpdateAvailablePhase(page);
  } else if (phase === "updated") {
    result = await runUpdatedPhase(page);
  } else {
    result = await runInvalidPhase(page);
  }

  console.log(JSON.stringify({ phase, ...result }));
} finally {
  await browser.close().catch(() => {});
}
