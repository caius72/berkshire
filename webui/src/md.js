// Markdown → a small block/inline tree, rendered by Markdown.jsx as React elements.
// No innerHTML anywhere: report text is LLM output, so it never becomes markup.
// Covers what the agents write: headings, paragraphs, bullet/numbered lists,
// pipe tables, fenced code, blockquotes, rules, and **bold**, *italic*, `code`.
// ponytail: no nested lists or images. Add them if reports start using them.

const TABLE_SEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/

const cells = (line) => line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim())

export function parseBlocks(md) {
  const lines = (md || '').replace(/\r\n/g, '\n').split('\n')
  const blocks = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) { i++; continue }
    if (line.startsWith('```')) {
      const lang = line.slice(3).trim()
      const body = []
      i++
      while (i < lines.length && !lines[i].startsWith('```')) body.push(lines[i++])
      i++
      blocks.push({ type: 'code', lang, text: body.join('\n') })
      continue
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(line)
    if (h) { blocks.push({ type: 'heading', level: h[1].length, text: h[2].trim() }); i++; continue }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) { blocks.push({ type: 'hr' }); i++; continue }
    if (line.includes('|') && i + 1 < lines.length && TABLE_SEP.test(lines[i + 1])) {
      const head = cells(line)
      const rows = []
      i += 2
      while (i < lines.length && lines[i].includes('|') && lines[i].trim()) rows.push(cells(lines[i++]))
      blocks.push({ type: 'table', head, rows })
      continue
    }
    const li = /^\s*([-*+]|\d+[.)])\s+(.*)$/.exec(line)
    if (li) {
      const ordered = /\d/.test(li[1])
      const items = []
      while (i < lines.length) {
        const m = /^\s*([-*+]|\d+[.)])\s+(.*)$/.exec(lines[i])
        if (m) { items.push(m[2]); i++ } else if (lines[i].trim() && /^\s{2,}/.test(lines[i])) {
          items[items.length - 1] += ` ${lines[i].trim()}`; i++
        } else break
      }
      blocks.push({ type: 'list', ordered, items })
      continue
    }
    if (line.startsWith('>')) {
      const body = []
      while (i < lines.length && lines[i].startsWith('>')) body.push(lines[i++].replace(/^>\s?/, ''))
      blocks.push({ type: 'quote', text: body.join(' ') })
      continue
    }
    const para = []
    while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|```|>|\s*([-*+]|\d+[.)])\s)/.test(lines[i])
           && !(lines[i].includes('|') && TABLE_SEP.test(lines[i + 1] || ''))) para.push(lines[i++].trim())
    blocks.push({ type: 'para', text: para.join(' ') })
  }
  return blocks
}

// Inline runs: {t:'text'|'b'|'i'|'code', v}.
export function parseInline(s) {
  const out = []
  const re = /(`[^`]+`|\*\*[^*]+\*\*|__[^_]+__|\*[^*\s][^*]*\*)/g
  let last = 0
  for (const m of (s || '').matchAll(re)) {
    if (m.index > last) out.push({ t: 'text', v: s.slice(last, m.index) })
    const tok = m[0]
    if (tok.startsWith('`')) out.push({ t: 'code', v: tok.slice(1, -1) })
    else if (tok.startsWith('**') || tok.startsWith('__')) out.push({ t: 'b', v: tok.slice(2, -2) })
    else out.push({ t: 'i', v: tok.slice(1, -1) })
    last = m.index + tok.length
  }
  if (last < (s || '').length) out.push({ t: 'text', v: s.slice(last) })
  return out
}
