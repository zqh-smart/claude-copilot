import { expect, test } from '@playwright/test'

test('remote report remains canonical across edit, save, and refresh', async ({ page }) => {
  let lastPatch: Record<string, unknown> | null = null
  const draft = {
    draft_id: 'draft-1',
    title: '可信报告闭环',
    template_id: 'comprehensive_financial',
    language: 'zh',
    length: 'standard',
    prompt: '只使用已入库证据',
    status: 'draft',
    sources: [{ doc_id: 'doc-1', filename: '年报.pdf', company: '示例公司', year: 2025, doc_type: '年报' }],
    sections: [{
      section_id: 'sec-core',
      chapter_id: 'core_metrics',
      title: '核心财务指标',
      content: '后端真实正文 [C1]',
      editor_json: null,
      citation_ids: ['C1'],
      required_metrics: ['revenue'],
      analysis_requirements: ['不得虚构数字'],
    }],
    citations: [{
      citation_id: 'C1',
      doc_id: 'doc-1',
      filename: '年报.pdf',
      section_title: '管理层讨论',
      page: 42,
      excerpt: '营业收入保持增长。',
      path_label: '年报.pdf · 管理层讨论 · p.42',
      metric_key: 'revenue',
    }],
    warnings: [],
    created_at: '2026-09-20T00:00:00Z',
    updated_at: '2026-09-20T00:00:00Z',
  }

  await page.addInitScript(() => localStorage.clear())
  await page.route('**/api/fastapi/api/v1/report/drafts', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{
        draft_id: draft.draft_id,
        title: draft.title,
        template_id: draft.template_id,
        status: draft.status,
        source_count: 1,
        updated_at: draft.updated_at,
      }]),
    })
  })
  await page.route('**/api/fastapi/api/v1/report/drafts/draft-1', async (route) => {
    if (route.request().method() === 'PATCH') {
      lastPatch = route.request().postDataJSON() as Record<string, unknown>
      const body = lastPatch as { title?: string; status?: string; sections?: typeof draft.sections }
      if (body.title) draft.title = body.title
      if (body.status) draft.status = body.status
      if (body.sections) draft.sections = body.sections
      draft.updated_at = '2026-09-20T00:01:00Z'
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(draft) })
  })

  await page.goto('http://127.0.0.1:3000/reports/draft-1')
  // The first dev-server compilation updates generated component types and can
  // invalidate a lazy route request. Reload once after the module graph is warm.
  await page.waitForTimeout(2_000)
  await page.reload()
  const paragraph = page.locator('.report-prose p').filter({ hasText: '后端真实正文' })
  await expect(paragraph).toBeVisible({ timeout: 30_000 })
  await paragraph.click()
  await page.keyboard.press('End')
  await page.keyboard.type('，人工修改')

  await expect.poll(() => lastPatch).not.toBeNull()
  const sections = (lastPatch as { sections: Array<Record<string, unknown>> }).sections
  expect(sections[0]).toMatchObject({
    section_id: 'sec-core',
    chapter_id: 'core_metrics',
    citation_ids: ['C1'],
    required_metrics: ['revenue'],
    analysis_requirements: ['不得虚构数字'],
  })
  expect(sections[0].editor_json).toBeTruthy()

  await page.reload()
  await expect(page.locator('.report-prose')).toContainText('后端真实正文')
  await expect(page.locator('.report-prose')).toContainText('人工修改')
})
