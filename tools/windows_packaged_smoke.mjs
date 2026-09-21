import { chromium } from "@playwright/test";
import http from "node:http";
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

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
const diagnosticsDir = args.get("--diagnostics-dir");
const importDir = args.get("--import-dir");
if (
  !["update-available", "updated", "invalid"].includes(phase) ||
  !debugPort ||
  !expectedVersion ||
  !expectedPackVersion ||
  !diagnosticsDir ||
  !importDir
) {
  throw new Error(
    "usage: windows_packaged_smoke.mjs --phase update-available|updated|invalid --debug-port PORT --expected-version VERSION --expected-pack-version PACK_VERSION --diagnostics-dir DIR --import-dir DIR",
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

function readDiagnosticsText(root) {
  const files = [];
  const visit = (directory) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) visit(path);
      else if (entry.isFile()) files.push(path);
    }
  };
  visit(root);
  return files.map((path) => ({ path, text: readFileSync(path, "utf8") }));
}

function assertDiagnosticsSafe(token) {
  const rawQuery = `/events?token=${encodeURIComponent(token)}`;
  const decodedQuery = `token=${token}`;
  const tokenAssignment = /\b(?:[A-Za-z0-9_-]*token|password|secret)\b\s*[:=]\s*["']?[A-Za-z0-9._~+/=-]{8,}/i;
  const tokenShape = /\b(?:ghp|github_pat|glpat|xox[baprs])_[A-Za-z0-9._-]+\b|\bRGAPI-[A-Za-z0-9_-]+\b|\bBearer\s+[A-Za-z0-9._~+/=-]+/i;
  for (const { text } of readDiagnosticsText(diagnosticsDir)) {
    if (text.includes(token) || text.includes(rawQuery) || text.includes(decodedQuery)) {
      throw new Error("packaged diagnostics contain a discovered token or raw SSE query");
    }
    if (tokenShape.test(text) || tokenAssignment.test(text)) {
      throw new Error("packaged diagnostics contain a token-shaped value");
    }
  }
}

function rawHttp({ port, method = "GET", path, host, token, body, accept }) {
  return new Promise((resolve, reject) => {
    const headers = { Host: host, Connection: "close" };
    if (token !== undefined) headers["X-BL-Token"] = token;
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      headers["Content-Length"] = Buffer.byteLength(body);
    }
    if (accept) headers.Accept = accept;
    const request = http.request(
      { host: "127.0.0.1", port, method, path, headers },
      (response) => {
        const chunks = [];
        response.on("data", (chunk) => chunks.push(chunk));
        response.on("end", () =>
          resolve({ status: response.statusCode ?? 0, body: Buffer.concat(chunks).toString("utf8") }),
        );
      },
    );
    request.setTimeout(10_000, () => request.destroy(new Error("raw sidecar request timed out")));
    request.on("error", reject);
    if (body !== undefined) request.write(body);
    request.end();
  });
}

