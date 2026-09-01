/* 后端 API 契约（TC-API，回归保障）*/
import { expect, test } from '@playwright/test'

const BASE = 'http://127.0.0.1:18980'

test.describe('TC-API 后端 API 契约', () => {
  test('API-01 GET /overview/model', async ({ request }) => {
    const r = await request.get(`${BASE}/overview/model`)
    expect(r.status()).toBe(200)
    const d = await r.json()
    expect(d).toHaveProperty('loaded')
    expect(d).toHaveProperty('device')
    expect(d).toHaveProperty('embedding_model')
    expect(typeof d.loaded).toBe('boolean')
    expect(['cpu', 'cuda']).toContain(d.device)
  })

  test('API-02 GET /overview/qdrant', async ({ request }) => {
    const r = await request.get(`${BASE}/overview/qdrant`)
    expect(r.status()).toBe(200)
    const d = await r.json()
    expect(d).toHaveProperty('ready')
    expect(d).toHaveProperty('host')
    expect(d).toHaveProperty('port')
    expect(d).toHaveProperty('collection')
  })

  test('API-03 GET /overview/flask', async ({ request }) => {
    const r = await request.get(`${BASE}/overview/flask`)
    expect(r.status()).toBe(200)
    const d = await r.json()
    expect(d).toHaveProperty('pid')
    expect(d).toHaveProperty('port')
    expect(d).toHaveProperty('uptime')
    expect(d.port).toBe(18980)
  })

  test('API-04 GET /memory/count', async ({ request }) => {
    const r = await request.get(`${BASE}/memory/count`)
    expect(r.status()).toBe(200)
    const d = await r.json()
    expect(d.count).toBeGreaterThanOrEqual(0)
  })

  test('API-05 GET /chat/state 与 /chat/seq', async ({ request }) => {
    const r1 = await request.get(`${BASE}/chat/state`)
    expect(r1.status()).toBe(200)
    const s = await r1.json()
    expect(typeof s).toBe('object')
    const r2 = await request.get(`${BASE}/chat/seq`)
    expect(r2.status()).toBe(200)
    const seq = await r2.json()
    expect(seq).toHaveProperty('seq')
    expect(typeof seq.seq).toBe('number')
  })

  test('API-07 GET /brain/state 与 /brain/runs/recent', async ({ request }) => {
    const r1 = await request.get(`${BASE}/brain/state`)
    expect(r1.status()).toBe(200)
    const r2 = await request.get(`${BASE}/brain/runs/recent?limit=5`)
    expect(r2.status()).toBe(200)
    const d = await r2.json()
    expect(Array.isArray(d.runs ?? [])).toBe(true)
  })

  test('API-08 GET /stream/api?action=store&days=3', async ({ request }) => {
    const r = await request.get(`${BASE}/stream/api?action=store&days=3`)
    expect(r.status()).toBe(200)
    const d = await r.json()
    expect(Array.isArray(d.items)).toBe(true)
  })

  test('API-EXTRA GET /statusbar/api', async ({ request }) => {
    const r = await request.get(`${BASE}/statusbar/api`)
    expect(r.status()).toBe(200)
    const d = await r.json()
    expect(d).toHaveProperty('model_loaded')
    expect(d).toHaveProperty('qdrant_ready')
    expect(d).toHaveProperty('device')
  })

  test('API-EXTRA GET /memory/search-history', async ({ request }) => {
    const r = await request.get(`${BASE}/memory/search-history`)
    expect(r.status()).toBe(200)
    const d = await r.json()
    expect(Array.isArray(d.history)).toBe(true)
  })
})
