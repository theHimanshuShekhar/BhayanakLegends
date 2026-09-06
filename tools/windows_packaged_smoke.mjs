import { chromium } from "@playwright/test";

const args = new Map();
for (let index = 2; index < process.argv.length; index += 2) {
  args.set(process.argv[index], process.argv[index + 1]);
}
const phase = args.get("--phase");
const debugPort = args.get("--debug-port");
const expectedVersion = args.get("--expected-version");
const expectedPackVersion = args.get("--expected-pack-version");
if (!["valid", "durable"].includes(phase) || !debugPort || !expectedVersion || !expectedPackVersion) {
  throw new Error(
    "usage: windows_packaged_smoke.mjs --phase valid|durable --debug-port PORT --expected-version VERSION --expected-pack-version PACK_VERSION",
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
  const results = await page.evaluate(async ({ port, token, routes: paths }) => {
    const responses = await Promise.all(
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
    return responses;
  }, { port: sidecarInfo.port, token: sidecarInfo.token, routes });
  const failed = results.filter((result) => result.status !== 200);
  if (failed.length > 0) {
    throw new Error(`packaged core route check failed: ${JSON.stringify(failed)}`);
  }
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
  // Startup validates each available ONNX artifact and its card. An empty
  // available set is valid for a withheld-model seed; inference is conditional.
  return available;
}

async function assertAvailableModelInference(page, sidecarInfo, availableModels) {
  if (availableModels.length === 0) {
    return { attempted: false, status: "no-available-model", model_count: 0 };
  }
  const result = await page.evaluate(async ({ port, token }) => {
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
  }, { port: sidecarInfo.port, token: sidecarInfo.token });
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
  const activePack = await page.evaluate(async ({ port, token, expected }) => {
    const until = Date.now() + 20_000;
    while (Date.now() < until) {
      try {
        const response = await fetch(`http://127.0.0.1:${port}/pack`, {
          headers: { "X-BL-Token": token },
        });
        if (response.ok) {
          const pack = await response.json();
          if (pack.pack_version === expected) return pack;
        }
      } catch {
        // The sidecar may still be binding or completing its startup release check.
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    return null;
  }, { port: sidecarInfo.port, token: sidecarInfo.token, expected: expectedPackVersion });
  const availableModels = assertModelInventory(activePack);
  await assertCoreRoutes(page, sidecarInfo);
  const inference = await assertAvailableModelInference(page, sidecarInfo, availableModels);

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
        pack_version: expectedPackVersion,
        model_count: availableModels.length,
        inference,
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
        pack_version: expectedPackVersion,
        model_count: availableModels.length,
        inference,
        sidecar_port: sidecarInfo.port,
        sidecar_status: sidecarInfo.status,
      }),
    );
  }
} finally {
  await browser.close();
}
