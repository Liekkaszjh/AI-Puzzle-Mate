import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../../../', import.meta.url))
const python = fileURLToPath(new URL('../../../.venv/Scripts/python.exe', import.meta.url))
const database = fileURLToPath(new URL('../../../data/e2e.sqlite3', import.meta.url))

test('administrator can find, edit and disable registered players', async ({ page }) => {
  const suffix = Date.now()
  const playerEmail = `managed-${suffix}@example.com`
  const adminEmail = `admin-${suffix}@example.com`
  await page.goto('/')
  await page.getByRole('button', { name: '注册', exact: true }).click()
  await page.getByLabel('邮箱').fill(playerEmail)
  await page.getByLabel('注册昵称').fill('待管理玩家')
  await page.getByLabel('密码', { exact: true }).fill('player-password')
  await page.getByRole('button', { name: '创建账号' }).click()
  await expect(page.getByRole('button', { name: '开始新的一局' })).toBeVisible()
  await page.getByRole('button', { name: '退出登录' }).click()

  execFileSync(python, ['-c', 'import sys; from module3_host.storage import Repository; Repository(sys.argv[1]).create_admin(sys.argv[2], "admin-password", "管理员")', database, adminEmail],
    { cwd: root, env: { ...process.env, PYTHONPATH: `${root}code` } })
  await page.getByLabel('邮箱').fill(adminEmail)
  await page.getByLabel('密码', { exact: true }).fill('admin-password')
  await page.getByRole('button', { name: '邮箱登录' }).click()
  await expect(page.getByRole('heading', { name: '注册用户管理' })).toBeVisible()
  await expect(page.getByRole('button', { name: '开始新的一局' })).toHaveCount(0)

  await page.getByLabel('搜索邮箱或昵称').fill(playerEmail)
  await page.getByRole('button', { name: '搜索' }).click()
  await expect(page.getByText(playerEmail, { exact: true })).toBeVisible()
  await page.getByLabel(`${playerEmail} 的昵称`).fill('已管理玩家')
  await page.getByRole('button', { name: '保存昵称' }).click()
  await expect(page.getByLabel(`${playerEmail} 的昵称`)).toHaveValue('已管理玩家')
  await page.getByRole('button', { name: '禁用账号' }).click()
  await expect(page.getByRole('button', { name: '启用账号' })).toBeVisible()
  await page.getByRole('button', { name: '启用账号' }).click()
  await expect(page.getByRole('button', { name: '禁用账号' })).toBeVisible()
})
