import { defineConfig } from '@playwright/test'
import { fileURLToPath } from 'node:url'

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:5174', channel: 'chrome', headless: true },
  webServer: [
    {
      command: `"${fileURLToPath(new URL(process.platform === 'win32' ? '../../.venv/Scripts/python.exe' : '../../.venv/bin/python', import.meta.url))}" "${fileURLToPath(new URL('../run.py', import.meta.url))}" --demo --port 8001`,
      url: 'http://127.0.0.1:8001/api/health',
      env: { DATABASE_PATH: fileURLToPath(new URL('../../data/e2e.sqlite3', import.meta.url)), COOKIE_SECURE: 'false' },
      reuseExistingServer: false,
    },
    {
      command: 'npm run dev -- --port 5174',
      url: 'http://127.0.0.1:5174',
      env: { API_PROXY_TARGET: 'http://127.0.0.1:8001' },
      reuseExistingServer: false,
    },
  ],
})
