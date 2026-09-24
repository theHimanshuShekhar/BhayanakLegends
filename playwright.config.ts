import { defineConfig } from "@playwright/test";

export default defineConfig({
  // The replay stack is a singleton on port 23122; parallel workers would
  // cross-talk scenarios. Serial execution keeps suites deterministic.
  workers: 1,
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
  testDir: "./e2e",
  timeout: 30_000,
  use: {
    baseURL: "http://localhost:1420",
  },
  webServer: [
    {
      command: "python3 e2e/replay_stack.py",
      // /events never completes; probing it keeps an SSE connection open during teardown.
      // /health returns a finite 401 without credentials, which Playwright accepts as ready.
      url: "http://127.0.0.1:23122/health",
      reuseExistingServer: false,
      timeout: 60_000,
      gracefulShutdown: { signal: "SIGTERM", timeout: 10_000 },
    },
    {
      command: "node node_modules/vite/bin/vite.js --host 127.0.0.1",
      url: "http://127.0.0.1:1420",
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        VITE_BL_PORT: "23122",
        VITE_BL_TOKEN: "local-sidecar-development-token-32chars",
      },
    },
  ],
});
