import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  reporter: "line",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3001",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chrome",
      use: { ...devices["Desktop Chrome"], channel: "chrome" },
    },
  ],
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        command: "pnpm dev --hostname 127.0.0.1 --port 3001",
        url: "http://127.0.0.1:3001",
        reuseExistingServer: false,
        timeout: 90_000,
        env: {
          NEXT_PUBLIC_API_URL: "http://127.0.0.1:2025",
          NEXT_PUBLIC_ASSISTANT_ID: "agent",
        },
      },
});
