import { expect, test } from '@playwright/test'

/**
 * P0 Acceptance #4 — the Workbench → Agent Chat handoff carries `cc_*` params.
 *
 * Full round trip, with FastAPI stubbed so the test does not need a live
 * backend:
 *   /knowledge (document selected)  →  click "Agent Chat"
 *   →  lands on :3001/chat/ with cc_source / cc_resource / cc_prompt
 *   →  chat-ui renders the handoff banner from those params
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

  await page.goto(`${WORKBENCH}/knowledge`)

  // The view auto-selects the first completed document, which is what publishes
  // the handoff context. The rail renders metadata.company rather than the
  // filename, so assert on the company label.
  await expect(page.getByText(COMPANY)).toBeVisible({ timeout: 15_000 })

  await page.getByRole('button', { name: /Agent Chat/ }).click()

  // Handoff must land on the chat-ui origin, not the workbench's dead /chat.
  await page.waitForURL(/127\.0\.0\.1:3001\/chat\//, { timeout: 20_000 })
  const handoff = new URL(page.url())

  console.log('#4 handoff url = ' + handoff.toString())
  console.log('#4 cc_source   = ' + handoff.searchParams.get('cc_source'))
  console.log('#4 cc_resource = ' + handoff.searchParams.get('cc_resource'))
  console.log('#4 cc_prompt   = ' + handoff.searchParams.get('cc_prompt'))

  expect(handoff.searchParams.get('cc_source')).toBe('knowledge')
  expect(handoff.searchParams.get('cc_resource')).toBe(DOC_ID)
  expect(handoff.searchParams.get('cc_prompt')).toBe(PROMPT)

  // Round trip: chat-ui must actually render the banner from those params.
  await expect(page.getByText('已从工作台衔接')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText('知识库', { exact: false })).toBeVisible()

  await page.screenshot({ path: '../.p0-artifacts/11-handoff-round-trip.png', fullPage: true })
})
