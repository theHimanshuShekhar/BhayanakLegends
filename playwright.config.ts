import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: {
    baseURL: "http://localhost:1420",
  },
  webServer: [
    {
      command: "python3 e2e/replay_stack.py",
      url: "http://127.0.0.1:23122/events?token=dev",
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "pnpm dev --host 127.0.0.1",
      url: "http://127.0.0.1:1420",
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        VITE_BL_PORT: "23122",
        VITE_BL_TOKEN: "dev",
      },
    },
  ],
});
