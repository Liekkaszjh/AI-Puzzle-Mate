import { test, expect } from '@playwright/test'

async function register(page) {
  await page.getByRole('button', { name: '注册', exact: true }).click()
  await page.getByLabel('邮箱').fill(`game-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`)
  await page.getByLabel('注册昵称').fill('架构联调玩家')
  await page.getByLabel('密码', { exact: true }).fill('test-password')
  await page.getByRole('button', { name: '创建账号' }).click()
  await expect(page.getByRole('button', { name: '开始新的一局' })).toBeEnabled()
}

test('cooperative game, public dialogue, scoring and refresh recovery', async ({ page }) => {
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  await register(page)
  await page.getByLabel('玩家昵称').fill('架构联调玩家')
  await page.getByRole('button', { name: '保存我的昵称' }).click()
  await expect(page.getByRole('button', { name: '开始新的一局' })).toBeEnabled()
  await page.getByRole('button', { name: '开始新的一局' }).click()
  await expect(page.locator('.story h2')).toBeVisible()
  await expect(page.getByRole('heading', { name: '故事真相' })).toHaveCount(0)
  await page.getByLabel('你的问题（是 / 否 / 无关）').fill('这和身高有关吗？')
  await page.getByRole('button', { name: '提问', exact: true }).click()
  await expect(page.locator('.teammate-seat')).toHaveCount(2)
  await expect(page.locator('.wood-table')).toBeVisible()
  await expect(page.locator('.turn')).toHaveCount(3)
  await expect(page.locator('.turn').nth(1)).toContainText('小夏')
  await expect(page.locator('.turn').nth(2)).toContainText('阿澄')
  await page.reload()
  await expect(page.locator('.turn')).toHaveCount(3)
  await expect(page.getByLabel('玩家昵称')).toHaveValue('架构联调玩家')
  await page.screenshot({ path: '../../data/verification/vue-desktop.png', fullPage: true })
  await page.getByText('我要提交完整还原', { exact: true }).click()
  await page.getByLabel('请写出完整故事与原因').fill('这完全是一个无关的故事。')
  await page.getByRole('button', { name: '提交答案并评分' }).click()
  await expect(page.locator('.score')).toBeVisible()
  await expect(page.getByRole('heading', { name: '故事真相' })).toBeVisible()
  await page.reload()
  await expect(page.locator('.score')).toBeVisible()
  expect(errors).toEqual([])
})

test('mobile solo game and reveal', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await register(page)
  await page.getByLabel('推理方式').selectOption('solo')
  await page.getByRole('button', { name: '开始新的一局' }).click()
  await expect(page.locator('.teammate-seat')).toHaveCount(0)
  await page.getByLabel('你的问题（是 / 否 / 无关）').fill('与录音有关吗？')
  await page.getByRole('button', { name: '提问', exact: true }).click()
  await expect(page.locator('.turn')).toHaveCount(1)
  await expect(page.getByRole('button', { name: '提问', exact: true })).toBeEnabled()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: '../../data/verification/vue-mobile.png', fullPage: true })
  await page.getByRole('button', { name: '结束本局并揭晓汤底' }).click()
  await expect(page.getByRole('heading', { name: '故事真相' })).toBeVisible()
})

test('three teammates on mobile resume the failed second turn without repeating the first', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await register(page)
  await page.getByLabel('AI 队友人数').selectOption('3')
  await page.getByRole('button', { name: '开始新的一局' }).click()
  await expect(page.locator('.teammate-seat')).toHaveCount(3)
  let requests = 0
  await page.route('**/api/teammate', async route => {
    requests++
    if (requests === 2) await route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ error: '模拟阿澄回合失败，请继续' }) })
    else await route.continue()
  })
  await page.getByLabel('你的问题（是 / 否 / 无关）').fill('和年龄有关吗？')
  await page.getByRole('button', { name: '提问', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('模拟阿澄回合失败')
  await expect(page.locator('.turn')).toHaveCount(2)
  await page.reload()
  await expect(page.locator('.teammate-seat.active')).toHaveAttribute('data-teammate-id', 'acheng')
  await page.getByRole('button', { name: '继续队友回合' }).click()
  await expect(page.locator('.turn')).toHaveCount(4)
  await expect(page.locator('.turn').nth(3)).toContainText('小墨')
  await expect(page.getByRole('button', { name: '提问', exact: true })).toBeEnabled()
  for (const width of [390, 320, 820, 1280]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await expect.poll(() => page.locator('.scene img').evaluateAll(images => images.every(img => img.complete && img.naturalWidth > 0))).toBe(true)
    const boxes = await page.locator('.scene .speech').evaluateAll(nodes => nodes.map(node => {
      const rect = node.getBoundingClientRect()
      return { x: rect.x, y: rect.y, right: rect.right, bottom: rect.bottom }
    }))
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i], b = boxes[j]
        expect(a.right <= b.x || b.right <= a.x || a.bottom <= b.y || b.bottom <= a.y, `speech bubbles overlap at ${width}px (${i}, ${j})`).toBe(true)
      }
    }
    await page.locator('.table-panel').screenshot({ path: `../../data/verification/roundtable-team-${width}.png` })
  }
})