async function assertSecurityMatrix(sidecarInfo, phase) {
  const { port, token } = sidecarInfo;
  if (
    typeof token !== "string" ||
    token.length < 32 ||
    token !== token.trim() ||
    token.toLowerCase() === "dev"
  ) {
    throw new Error("packaged sidecar returned an invalid security token");
  }
  const validHost = `127.0.0.1:${port}`;
  const invalidToken = `${token.slice(0, -1)}${token.endsWith("x") ? "y" : "x"}`;
  const cases = [
    ["valid-token-valid-host", token, validHost, 200],
    ["invalid-token-valid-host", invalidToken, validHost, 401],
    ["valid-token-invalid-host", token, `invalid.example:${port}`, 400],
    ["invalid-token-invalid-host", invalidToken, `invalid.example:${port}`, 400],
  ];
  const httpProof = [];
  for (const [name, requestToken, host, expected] of cases) {
    const result = await rawHttp({ port, path: "/health", host, token: requestToken });
    if (result.status !== expected) throw new Error(`packaged security matrix failed: ${name}`);
    httpProof.push({ case: name, status: result.status });
  }

  const importResult = await rawHttp({
    port,
    method: "POST",
    path: "/dev/import",
    host: validHost,
    token,
    body: JSON.stringify({ dir: importDir }),
  });
  if (importResult.status !== 403 || !importResult.body.includes("dev import disabled")) {
    throw new Error("packaged frozen import security check failed");
  }

  const sse = await new Promise((resolve, reject) => {
    const request = http.request(
      {
        host: "127.0.0.1",
        port,
        method: "GET",
        path: `/events?token=${encodeURIComponent(token)}`,
        headers: { Host: validHost, Accept: "text/event-stream", Connection: "close" },
      },
      (response) => {
        let data = "";
        let settled = false;
        const finish = (value) => {
          if (settled) return;
          settled = true;
          request.destroy();
          resolve(value);
        };
        response.on("data", (chunk) => {
          data += chunk.toString("utf8");
          if (data.includes('"type": "hello"') || data.includes('"type":"hello"')) {
            finish({ status: response.statusCode ?? 0, hello: true });
          }
        });
        response.on("end", () => finish({ status: response.statusCode ?? 0, hello: false }));
      },
    );
    request.setTimeout(10_000, () => request.destroy(new Error("SSE security request timed out")));
    request.on("error", (error) => {
      if (error.code !== "ECONNRESET") reject(error);
    });
    request.end();
  });
  if (sse.status !== 200 || !sse.hello) throw new Error("packaged SSE query-token check failed");

  assertDiagnosticsSafe(token);
  const proof = {
    phase,
    token: { length: token.length, not_dev: true, explicit: true },
    http: httpProof,
    sse: { status: sse.status, hello: sse.hello, query_token: true },
    dev_import: { status: importResult.status, fixture_reads: false },
  };
  writeFileSync(join(diagnosticsDir, `sidecar-security-${phase}.json`), `${JSON.stringify(proof)}\n`, "utf8");
  return proof;
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
      last = JSON.stringify({
        sidecarInfo: sidecarInfo
          ? { port: sidecarInfo.port, status: sidecarInfo.status, token_present: typeof sidecarInfo.token === "string" }
          : null,
        title,
      });
      if (
        sidecarInfo &&
        typeof sidecarInfo.port === "number" &&
        sidecarInfo.port >= 1 &&
        sidecarInfo.port <= 65535 &&
        sidecarInfo.port !== 23110 &&
        ["ok", "degraded"].includes(sidecarInfo.status) &&
        typeof sidecarInfo.token === "string" &&
        sidecarInfo.token.length >= 32 &&
        sidecarInfo.token === sidecarInfo.token.trim() &&
        sidecarInfo.token.toLowerCase() !== "dev" &&
        title === "sidecar connected"
      ) {
        return sidecarInfo;
      }
    } catch (error) {
      last = error instanceof Error ? error.message : "sidecar handshake failed";
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
      const card = declaration.model_card;
      const smoke = card.smoke_test;
      if (
        typeof card.model_version !== "string" ||
        !Array.isArray(card.feature_order) ||
        card.feature_order.length === 0 ||
        !smoke ||
        !Array.isArray(smoke.features) ||
        smoke.features.length !== card.feature_order.length ||
        typeof smoke.expected !== "number" ||
        !Number.isFinite(smoke.expected) ||
        typeof smoke.tolerance !== "number" ||
        !Number.isFinite(smoke.tolerance) ||
        smoke.tolerance < 0 ||
        !card.patch_scope ||
        typeof card.patch_scope.max !== "string"
      ) {
        throw new Error(`available model ${key} has an invalid model-card smoke contract`);
      }
      available.push({
        key,
        model_version: card.model_version,
        artifact_path: declaration.artifact.path,
        card_path: declaration.artifact.model_card_path,
        smoke: {
          feature_count: card.feature_order.length,
          expected: smoke.expected,
          tolerance: smoke.tolerance,
          patch: card.patch_scope.max,
        },
      });
    } else if (key === "surrender_advisor" && declaration.release_status !== "withheld") {
      throw new Error("Surrender Advisor must remain withheld in the packaged smoke");
    }
  }
  return available;
}

