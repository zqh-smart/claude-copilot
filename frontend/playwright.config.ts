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
      // The trailing slash is required: chat-ui sets Vite `base: '/chat/'`
      // and the dev server 404s on `/chat` without it, so Playwright would
      // never consider the server ready.
      url: 'http://127.0.0.1:3001/chat/',
      reuseExistingServer: true,
      timeout: 90_000,
      env: {
        VITE_LANGGRAPH_API_URL: 'http://127.0.0.1:2025',
        VITE_LANGGRAPH_ASSISTANT_ID: 'agent',
      },
    },
  ],
})
