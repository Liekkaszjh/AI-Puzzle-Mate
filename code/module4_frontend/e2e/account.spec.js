import { test, expect } from '@playwright/test'

test('register, restore game after login, edit profile and change password', async ({ page }) => {
  const email = `player-${Date.now()}@example.com`
  await page.goto('/')
  await expect(page.getByRole('button', { name: '开始新的一局' })).toHaveCount(0)
  await page.getByRole('button', { name: '注册', exact: true }).click()
  await page.getByLabel('邮箱').fill(email)
  await page.getByLabel('注册昵称').fill('注册玩家')
  await page.getByLabel('密码', { exact: true }).fill('first-password')
  await page.getByRole('button', { name: '创建账号' }).click()
  await expect(page.getByText(`已登录：${email}`)).toBeVisible()
  await page.getByRole('button', { name: '开始新的一局' }).click()
  await expect(page.locator('.story h2')).toBeVisible()

  await page.getByLabel('玩家昵称').fill('新昵称')
  await page.getByRole('button', { name: '保存我的昵称' }).click()
  await page.getByLabel('当前密码').fill('first-password')
  await page.getByLabel('新密码').fill('second-password')
  await page.getByRole('button', { name: '修改密码' }).click()
  await expect(page.getByText('密码已更新，其他设备需要重新登录。')).toBeVisible()

  await page.getByRole('button', { name: '退出登录' }).click()
  await expect(page.getByText('请先注册或登录，登录后才能开始游戏。')).toBeVisible()
  await expect(page.getByRole('button', { name: '开始新的一局' })).toHaveCount(0)
  await page.getByLabel('邮箱').fill(email)
  await page.getByLabel('密码', { exact: true }).fill('second-password')
  await page.getByRole('button', { name: '邮箱登录' }).click()
  await expect(page.getByText(`已登录：${email}`)).toBeVisible()
  await expect(page.getByLabel('玩家昵称')).toHaveValue('新昵称')
  await expect(page.locator('.story h2')).toBeVisible()
})
