// All cookies and CSRF handling live here; components never contact DeepSeek.
export function createApi(fetcher = globalThis.fetch.bind(globalThis)) {
  let csrf = ''
  return async function request(path, data, method = 'POST') {
    const options = { method: data === undefined ? 'GET' : method, credentials: 'same-origin' }
    if (data !== undefined) {
      options.headers = { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }
      options.body = JSON.stringify(data)
    }
    const response = await fetcher(`/api/${path}`, options)
    const result = await response.json()
    if (!response.ok) throw new Error(result.error || '请求失败，请重试')
    if (result.csrf) csrf = result.csrf
    return result
  }
}

export const api = createApi()
