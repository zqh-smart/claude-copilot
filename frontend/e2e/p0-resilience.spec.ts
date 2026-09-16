import { expect, test } from '@playwright/test'

/**
 * P0 Acceptance #11 / #12 — LangGraph `:2025` is unavailable.
 *
 * These must be run with the LangGraph dev server deliberately DOWN, which is
 * not the default state of a dev box, so they are gated behind
 * `LANGGRAPH_DOWN=1`. Without the gate the suite would run them against a
 * healthy `:2025` and assert the opposite of what the items mean.
 *
 *   # PowerShell
 *   $env:LANGGRAPH_DOWN=1; pnpm test:e2e
 *
 *   # bash
 *   LANGGRAPH_DOWN=1 pnpm test:e2e
 *
 * Assertions are deliberately strict: the failure mode #11 forbids is an
 * *infinite spinner with no user-visible error*, so "the page rendered
 * something" is not evidence of passing. See RUNTIME.md §"Failure detail — #11"
 * for the observed cold-start defect these tests were written against.
 */
const CHAT = 'http://127.0.0.1:3001/chat/'

test.describe('LangGraph unavailable', () => {
  test.skip(
    !process.env.LANGGRAPH_DOWN,
    'Requires :2025 to be down. Re-run with LANGGRAPH_DOWN=1.',
  )

  test('#11 a failed run terminates with a user-visible error', async ({ page }) => {
    const pageErrors: string[] = []
    page.on('pageerror', (error) => pageErrors.push(error.message))

    await page.goto(CHAT)
    await expect(page.getByRole('button', { name: '新对话' })).toBeVisible()

    const composer = page.getByPlaceholder('向 Claude Copilot 提问…')
    await composer.fill('这是一条在 LangGraph 离线时发送的探测消息')
    await composer.press('Enter')

    // Give the runtime a generous window to settle into a terminal state.
    await page.waitForTimeout(35_000)

    const stopVisible = await page.getByRole('button', { name: '停止' }).isVisible()
    const toastCount = await page.locator('[data-sonner-toaster] [data-sonner-toast]').count()
    const inlineAlertCount = await page.locator('[role="alert"]').count()
    const liveText = (await page.locator('[aria-live]').allInnerTexts()).join(' ').trim()

    console.log('#11 stopButtonVisible=' + stopVisible)
    console.log('#11 toasts=' + toastCount + ' roleAlerts=' + inlineAlertCount)
    console.log('#11 ariaLive=' + JSON.stringify(liveText.slice(0, 300)))

    await page.screenshot({ path: '../.p0-artifacts/09-2025-down-after-send.png', fullPage: true })

    // #11 requires a FINITE error, not an endless spinner.
    expect(
      stopVisible,
      'run never reached a terminal state — the Stop button is still shown, i.e. an infinite spinner',
    ).toBe(false)

    const surfaced = toastCount + inlineAlertCount + pageErrors.length
    expect(
      surfaced,
      'run terminated but no error was surfaced to the user (no toast, no alert, no thrown error)',
    ).toBeGreaterThan(0)
  })

  test('#12 the shell and rail still render with the backend down', async ({ page }) => {
    const pageErrors: string[] = []
    page.on('pageerror', (error) => pageErrors.push(error.message))

    await page.goto(CHAT)
    await expect(page.getByText('Agent Chat').first()).toBeVisible()
    await expect(page.getByRole('button', { name: '新对话' })).toBeVisible()
    await expect(page.getByPlaceholder('向 Claude Copilot 提问…')).toBeVisible()
    await page.waitForTimeout(5000)

    // A backend outage must not crash the React tree.
    expect(pageErrors.filter((m) => !/favicon/i.test(m))).toEqual([])

    await page.screenshot({ path: '../.p0-artifacts/10-2025-down-shell.png', fullPage: true })
  })
})
