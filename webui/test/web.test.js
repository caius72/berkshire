// Unit tests for the web view's pure modules: node --test test/
// Test ids trace to docs/test-plan.md like the Python ones (see tests/test_traceability.py).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { parseBlocks, parseInline } from '../src/md.js'
import { parseSSE, takeToken } from '../src/api.js'

test('TST-WEB-01: Report markdown parses to blocks the reader renders, tables included [REQ-UI-05]', () => {
  const md = '## Price action\n\nApple closed **above** the 50 SMA.\n\n| Level | Value |\n|---|---:|\n| Support | 245 |\n| ATR | 4.1 |\n\n- one\n- two\n\n1. first\n\n```\ncode\n```\n\n> quoted\n\n---'
  const blocks = parseBlocks(md)
  assert.deepEqual(blocks.map((b) => b.type), ['heading', 'para', 'table', 'list', 'list', 'code', 'quote', 'hr'])
  assert.deepEqual(blocks[2], { type: 'table', head: ['Level', 'Value'], rows: [['Support', '245'], ['ATR', '4.1']] })
  assert.equal(blocks[3].ordered, false)
  assert.equal(blocks[4].ordered, true)
  assert.equal(blocks[5].text, 'code')
})

test('TST-WEB-02: Inline markup becomes runs, never HTML; tags stay literal text [REQ-UI-05, REQ-UI-02]', () => {
  assert.deepEqual(parseInline('**Rating**: Buy at `224.5` *now*'),
    [{ t: 'b', v: 'Rating' }, { t: 'text', v: ': Buy at ' }, { t: 'code', v: '224.5' }, { t: 'text', v: ' ' }, { t: 'i', v: 'now' }])
  assert.deepEqual(parseInline('<img src=x onerror=alert(1)>'), [{ t: 'text', v: '<img src=x onerror=alert(1)>' }])
  assert.deepEqual(parseBlocks('<script>alert(1)</script>'), [{ type: 'para', text: '<script>alert(1)</script>' }])
})

test('TST-WEB-03: The SSE parser handles split chunks, comments and multi-event buffers [REQ-UI-04]', () => {
  let out = parseSSE('event: hello\ndata: {"keys":[]}\n\n: keep-alive\n\nevent: change\ndata: {"ke')
  assert.deepEqual(out.events, [{ event: 'hello', data: { keys: [] } }])
  out = parseSSE(out.rest + 'ys":["queue"]}\n\n')
  assert.deepEqual(out.events, [{ event: 'change', data: { keys: ['queue'] } }])
  assert.equal(out.rest, '')
})

test('TST-WEB-04: The ?t= token moves to sessionStorage and leaves the address bar [REQ-UI-02]', () => {
  const store = new Map()
  const storage = { setItem: (k, v) => store.set(k, v), getItem: (k) => store.get(k) ?? null }
  let replaced = null
  const history = { replaceState: (_s, _t, url) => { replaced = url } }
  assert.equal(takeToken({ href: 'http://127.0.0.1:8787/?t=abc#runs' }, storage, history), 'abc')
  assert.equal(replaced, '/#runs')
  assert.equal(takeToken({ href: 'http://127.0.0.1:8787/' }, storage, history), 'abc')
})
