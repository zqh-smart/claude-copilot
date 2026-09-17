import { expect, test } from '@playwright/test'

/**
 * P0 Acceptance #4 — the Workbench → Agent Chat handoff carries `cc_*` params.
 *
 * Full round trip, with FastAPI stubbed so the test does not need a live
 * backend:
 *   /knowledge (document selected)  →  click "研究对话"
 *   →  lands on the embedded /agent-chat route with cc_* params
 *   →  the React composer renders the handoff prompt as an unsent draft
 *
 * The Workbench has no /chat proxy, so a bare relative fallback would land on
 * http://127.0.0.1:3000/chat (dead). This test pins the baked __CHAT_UI_URL__
 * default from apps/workbench/vite.config.ts.
 */
const DOC_ID = 'p0-acceptance-doc-0001'
const COMPANY = '验收样例公司'
const PROMPT = '2021年营业收入是多少？'

/**
 * The Workbench is contractually on :3000, but that port is not always
 * available on a dev box (another service or an editor port-forward can hold
 * it, in which case Vite silently falls back to :3001 and this test would fail
 * for the wrong reason). Probe first and skip with an explicit message.
 */
const WORKBENCH = process.env.WORKBENCH_URL || 'http://127.0.0.1:3000'
let workbenchReady = false

async function stubWorkbenchApi(page: import('@playwright/test').Page) {
  await page.route('**/api/fastapi/**', async (route) => {
    const url = route.request().url()

    if (url.endsWith('/api/v1/documents')) {
      await route.fulfill({
        json: [
          {
            doc_id: DOC_ID,
            filename: 'P0-ACCEPTANCE-REPORT.pdf',
            status: 'completed',
            segment_count: 12,
            metadata: { company: COMPANY, year: 2021 },
          },
        ],
      })
      return
    }

    // knowledge-graph must return the object shape, not []: the view reads
    // `graph?.nodes.length`, which throws on an array.
    if (url.endsWith('/knowledge-graph')) {
      await route.fulfill({ json: { nodes: [], relationships: [] } })
      return
    }

    await route.fulfill({ json: [] })
  })
}

test.beforeAll(async ({ request }) => {
  try {
    const response = await request.get(WORKBENCH, { timeout: 4000 })
    workbenchReady = response.ok() && (await response.text()).includes('id="app"')
  } catch {
    workbenchReady = false
  }
})

test('workbench handoff reaches chat-ui with launch context', async ({ page }) => {
  test.skip(
    !workbenchReady,
    `No Workbench dev server at ${WORKBENCH}. Start it with ` +
      '`pnpm dev:workbench` (it must own :3000) or set WORKBENCH_URL.',
  )

  // FastAPI is not required: stub the endpoints /knowledge touches on mount.
  await stubWorkbenchApi(page)

  await page.goto(`${WORKBENCH}/knowledge`)

  // The view auto-selects the first completed document, which is what publishes
  // the handoff context. The rail renders metadata.company rather than the
  // filename, so assert on the company label.
  await expect(page.getByText(COMPANY).first()).toBeVisible({ timeout: 15_000 })

  await page.getByRole('button', { name: /研究对话/ }).click()

  // Handoff stays inside the Vue shell; the iframe owns the React /chat/ URL.
  await page.waitForURL(/\/agent-chat/, { timeout: 20_000 })
  const handoff = new URL(page.url())

  console.log('#4 handoff url = ' + handoff.toString())
  console.log('#4 cc_source   = ' + handoff.searchParams.get('cc_source'))
  console.log('#4 cc_resource = ' + handoff.searchParams.get('cc_resource'))
  console.log('#4 cc_prompt   = ' + handoff.searchParams.get('cc_prompt'))

  expect(handoff.searchParams.get('cc_source')).toBe('knowledge')
  expect(handoff.searchParams.get('cc_resource')).toBe(DOC_ID)
  expect(handoff.searchParams.get('cc_prompt')).toBe(PROMPT)

  // Round trip: the embedded React composer receives the prompt without
  // automatically firing it.
  const chat = page.frameLocator('iframe[title="Claude Copilot 研究对话"]')
  await expect(chat.getByPlaceholder('向金融研究 Agent 提问…')).toHaveValue(PROMPT, {
    timeout: 15_000,
  })
  await expect(chat.getByRole('heading', { name: '金融研究 Agent' })).toBeVisible()

  await page.screenshot({ path: '../.p0-artifacts/11-handoff-round-trip.png', fullPage: true })
})

test('KeepAlive clears launch context after leaving a publishing page', async ({ page }) => {
  test.skip(
    !workbenchReady,
    `No Workbench dev server at ${WORKBENCH}. Start it with ` +
      '`pnpm dev:workbench` (it must own :3000) or set WORKBENCH_URL.',
  )

  await stubWorkbenchApi(page)
  await page.goto(`${WORKBENCH}/knowledge`)
  await expect(page.getByText(COMPANY).first()).toBeVisible({ timeout: 15_000 })

  // This must be an in-app navigation so KnowledgeView is deactivated by
  // KeepAlive rather than unmounted by a full page load.
  await page.locator('.el-menu-item').filter({ hasText: '文档上传' }).click()
  await expect(page).toHaveURL(/\/upload$/)
  await page.getByRole('button', { name: /研究对话/ }).click()
  await page.waitForURL(/\/agent-chat/, { timeout: 20_000 })

  const handoff = new URL(page.url())
  expect(handoff.searchParams.get('cc_source')).toBeNull()
  expect(handoff.searchParams.get('cc_resource')).toBeNull()
  expect(handoff.searchParams.get('cc_prompt')).toBeNull()
})
