import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  retries: 0,
  reporter: 'line',
  use: {
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command: 'pnpm dev:workbench',
      url: 'http://127.0.0.1:3000',
      reuseExistingServer: true,
      timeout: 90_000,
    },
    {
      command: 'pnpm dev:chat',
      url: 'http://127.0.0.1:3001/chat',
      reuseExistingServer: true,
      timeout: 90_000,
      env: {
        NEXT_PUBLIC_API_URL: 'http://127.0.0.1:2025',
        NEXT_PUBLIC_ASSISTANT_ID: 'agent',
      },
    },
  ],
})
