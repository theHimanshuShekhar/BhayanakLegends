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
const expectedPackVersion = args.get("--expected-pack-version");
if (!["update-available", "updated", "invalid"].includes(phase) || !debugPort || !expectedVersion || !expectedPackVersion) {
  throw new Error(
    "usage: windows_packaged_smoke.mjs --phase update-available|updated|invalid --debug-port PORT --expected-version VERSION --expected-pack-version PACK_VERSION",
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
  const startedAt = Date.now();
  const deadline = startedAt + deadlineMs;
  let nextProgressAt = startedAt + 5_000;
  let lastProbe = "not probed yet";
  while (Date.now() < deadline) {
    let ready = false;
    try {
      const response = await fetch(`${endpoint}/json/version`);
      lastProbe = response.ok ? "ok" : `listener answered http status ${response.status}`;
      ready = response.ok;
      if (ready) return await chromium.connectOverCDP(endpoint);
    } catch (error) {
      const code = error && error.cause && error.cause.code;
      lastProbe = code ? `connection ${code}` : `fetch error: ${error && error.message}`;
    }
    if (Date.now() >= nextProgressAt) {
      console.error(`cdp-wait: ${Math.round((Date.now() - startedAt) / 1000)}s elapsed (last probe: ${lastProbe})`);
      nextProgressAt += 5_000;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`packaged WebView2 CDP endpoint did not become ready within ${deadlineMs / 1000}s (last probe: ${lastProbe})`);
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
  const deadline = Date.now() + 30_000;
  let last = "no handshake observed";
  while (Date.now() < deadline) {
    try {
      const sidecarInfo = await page.evaluate(async () => {
        const internals = window.__TAURI_INTERNALS__;
        if (!internals || typeof internals.invoke !== "function") return null;
        return internals.invoke("sidecar_info");
      });
      const title = await page.getByTestId("sidecar-dot").getAttribute("title").catch(() => null);
      last = JSON.stringify({ sidecarInfo, title });
      if (
        sidecarInfo &&
        typeof sidecarInfo.port === "number" &&
        sidecarInfo.port >= 1 &&
        sidecarInfo.port <= 65535 &&
        sidecarInfo.port !== 23110 &&
        ["ok", "degraded"].includes(sidecarInfo.status) &&
        typeof sidecarInfo.token === "string" &&
        sidecarInfo.token.length >= 32 &&
        title === "sidecar connected"
      ) {
        return sidecarInfo;
      }
    } catch (error) {
      last = error instanceof Error ? error.message : String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`webview did not reconcile an authenticated sidecar connection: ${last}`);
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

async function assertCoreRoutes(page, sidecarInfo) {
  const routes = [
    "/health",
    "/pack",
    "/history/summary",
    "/history/insights",
    "/benchmarks",
    "/postgame/latest",
    "/live/status",
    "/live/session",
    "/live/ingame",
  ];
  const results = await page.evaluate(async ({ port, token, paths }) => {
    return Promise.all(
      paths.map(async (path) => {
        try {
          const response = await fetch(`http://127.0.0.1:${port}${path}`, {
            headers: { "X-BL-Token": token },
          });
          return { path, status: response.status };
        } catch {
          return { path, status: 0 };
        }
      }),
    );
  }, { port: sidecarInfo.port, token: sidecarInfo.token, paths: routes });
  const failed = results.filter((result) => result.status !== 200);
  if (failed.length > 0) {
    throw new Error(`packaged core route check failed: ${JSON.stringify(failed)}`);
  }
}

async function fetchActivePack(page, sidecarInfo) {
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    try {
      const pack = await page.evaluate(
        async ({ port, token }) => {
          const response = await fetch(`http://127.0.0.1:${port}/pack`, {
            headers: { "X-BL-Token": token },
          });
          return response.ok ? response.json() : null;
        },
        { port: sidecarInfo.port, token: sidecarInfo.token },
      );
      if (pack?.pack_version === expectedPackVersion) return pack;
    } catch {
      // The sidecar may still be binding or completing its startup release check.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  return null;
}

function assertModelInventory(pack) {
  if (!pack || pack.schema_version !== 2 || pack.pack_version !== expectedPackVersion) {
    throw new Error("packaged sidecar did not return the exact canonical Findings Pack");
  }
  if (!pack.models || typeof pack.models !== "object" || Array.isArray(pack.models)) {
    throw new Error("packaged Findings Pack has no model inventory");
  }
  const available = [];
  for (const [key, declaration] of Object.entries(pack.models)) {
    if (!declaration || typeof declaration !== "object") {
      throw new Error(`model declaration ${key} is malformed`);
    }
    if (declaration.release_status === "available") {
      if (!declaration.artifact || !declaration.model_card) {
        throw new Error(`available model ${key} is missing its artifact/card`);
      }
      if (declaration.artifact.format !== "onnx") {
        throw new Error(`available model ${key} is not an ONNX artifact`);
      }
      available.push({
        key,
        model_version: declaration.model_card.model_version,
        artifact_path: declaration.artifact.path,
        card_path: declaration.artifact.model_card_path,
      });
    } else if (key === "surrender_advisor" && declaration.release_status !== "withheld") {
      throw new Error("Surrender Advisor must remain withheld in the packaged smoke");
    }
  }
  return available;
}

async function assertAvailableModelInference(page, sidecarInfo, availableModels) {
  if (availableModels.length === 0) {
    return { attempted: false, status: "no-available-model", model_count: 0 };
  }
  const result = await page.evaluate(
    async ({ port, token }) => {
      try {
        const response = await fetch(`http://127.0.0.1:${port}/history/what-if`, {
          method: "POST",
          headers: {
            "X-BL-Token": token,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ adjustments: {} }),
        });
        return response.ok ? response.json() : { status: `http-${response.status}` };
      } catch (error) {
        return { status: "request-failed", reason: String(error) };
      }
    },
    { port: sidecarInfo.port, token: sidecarInfo.token },
  );
  if (result.status === "available") {
    if (
      typeof result.probability !== "number" ||
      !Number.isFinite(result.probability) ||
      result.probability < 0 ||
      result.probability > 1 ||
      typeof result.model_version !== "string" ||
      result.pack_version !== expectedPackVersion
    ) {
      throw new Error("available Personal What-If inference returned an invalid result");
    }
  } else if (result.status === "error" || result.status === "request-failed") {
    throw new Error(`available model inference failed: ${result.reason ?? result.status}`);
  }
  return {
    attempted: true,
    status: result.status,
    model_count: availableModels.length,
  };
}

async function assertPackContract(page, sidecarInfo) {
  const activePack = await fetchActivePack(page, sidecarInfo);
  const availableModels = assertModelInventory(activePack);
  await assertCoreRoutes(page, sidecarInfo);
  const inference = await assertAvailableModelInference(page, sidecarInfo, availableModels);
  return {
    pack_version: expectedPackVersion,
    model_count: availableModels.length,
    inference,
  };
}

async function runUpdateAvailablePhase(page) {
  try {
    await waitUpdaterText(page, new RegExp(`^Version ${escapeRegExp(expectedVersion)} is available\\.(?:\\r?\\nInstall update)?$`), 30_000);
  } catch (error) {
    const rawCheck = await page.evaluate(async () => {
      try {
        const metadata = await window.__TAURI_INTERNALS__.invoke("plugin:updater|check", {});
        return { ok: true, version: metadata?.version ?? null, keys: Object.keys(metadata ?? {}) };
      } catch (rawError) {
        return { ok: false, error: rawError instanceof Error ? rawError.message : String(rawError) };
      }
    });
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`${message}; raw plugin check: ${JSON.stringify(rawCheck)}`);
  }
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

  await page.getByText("Findings Pack v2", { exact: true }).waitFor({ state: "visible", timeout: 15_000 });
  const health = await fetchAuthenticatedHealth(page, sidecarInfo);
  if (!health || health.pack_version !== expectedPackVersion) {
    throw new Error("active Findings Pack release did not survive the signed update and relaunch");
  }
  const packProof = await assertPackContract(page, sidecarInfo);

  // Give the mount-time updater check time to land, then require the exact
  // steady-state copy: the fixture now serves same-version metadata for the
  // relaunched (higher) install, so it must read as current, not available.
  await new Promise((resolve) => setTimeout(resolve, 5_000));
  const text = await page.getByTestId(UPDATER_TESTID).innerText();
  if (text !== "Bhayanak Legends is up to date.") {
    throw new Error(`relaunched app did not settle on up-to-date status: ${text}`);
  }
  return { sidecar_port: sidecarInfo.port, sidecar_status: sidecarInfo.status, ...packProof };
}

async function runInvalidPhase(page) {
  const sidecarInfo = await assertSidecarConnected(page);
  const packProof = await assertPackContract(page, sidecarInfo);

  await waitUpdaterText(page, new RegExp(`^Version ${escapeRegExp(expectedVersion)} is available\\.(?:\\r?\\nInstall update)?$`), 30_000);
  await page.getByRole("button", { name: "Install update" }).click();

  const failureText = await waitUpdaterText(page, /signature could not be verified/i, 120_000);
  if (!failureText) {
    throw new Error("app exited instead of rejecting the mismatched-signature update");
  }

  // The rejection must not have torn down the process or the sidecar.
  await assertSidecarConnected(page);
  return { sidecar_port: sidecarInfo.port, sidecar_status: sidecarInfo.status, ...packProof, rejected_message: failureText };
}

async function waitForAppPage(browser, deadlineMs) {
  const deadline = Date.now() + deadlineMs;
  let lastUrls = [];
  while (Date.now() < deadline) {
    const pages = browser.contexts().flatMap((context) => context.pages());
    lastUrls = pages.map((page) => page.url());
    for (const page of pages) {
      const url = page.url();
      if (url === "about:blank" || url.startsWith("devtools://")) continue;
      try {
        await page.waitForLoadState("domcontentloaded", { timeout: 1_000 });
        const pathname = await page.evaluate(() => window.location.pathname);
        if (pathname === "/" || pathname === "/live") return page;
      } catch {
        // WebView2 exposes its target before the Tauri document settles.
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`packaged app webview did not settle; observed targets: ${lastUrls.join(", ") || "(none)"}`);
}

// First launch can be slow (WebView2 host creation, SmartScan); the PS1
// harness watches the app process and kills this script early if the app
// itself dies, so a long wait here only costs time when progress is real.
const browser = await waitForCdp(120_000);
try {
  const page = await waitForAppPage(browser, 30_000);

  await page.getByTestId(UPDATER_TESTID).waitFor({ state: "visible", timeout: 15_000 });

  let result;
  if (phase === "update-available") {
    const sidecarInfo = await assertSidecarConnected(page);
    const packProof = await assertPackContract(page, sidecarInfo);
    result = { ...packProof, ...await runUpdateAvailablePhase(page) };
  } else if (phase === "updated") {
    result = await runUpdatedPhase(page);
  } else {
    result = await runInvalidPhase(page);
  }

  console.log(JSON.stringify({ phase, ...result }));
} finally {
  await browser.close().catch(() => {});
}
