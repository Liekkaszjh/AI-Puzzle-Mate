import test from 'node:test'
import assert from 'node:assert/strict'
import { createApi } from './api.js'

test('state CSRF is included in mutations with same-origin cookies', async () => {
  const calls = []
  const api = createApi(async (url, options) => {
    calls.push({ url, options })
    return { ok: true, json: async () => ({ csrf: 'session-token' }) }
  })
  await api('state')
  await api('question', { text: '与身高有关吗？' })
  assert.equal(calls[1].url, '/api/question')
  assert.equal(calls[1].options.headers['X-CSRF-Token'], 'session-token')
  assert.equal(calls[1].options.credentials, 'same-origin')
  assert.deepEqual(JSON.parse(calls[1].options.body), { text: '与身高有关吗？' })
})

test('API errors are exposed without replacing state', async () => {
  const api = createApi(async () => ({ ok: false, json: async () => ({ error: '当前不是你的回合' }) }))
  await assert.rejects(api('question', { text: '问题' }), /当前不是你的回合/)
})
