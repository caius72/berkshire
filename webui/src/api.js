// Client of the Berkshire API (berkshire/server.py). Relative URLs, so requests are
// same-origin (built bundle served by the backend, or the Vite dev proxy).
//
// The session token arrives once as `?t=` (printed by `berkshire web`). It moves into
// sessionStorage and leaves the address bar, so it doesn't end up in copied links or
// history. A new server run mints a new token.
const TOKEN_KEY = 'berkshire-token'

export function takeToken(loc = globalThis.location, store = globalThis.sessionStorage, history = globalThis.history) {
  const u = new URL(loc.href)
  const t = u.searchParams.get('t')
  if (t) {
    store.setItem(TOKEN_KEY, t)
    u.searchParams.delete('t')
    history.replaceState({}, '', u.pathname + u.search + u.hash)
  }
  return store.getItem(TOKEN_KEY) || ''
}

let HDR = null
const headers = () => (HDR ??= { 'X-WebUI': '1', 'X-WebUI-Token': takeToken() })

async function j(r) {
  if (r.status === 403) throw new Error('HTTP 403: stale session token. Reopen the URL printed by `berkshire web`.')
  const body = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(body.error || `HTTP ${r.status}`)
  return body
}

export const get = (path) => fetch(path, { headers: headers() }).then(j)
export const post = (path, body) =>
  fetch(path, { method: 'POST', headers: { ...headers(), 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(j)

export const api = {
  runs: () => get('/api/runs'),
  run: (ticker, date) => get(`/api/runs/${encodeURIComponent(ticker)}/${encodeURIComponent(date)}`),
  memory: () => get('/api/memory'),
  queue: () => get('/api/queue'),
  backtests: () => get('/api/backtests'),
  jobs: () => get('/api/jobs'),
  startJob: (form) => post('/api/jobs', form),
  stopRun: (ticker, date) => post(`/api/runs/${encodeURIComponent(ticker)}/${encodeURIComponent(date)}/stop`, {}),
}

// Incremental SSE parser, pure so it tests under node. Feed text chunks; returns
// complete events and the unconsumed remainder to prepend to the next chunk.
export function parseSSE(buffer) {
  const events = []
  const blocks = buffer.split(/\r?\n\r?\n/)
  const rest = blocks.pop()
  for (const block of blocks) {
    let event = 'message'
    const data = []
    for (const line of block.split(/\r?\n/)) {
      if (!line || line.startsWith(':')) continue
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
    }
    if (data.length) events.push({ event, data: JSON.parse(data.join('\n')) })
  }
  return { events, rest }
}

// EventSource cannot send our auth headers, so read the stream with fetch.
// Calls onEvent(name, data), reconnects with backoff, and returns a stop() function.
export function subscribe(onEvent, onStatus = () => {}) {
  let stopped = false
  let ctrl = null
  let delay = 1000
  const loop = async () => {
    while (!stopped) {
      try {
        ctrl = new AbortController()
        const r = await fetch('/api/events', { headers: headers(), signal: ctrl.signal })
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        onStatus('live')
        delay = 1000
        const reader = r.body.getReader()
        const dec = new TextDecoder()
        let buf = ''
        for (;;) {
          const { value, done } = await reader.read()
          if (done) break
          const out = parseSSE(buf + dec.decode(value, { stream: true }))
          buf = out.rest
          for (const e of out.events) onEvent(e.event, e.data)
        }
      } catch {
        if (stopped) return
      }
      onStatus('offline')
      await new Promise((res) => setTimeout(res, delay))
      delay = Math.min(delay * 2, 15000)
    }
  }
  loop()
  return () => { stopped = true; ctrl?.abort() }
}
