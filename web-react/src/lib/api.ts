/* API 封装 - 与 Vue 版 useApi 保持一致（带重试） */
const API_BASE = window.location.origin

interface FetchOptions {
  method?: string
  body?: string
  query?: Record<string, string | number>
  retries?: number
}

export async function fetchJson<T>(url: string, options?: FetchOptions): Promise<T> {
  const fullUrl = url.startsWith('http') ? url : API_BASE + url
  const method = options?.method ?? 'GET'
  const retries = options?.retries ?? 3

  let finalUrl = fullUrl
  if (options?.query) {
    const qs = new URLSearchParams(
      Object.entries(options.query).map(([k, v]) => [k, String(v)])
    ).toString()
    finalUrl = fullUrl + (fullUrl.includes('?') ? '&' : '?') + qs
  }

  for (let i = 0; i < retries; i++) {
    try {
      const r = await fetch(finalUrl, {
        method,
        headers: method === 'POST' ? { 'Content-Type': 'application/json' } : {},
        body: method === 'POST' ? options?.body : undefined,
      })
      if (!r.ok && r.status >= 500 && i < retries - 1) {
        await new Promise((res) => setTimeout(res, 500))
        continue
      }
      return (await r.json()) as T
    } catch (e) {
      if (i < retries - 1) {
        await new Promise((res) => setTimeout(res, 500))
        continue
      }
      throw e
    }
  }
  throw new Error('fetchJson: unreachable')
}

export async function postJson<T = any>(url: string, body: any): Promise<T> {
  const fullUrl = url.startsWith('http') ? url : API_BASE + url
  const r = await fetch(fullUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return (await r.json()) as T
}

export { API_BASE }
