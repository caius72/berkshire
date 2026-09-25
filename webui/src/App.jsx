import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api, subscribe } from './api.js'
import Markdown from './Markdown.jsx'

const VIEWS = ['Runs', 'Decisions', 'Orders', 'Backtests', 'Jobs']
const TEAMS = ['Analyst Team', 'Research Team', 'Trading Team', 'Risk Management', 'Portfolio Management']
const TEAM_SHORT = { 'Analyst Team': 'Analysts', 'Research Team': 'Research', 'Trading Team': 'Trader',
  'Risk Management': 'Risk committee', 'Portfolio Management': 'Portfolio manager' }

const signalClass = (s) => `sig sig-${(s || 'none').toLowerCase()}`
const Signal = ({ value }) => <span className={signalClass(value)}>{value || 'In progress'}</span>

function useAsync(fn, deps) {
  const [state, set] = useState({ data: null, error: null })
  const reload = useCallback(() => fn().then((data) => set({ data, error: null }), (error) => set({ data: null, error })), deps) // eslint-disable-line
  useEffect(() => { reload() }, [reload])
  return [state, reload]
}

// --- The floor: five teams, one seat per agent (the page's centrepiece) ------------
function Floor({ progress }) {
  const byTeam = useMemo(() => TEAMS.map((t) => ({ team: t, seats: progress.filter((p) => p.team === t) })), [progress])
  return (
    <ol className="floor" aria-label="Agent progress by team">
      {byTeam.map(({ team, seats }) => {
        const state = seats.every((s) => s.status === 'done') ? 'done'
          : seats.some((s) => s.status !== 'pending') ? 'active' : 'pending'
        return (
          <li key={team} className={`station station-${state}`}>
            <span className="station-name">{TEAM_SHORT[team]}</span>
            <span className="seats">
              {seats.map((s) => (
                <span key={s.agent} className={`seat seat-${s.status.replace(' ', '-')}`} title={`${s.agent}: ${s.status}`}>
                  <span className="seat-dot" aria-hidden="true" />
                  {s.agent}
                </span>
              ))}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

function OrderCard({ orders }) {
  if (!orders) return <p className="muted">The risk gate hasn't run for this analysis yet.</p>
  const i = orders.intent
  return (
    <div className="order">
      {i ? (
        <p className="order-line">
          <strong>{i.kind === 'open' ? `Buy ${i.etoro_symbol}` : `Reduce ${i.etoro_symbol}`}</strong>
          {i.kind === 'open' && <> for ${i.amount.toLocaleString()}, stop at {i.stop_loss_rate}{i.take_profit_rate ? `, target ${i.take_profit_rate}` : ''}</>}
          {i.kind === 'close' && <> by closing {i.closes.length} position{i.closes.length > 1 ? 's' : ''}</>}
          <span className="account">{i.account}</span>
        </p>
      ) : <p className="order-line"><strong>No order</strong></p>}
      <ul className="reasons">{orders.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
      {i && <p className="muted small">Place it from Claude with <code>/berkshire:approve</code>. Every order is confirmed there, one at a time.</p>}
    </div>
  )
}

function RunDetail({ run, tick }) {
  const [{ data, error }, reload] = useAsync(() => api.run(run.ticker, run.date), [run.ticker, run.date])
  const [section, setSection] = useState(null)
  useEffect(() => { reload() }, [tick]) // eslint-disable-line
  useEffect(() => { setSection(null) }, [run.ticker, run.date])
  if (error) return <p className="error">{error.message}</p>
  if (!data) return <p className="muted">Loading {run.ticker}…</p>
  const s = data.summary
  const company = /Company: ([^;.]+)/.exec(data.instrument_context)?.[1] || /Name: ([^;.]+)/.exec(data.instrument_context)?.[1]
  const current = section ?? data.sections.length - 1
  const sec = data.sections[current]
  return (
    <article className="run">
      <header className="run-head">
        <div>
          <h1>{s.ticker}</h1>
          <p className="company">{company || s.asset_type} <span className="muted">analysed for {s.date}</span></p>
        </div>
        <div className="verdict">
          <Signal value={s.signal} />
          <span className="muted small">{s.done} of {s.total} agents finished</span>
        </div>
      </header>
      <Floor progress={data.progress} />
      <div className="run-body">
        <section className="reader" aria-label="Reports">
          <nav className="sections">
            {data.sections.length === 0 && <p className="muted small">Reports appear here as each agent finishes.</p>}
            {data.sections.map((x, i) => (
              <button key={x.dir + x.key} className={i === current ? 'on' : ''} onClick={() => setSection(i)}>
                <span className="sec-team">{x.team.split('. ')[0]}</span>{x.agent}
              </button>
            ))}
          </nav>
          <div className="report">
            {sec ? <><h2>{sec.agent}</h2><Markdown text={sec.text} /></> : null}
          </div>
        </section>
        <aside className="side">
          <h3>Order proposal</h3>
          <OrderCard orders={data.orders} />
          {data.warnings.length > 0 && (<><h3>Warnings</h3><ul className="warnings">{data.warnings.map((w) => <li key={w}>{w}</li>)}</ul></>)}
          <h3>Timeline</h3>
          <ol className="timeline">
            {[...data.timeline].reverse().map((t) => (
              <li key={t.step}><time>{t.at ? t.at.slice(11, 16) : '--:--'}</time>{t.step.replace(/_/g, ' ')}</li>
            ))}
            {data.timeline.length === 0 && <li className="muted">No steps recorded yet.</li>}
          </ol>
        </aside>
      </div>
    </article>
  )
}

function Runs({ tick, onNew }) {
  const [{ data: runs, error }, reload] = useAsync(api.runs, [])
  const [sel, setSel] = useState(null)
  useEffect(() => { reload() }, [tick]) // eslint-disable-line
  if (error) return <p className="error">{error.message}</p>
  if (!runs) return <p className="muted">Loading analyses…</p>
  if (runs.length === 0) return (
    <div className="empty"><h2>No analyses yet</h2><p>Start one here, or run <code>/berkshire:analyze NVDA</code> in Claude Code.</p>
      <button className="primary" onClick={onNew}>New analysis</button></div>)
  const current = runs.find((r) => sel && r.ticker === sel.ticker && r.date === sel.date) || runs[0]
  return (
    <div className="runs">
      <nav className="run-list" aria-label="Analyses">
        {runs.map((r) => (
          <button key={r.ticker + r.date} className={r === current ? 'on' : ''} onClick={() => setSel(r)}>
            <span className="rl-ticker">{r.ticker}</span>
            <Signal value={r.signal} />
            <span className="rl-date">{r.date}</span>
            <span className="rl-bar" style={{ '--p': r.done / r.total }} aria-label={`${r.done} of ${r.total}`} />
          </button>
        ))}
      </nav>
      <RunDetail run={current} tick={tick} />
    </div>
  )
}

function Table({ cols, rows, empty }) {
  if (!rows?.length) return <p className="muted">{empty}</p>
  return (
    <div className="table-wrap"><table className="data">
      <thead><tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, k) => <td key={k}>{c}</td>)}</tr>)}</tbody>
    </table></div>
  )
}

function Decisions({ tick }) {
  const [{ data, error }, reload] = useAsync(api.memory, [])
  useEffect(() => { reload() }, [tick]) // eslint-disable-line
  if (error) return <p className="error">{error.message}</p>
  return (
    <section className="page-section"><h2>Decision log</h2>
      <p className="lede">Each finished analysis is logged here. After the holding window has traded, it gets its return, its alpha against the benchmark, and a lesson that the portfolio manager reads next time.</p>
      <Table cols={['Date', 'Ticker', 'Rating', 'Return', 'Alpha', 'Window', 'Lesson']} empty="No decisions logged yet."
        rows={data?.map((e) => [e.date, e.ticker, <Signal value={e.rating} />, e.raw || 'pending', e.alpha || '', e.holding || '', e.reflection || <span className="muted">not yet settled</span>])} />
    </section>
  )
}

function Orders({ tick }) {
  const [{ data, error }, reload] = useAsync(api.queue, [])
  useEffect(() => { reload() }, [tick]) // eslint-disable-line
  if (error) return <p className="error">{error.message}</p>
  return (
    <section className="page-section"><h2>Order queue</h2>
      <p className="lede">Proposals from the risk gate. They are read-only here. Place or reject them from Claude with <code>/berkshire:approve</code>, which confirms each one with eToro.</p>
      <Table cols={['Created', 'Instrument', 'Rating', 'Order', 'Stop', 'Account', 'Status']} empty="The queue is empty."
        rows={data?.map((q) => [q.created.replace('T', ' ').slice(0, 16), q.intent.etoro_symbol, <Signal value={q.intent.rating} />,
          q.intent.kind === 'open' ? `Buy $${q.intent.amount}` : `Close ${q.intent.closes.length}`, q.intent.stop_loss_rate ?? '', q.intent.account,
          <span className={`status status-${q.status}`}>{q.status.replace('_', ' ')}</span>])} />
    </section>
  )
}

function Backtests({ tick }) {
  const [{ data, error }, reload] = useAsync(api.backtests, [])
  useEffect(() => { reload() }, [tick]) // eslint-disable-line
  if (error) return <p className="error">{error.message}</p>
  return (
    <section className="page-section"><h2>Backtests</h2>
      {!data?.length && <p className="muted">No backtests yet. Run <code>/berkshire:backtest NVDA,AAPL --start 2026-06-01 --end 2026-08-01</code> in Claude Code.</p>}
      {data?.map((b) => (
        <div key={b.run_id} className="bt">
          <h3>{b.run_id}</h3>
          <p className="muted small">{b.resolved} settled, {b.pending} waiting for their window, {b.unscored} without a rating</p>
          <Table cols={['Rating', 'Decisions', 'Called direction', 'Mean alpha']} empty="Nothing settled yet."
            rows={Object.entries(b.by_rating).map(([r, s]) => [<Signal value={r} />, s.count,
              s.hit_rate == null ? 'no direction' : `${Math.round(s.hit_rate * 100)}%`, `${(s.mean_alpha * 100).toFixed(2)}%`])} />
        </div>
      ))}
    </section>
  )
}

function Jobs({ tick }) {
  const [{ data, error }, reload] = useAsync(api.jobs, [])
  useEffect(() => { reload() }, [tick]) // eslint-disable-line
  if (error) return <p className="error">{error.message}</p>
  return (
    <section className="page-section"><h2>Jobs</h2>
      <p className="lede">Analyses started from this page run headless in Claude Code. Their output log is below.</p>
      <Table cols={['Started', 'Instrument', 'Date', 'Status']} empty="No jobs started from here yet."
        rows={data?.map((j) => [j.started.replace('T', ' ').slice(0, 16), j.ticker, j.date, <span className={`status status-${j.status.split(' ')[0]}`}>{j.status}</span>])} />
      {data?.[0]?.log_tail && <pre className="log">{data[0].log_tail}</pre>}
    </section>
  )
}

function NewAnalysis({ onClose, onStarted }) {
  const today = new Date().toISOString().slice(0, 10)
  const [form, setForm] = useState({ ticker: '', date: today, depth: 'shallow', analysts: ['market', 'social', 'news', 'fundamentals'] })
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const toggle = (a) => setForm((f) => ({ ...f, analysts: f.analysts.includes(a) ? f.analysts.filter((x) => x !== a) : [...f.analysts, a] }))
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr(null)
    try { onStarted(await api.startJob(form)) } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  return (
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="na-title" onKeyDown={(e) => e.key === 'Escape' && onClose()}>
      <form className="sheet" onSubmit={submit}>
        <h2 id="na-title">New analysis</h2>
        <label>Instrument<input autoFocus required value={form.ticker} placeholder="NVDA, RHM.DE, BTC-USD"
          onChange={(e) => setForm({ ...form, ticker: e.target.value.toUpperCase() })} /></label>
        <label>Analysis date<input type="date" max={today} value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></label>
        <fieldset><legend>Analysts</legend>
          {['market', 'social', 'news', 'fundamentals'].map((a) => (
            <label key={a} className="check"><input type="checkbox" checked={form.analysts.includes(a)} onChange={() => toggle(a)} />{a === 'social' ? 'sentiment' : a}</label>))}
        </fieldset>
        <label>Research depth
          <select value={form.depth} onChange={(e) => setForm({ ...form, depth: e.target.value })}>
            <option value="shallow">Shallow, one debate round</option><option value="medium">Medium, three rounds</option><option value="deep">Deep, five rounds</option>
          </select></label>
        {err && <p className="error">{err}</p>}
        <div className="sheet-actions">
          <button type="button" onClick={onClose}>Cancel</button>
          <button className="primary" disabled={busy || !form.ticker || !form.analysts.length}>{busy ? 'Starting…' : 'Start analysis'}</button>
        </div>
        <p className="muted small">This runs <code>/berkshire:analyze</code> headless in Claude Code. It never places orders.</p>
      </form>
    </div>
  )
}

export default function App() {
  const [view, setView] = useState('Runs')
  const [tick, setTick] = useState(0)
  const [live, setLive] = useState('connecting')
  const [modal, setModal] = useState(false)
  const [toast, setToast] = useState(null)
  useEffect(() => subscribe((ev) => { if (ev === 'change') setTick((t) => t + 1) }, setLive), [])
  return (
    <div className="app">
      <header className="top">
        <span className="brand">Berkshire</span>
        <nav className="views">
          {VIEWS.map((v) => <button key={v} className={v === view ? 'on' : ''} aria-current={v === view ? 'page' : undefined} onClick={() => setView(v)}>{v}</button>)}
        </nav>
        <span className={`live live-${live}`} title={live === 'live' ? 'Updates as agents finish' : 'Reconnecting to berkshire serve'}>{live === 'live' ? 'Live' : live === 'offline' ? 'Offline' : 'Connecting'}</span>
        <button className="primary" onClick={() => setModal(true)}>New analysis</button>
      </header>
      <main>
        {view === 'Runs' && <Runs tick={tick} onNew={() => setModal(true)} />}
        {view === 'Decisions' && <Decisions tick={tick} />}
        {view === 'Orders' && <Orders tick={tick} />}
        {view === 'Backtests' && <Backtests tick={tick} />}
        {view === 'Jobs' && <Jobs tick={tick} />}
      </main>
      <footer className="foot">Research output from a multi-agent LLM system, not financial advice. Every order needs your approval in Claude Code.</footer>
      {modal && <NewAnalysis onClose={() => setModal(false)} onStarted={(j) => { setModal(false); setToast(`Started ${j.ticker} for ${j.date}`); setView('Jobs') }} />}
      {toast && <div className="toast" role="status" onAnimationEnd={() => setToast(null)}>{toast}</div>}
    </div>
  )
}
