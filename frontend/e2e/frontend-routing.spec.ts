import { expect, test } from '@playwright/test'

test('workbench exposes the financial product entry', async ({ page }) => {
  let documentRequests = 0
  const runtimeErrors: string[] = []
  page.on('pageerror', (error) => runtimeErrors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') runtimeErrors.push(message.text())
  })
  await page.route('**/api/fastapi/api/v1/documents', async (route) => {
    documentRequests += 1
    await route.fulfill({ json: [] })
  })
  await page.route('**/api/fastapi/api/v1/eval/serving', (route) => route.fulfill({ json: [] }))

  await page.goto('http://127.0.0.1:3000/')
  await expect(page.getByRole('heading', { name: '金融知识与研究工作台' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Agent Chat/ })).toBeVisible()

  await page.getByRole('menuitem', { name: '知识库' }).click()
  await expect(page.getByRole('heading', { name: '知识库与图谱' })).toBeVisible()
  await page.getByRole('menuitem', { name: '工作台' }).click()
  await expect(page.getByRole('heading', { name: '金融知识与研究工作台' })).toBeVisible()
  expect(documentRequests).toBe(1)
  expect(runtimeErrors).toEqual([])
})

test('chat UI is mounted below its production base path', async ({ page }) => {
  await page.goto('http://127.0.0.1:3001/chat')
  await expect(page).toHaveURL(/\/chat/)
  await expect(page.locator('body')).not.toBeEmpty()
})
