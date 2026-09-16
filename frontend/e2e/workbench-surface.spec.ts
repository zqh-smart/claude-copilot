import { expect, test } from '@playwright/test'

/**
 * Workbench surface inventory.
 *
 * Proves that every business route still renders after the monorepo
 * restructure, and records what each page does when FastAPI is unreachable.
 * Screenshots land in `.p0-artifacts/workbench/` for review.
 */
const ROUTES = [
  ['/', '工作台'],
  ['/knowledge', '知识库'],
  ['/research', '研究问答'],
  ['/compare', '对比分析'],
  ['/reports', '报告中心'],
  ['/metrics', '指标中心'],
  ['/eval', '评测中心'],
  ['/jobs', '任务中心'],
  ['/upload', '文档上传'],
  ['/chat-memory', '对话记忆'],
] as const

for (const [path, label] of ROUTES) {
  test(`workbench route ${path} (${label}) renders`, async ({ page }) => {
    const runtimeErrors: string[] = []
    page.on('pageerror', (error) => runtimeErrors.push(error.message))

    await page.goto(`http://127.0.0.1:3000${path}`)
    // Wait deterministically on the page heading instead of a fixed sleep:
    // lazy route chunks resolve at different speeds, and a fixed timeout
    // produces false "blank page" results.
    await expect(page.locator('h1').first()).toBeVisible({ timeout: 15_000 })
    await page.waitForTimeout(1200)

    const slug = path === '/' ? 'dashboard' : path.replace(/^\//, '')
    await page.screenshot({
      path: `../.p0-artifacts/workbench/${slug}.png`,
      fullPage: true,
    })

    const heading = page.locator('h1, h2, .el-card__header, .page-title').first()
    const text = (await page.locator('body').innerText()).trim()

    console.log(`[${path}] heading=${JSON.stringify(await heading.innerText().catch(() => null))}`)
    console.log(`[${path}] url=${page.url()}`)
    console.log(`[${path}] bodyPreview=${JSON.stringify(text.slice(0, 240))}`)
    console.log(`[${path}] runtimeErrors=${JSON.stringify(runtimeErrors)}`)

    expect(text.length).toBeGreaterThan(0)
    expect(runtimeErrors).toEqual([])
  })
}
