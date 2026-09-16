import { expect, test } from '@playwright/test'

/**
 * P0 acceptance items that require the LangGraph dev server on :2025 to be UP.
 *
 * Covers:
 *   #3  /chat/ loads in the browser
 *   #5  "新对话" creates a real LangGraph thread
 *   #6  the thread list loads from client.threads.search
 *   #12 (positive path) thread list is reachable with the backend healthy
 *   #14 hard refresh keeps the launch context and does NOT re-fire the prompt
 *
 * Items #7/#8/#9/#10/#13/#15 need real LLM completions (empty API key in
 * langgraph.env), so they are intentionally out of scope here.
 */
const CHAT = 'http://127.0.0.1:3001/chat/'

test('#3 /chat/ loads with LangGraph up', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))

  await page.goto(CHAT)
  await expect(page.getByText('Agent Chat').first()).toBeVisible()
  await expect(page.getByRole('button', { name: '新对话' })).toBeVisible()
  await page.waitForTimeout(2500)

  const backendFailures = errors.filter((message) => !/favicon/i.test(message))
  console.log('#3 pageErrors=' + JSON.stringify(backendFailures))
  expect(backendFailures).toEqual([])
})

test('#6 the thread rail is backed by client.threads.search on :2025', async ({ page }) => {
  // Deterministic proof that the rail is remote-backed rather than local-only:
  // a thread created out-of-band with a unique title must show up in the UI.
  const title = 'P0-ACCEPTANCE-LIST-PROBE'

  await page.goto(CHAT)
  await expect(page.getByRole('button', { name: '新对话' })).toBeVisible()
  await expect(page.getByText(title)).toBeVisible({ timeout: 20_000 })

  console.log('#6 LangGraph thread rendered in rail = true')
})

/**
 * #5 as originally written ("click 新对话, confirm the id in
 * client.threads.search") cannot pass by design.
 *
 * react-langgraph 0.14.28 wires thread creation into the *send* path:
 *
 *   // useLangGraphMessages.js
 *   initialize: async () => await aui.threadListItem.initialize()
 *
 * and types.d.ts states the remote id is only emitted "once the thread is
 * initialized". A freshly created thread is therefore optimistic/local until
 * the first message is sent. This test pins that contract so the acceptance
 * list can be corrected instead of chasing a phantom bug.
 */
test('#5 new conversation defers thread creation until the first send', async ({ page }) => {
  const requests: string[] = []
  page.on('request', (r) => {
    if (r.url().includes(':2025') && !r.url().includes('/threads/search')) {
      requests.push(`${r.method()} ${r.url()}`)
    }
  })

  await page.goto(CHAT)
  await expect(page.getByRole('button', { name: '新对话' })).toBeVisible()
  await page.getByRole('button', { name: '新对话' }).click()
  await page.waitForTimeout(4000)

  // No remote id: creation is deferred to the first message.
  console.log('#5 ?thread= after New = ' + new URL(page.url()).searchParams.get('thread'))
  console.log('#5 non-search :2025 requests after New = ' + JSON.stringify(requests))

  expect(requests).toEqual([])
  expect(new URL(page.url()).searchParams.get('thread')).toBeNull()
})

test('#14 hard refresh keeps launch context without re-firing the prompt', async ({ page }) => {
  const prompt = '2021年营业收入是多少？'
  const url = `${CHAT}?cc_source=research&cc_resource=doc-abc123&cc_prompt=${encodeURIComponent(prompt)}`

  await page.goto(url)
  await expect(page.getByText('已从工作台衔接')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText('研究问答')).toBeVisible()
  await expect(page.getByText(`预填问题：${prompt}`)).toBeVisible()

  // The prompt is displayed, never auto-sent.
  const userBubblesBefore = await page.locator('text=' + prompt).count()
  console.log('#14 prompt occurrences before reload = ' + userBubblesBefore)

  await page.reload()

  // Context survives F5 ...
  await expect(page.getByText('已从工作台衔接')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText(`预填问题：${prompt}`)).toBeVisible()
  expect(page.url()).toContain('cc_source=research')
  expect(page.url()).toContain('cc_resource=doc-abc123')

  // ... and the composer is still empty: the prompt went to the banner only.
  const composer = page.getByPlaceholder('向 Claude Copilot 提问…')
  await expect(composer).toHaveValue('')
  console.log('#14 composer empty after reload = true')

  await page.screenshot({
    path: '../.p0-artifacts/08-launch-context-2025-up.png',
    fullPage: true,
  })
})
