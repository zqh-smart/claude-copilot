import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  retries: 0,
  reporter: 'line',
  use: {
    // baseURL points at the chat-ui dev server, which mounts the app under
    // /chat/. Page.goto('/') in tests resolves to http://127.0.0.1:3001/chat/.
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:3001/chat/',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chrome',
      use: { ...devices['Desktop Chrome'], channel: 'chrome' },
    },
  ],
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        command: 'pnpm dev',
        // The dev server emits the index on /chat/; wait until it answers.
        // The trailing slash is required: Vite `base: '/chat/'` makes the dev
        // server 404 on `/chat`, so readiness polling must use `/chat/`.
        url: 'http://127.0.0.1:3001/chat/',
        reuseExistingServer: false,
        timeout: 90_000,
        env: {
          VITE_LANGGRAPH_API_URL: 'http://127.0.0.1:2025',
          VITE_LANGGRAPH_ASSISTANT_ID: 'agent',
        },
      },
})