import React from 'react'
import { parseBlocks, parseInline } from './md.js'

// Blocks and inline runs are parsed fresh from immutable text and hold no state, so their
// position is their identity: index keys are correct here (noArrayIndexKey is off for this file).

const Inline = ({ text }) =>
  parseInline(text).map((r, i) =>
    r.t === 'b' ? <strong key={i}>{r.v}</strong>
      : r.t === 'i' ? <em key={i}>{r.v}</em>
        : r.t === 'code' ? <code key={i}>{r.v}</code>
          : <React.Fragment key={i}>{r.v}</React.Fragment>)

export default function Markdown({ text }) {
  return (
    <div className="md">
      {parseBlocks(text).map((b, i) => {
        switch (b.type) {
          case 'heading': return React.createElement(`h${Math.min(b.level + 1, 6)}`, { key: i }, <Inline text={b.text} />)
          case 'code': return <pre key={i}><code>{b.text}</code></pre>
          case 'hr': return <hr key={i} />
          case 'quote': return <blockquote key={i}><Inline text={b.text} /></blockquote>
          case 'list': {
            const Tag = b.ordered ? 'ol' : 'ul'
            return <Tag key={i}>{b.items.map((it, k) => <li key={k}><Inline text={it} /></li>)}</Tag>
          }
          case 'table':
            return (
              <div key={i} className="table-wrap">
                <table>
                  <thead><tr>{b.head.map((h, k) => <th key={k}><Inline text={h} /></th>)}</tr></thead>
                  <tbody>{b.rows.map((r, k) => <tr key={k}>{r.map((c, n) => <td key={n}><Inline text={c} /></td>)}</tr>)}</tbody>
                </table>
              </div>
            )
          default: return <p key={i}><Inline text={b.text} /></p>
        }
      })}
    </div>
  )
}