async function assertAvailableModelInference(page, sidecarInfo, availableModels) {
  if (availableModels.length === 0) {
    return { attempted: false, status: "no-available-model", model_count: 0, models: {} };
  }
  const results = await page.evaluate(
    async ({ port, token, models }) => {
      return Promise.all(
        models.map(async (model) => {
          const path = model.key === "personal_what_if" ? "/history/what-if" : "/live/ingame";
          const options = {
            headers: { "X-BL-Token": token },
          };
          if (model.key === "personal_what_if") {
            options.method = "POST";
            options.headers["Content-Type"] = "application/json";
            options.body = JSON.stringify({ adjustments: {} });
          }
          try {
            const response = await fetch(`http://127.0.0.1:${port}${path}`, options);
            let payload = null;
            try {
              payload = await response.json();
            } catch {
              payload = { status: "invalid-json" };
            }
            return { key: model.key, path, http_status: response.status, payload };
          } catch (error) {
            return {
              key: model.key,
              path,
              http_status: 0,
              payload: { status: "request-failed", reason: String(error) },
            };
          }
        }),
      );
    },
    { port: sidecarInfo.port, token: sidecarInfo.token, models: availableModels },
  );
  const proof = {};
  for (const entry of results) {
    if (entry.http_status !== 200) {
      throw new Error(`available model ${entry.key} route failed: ${JSON.stringify(entry)}`);
    }
    const inference = entry.key === "live_wp" ? entry.payload?.inference : entry.payload;
    if (!inference || typeof inference.status !== "string") {
      throw new Error(`available model ${entry.key} route returned no inference status`);
    }
    if (["error", "request-failed", "invalid-json"].includes(inference.status)) {
      throw new Error(`available model ${entry.key} inference failed: ${inference.reason ?? inference.status}`);
    }
    if (!["available", "suppressed", "stale", "incompatible", "unsupported-patch"].includes(inference.status)) {
      throw new Error(`available model ${entry.key} returned unknown inference status: ${inference.status}`);
    }
    if (inference.status === "available") {
      const model = availableModels.find((candidate) => candidate.key === entry.key);
      if (
        typeof inference.probability !== "number" ||
        !Number.isFinite(inference.probability) ||
        inference.probability < 0 ||
        inference.probability > 1 ||
        inference.model_version !== model.model_version ||
        inference.pack_version !== expectedPackVersion
      ) {
        throw new Error(`available model ${entry.key} returned invalid provenance/output`);
      }
    }
    proof[entry.key] = {
      path: entry.path,
      status: inference.status,
      model_version: inference.model_version ?? null,
      pack_version: inference.pack_version ?? null,
    };
  }
  if (Object.keys(proof).length !== availableModels.length) {
    throw new Error("packaged smoke skipped an available model route");
  }
  return {
    attempted: true,
    status: "checked-all-available-model-routes",
    model_count: availableModels.length,
    models: proof,
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

  await page.getByText(`Findings Pack ${expectedPackVersion}`, { exact: true }).waitFor({ state: "visible", timeout: 15_000 });
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
let diagnosticToken = null;
try {
  const page = await waitForAppPage(browser, 30_000);

  await page.getByTestId(UPDATER_TESTID).waitFor({ state: "visible", timeout: 15_000 });

  let result;
  if (phase === "update-available") {
    const sidecarInfo = await assertSidecarConnected(page);
    diagnosticToken = sidecarInfo.token;
    const securityProof = await assertSecurityMatrix(sidecarInfo, phase);
    const packProof = await assertPackContract(page, sidecarInfo);
    result = { ...securityProof, ...packProof, ...await runUpdateAvailablePhase(page) };
  } else if (phase === "updated") {
    const sidecarInfo = await assertSidecarConnected(page);
    diagnosticToken = sidecarInfo.token;
    const securityProof = await assertSecurityMatrix(sidecarInfo, phase);
    result = { ...securityProof, ...await runUpdatedPhase(page) };
  } else {
    const sidecarInfo = await assertSidecarConnected(page);
    diagnosticToken = sidecarInfo.token;
    const securityProof = await assertSecurityMatrix(sidecarInfo, phase);
    result = { ...securityProof, ...await runInvalidPhase(page) };
  }

  console.log(JSON.stringify({ phase, ...result }));
} finally {
  if (diagnosticToken) assertDiagnosticsSafe(diagnosticToken);
  await browser.close().catch(() => {});
}
