import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, type AuditSummary, type CompareRow } from '../api'
import { CompareChart } from '../components/charts'
import { ScoreChip } from '../components/ScoreGauge'
import { CATEGORY_KEYS, CATEGORY_LABELS, formatBytes, formatMs, hostname, siteLabels, timeAgo } from '../lib/format'
import { useTheme } from '../lib/theme'

const MAX_SITES = 4

const METRIC_ROWS: { key: keyof CompareRow['metrics']; label: string; fmt: (v: number) => string }[] = [
  { key: 'ttfb_ms', label: 'Server response', fmt: formatMs },
  { key: 'load_ms', label: 'HTML download', fmt: formatMs },
  { key: 'page_weight_kb', label: 'Page weight', fmt: (v) => formatBytes(v * 1024) },
  { key: 'request_count', label: 'Requests', fmt: String },
  { key: 'dom_elements', label: 'DOM elements', fmt: (v) => v.toLocaleString() },
  { key: 'broken_links', label: 'Broken links', fmt: String },
]

export function Compare() {
  const { colors } = useTheme()
  const [params, setParams] = useSearchParams()
  const ids = useMemo(
    () => (params.get('ids') ?? '').split(',').map(Number).filter((n) => Number.isInteger(n) && n > 0).slice(0, MAX_SITES),
    [params],
  )
  const [audits, setAudits] = useState<AuditSummary[] | null>(null)
  const [rows, setRows] = useState<CompareRow[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .listAudits()
      .then((list) => setAudits(list.filter((a) => a.status === 'done')))
      .catch((err: Error) => setError(err.message))
  }, [])

  useEffect(() => {
    if (ids.length > 0) api.compare(ids).then(setRows).catch((err: Error) => setError(err.message))
  }, [ids])

  function toggle(id: number) {
    const next = ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id].slice(0, MAX_SITES)
    setParams(next.length ? { ids: next.join(',') } : {})
  }

  const shown = ids.length > 0 ? rows : []
  const best = (values: number[], higherIsBetter: boolean) =>
    higherIsBetter ? Math.max(...values) : Math.min(...values)

  return (
    <div className="grid">
      <div>
        <h1 style={{ fontSize: 28, marginBottom: 6 }}>Compare websites</h1>
        <p className="muted" style={{ margin: 0 }}>
          Benchmark your site against competitors. Pick up to {MAX_SITES} completed audits.
        </p>
      </div>

      <section className="card">
        <h2 className="card-title">Choose audits</h2>
        {error && <div className="error-box" role="alert">{error}</div>}
        {audits === null ? (
          !error && <p className="empty">Loading…</p>
        ) : audits.length === 0 ? (
          <p className="empty">
            No completed audits yet. <Link to="/">Run one first.</Link>
          </p>
        ) : (
          <ul className="audit-list">
            {audits.map((a) => (
              <li className="audit-row" key={a.id} style={{ gridTemplateColumns: 'auto 52px minmax(0,1fr) auto' }}>
                <input
                  type="checkbox"
                  id={`pick-${a.id}`}
                  checked={ids.includes(a.id)}
                  disabled={!ids.includes(a.id) && ids.length >= MAX_SITES}
                  onChange={() => toggle(a.id)}
                />
                <ScoreChip score={a.overall_score} />
                <label htmlFor={`pick-${a.id}`} className="url" style={{ cursor: 'pointer' }}>
                  {hostname(a.final_url ?? a.url)}
                </label>
                <span className="meta hide-sm">{timeAgo(a.created_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {shown.length >= 2 ? (
        <>
          <section className="card">
            <h2 className="card-title">Scores side by side</h2>
            <p className="card-sub">Higher is better. Hover a group to see exact values.</p>
            <CompareChart rows={shown} />
          </section>

          <section className="card">
            <h2 className="card-title">Head-to-head</h2>
            <p className="card-sub">The best value in each row is highlighted.</p>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Metric</th>
                    {shown.map((r, i) => (
                      <th key={r.id} className="num" style={{ textTransform: 'none', letterSpacing: 0 }}>
                        <span className="legend-item" style={{ justifyContent: 'flex-end' }}>
                          <span className="legend-swatch" style={{ background: colors.series[i] }} />
                          <Link to={`/audits/${r.id}`}>{siteLabels(shown)[i]}</Link>
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(['overall', ...CATEGORY_KEYS] as const).map((key) => {
                    const values = shown.map((r) => r.scores[key])
                    const top = best(values, true)
                    return (
                      <tr key={key}>
                        <td>{key === 'overall' ? <strong>Overall score</strong> : CATEGORY_LABELS[key]}</td>
                        {values.map((v, i) => (
                          <td key={shown[i].id} className={`num ${v === top ? 'best' : ''}`}>{v}</td>
                        ))}
                      </tr>
                    )
                  })}
                  {METRIC_ROWS.map((m) => {
                    const values = shown.map((r) => r.metrics[m.key])
                    const top = best(values, false)
                    return (
                      <tr key={m.key}>
                        <td>{m.label}</td>
                        {values.map((v, i) => (
                          <td key={shown[i].id} className={`num ${v === top ? 'best' : ''}`}>{m.fmt(v)}</td>
                        ))}
                      </tr>
                    )
                  })}
                  <tr>
                    <td>Critical + serious issues</td>
                    {(() => {
                      const values = shown.map((r) => r.issue_counts.critical + r.issue_counts.serious)
                      const top = best(values, false)
                      return values.map((v, i) => (
                        <td key={shown[i].id} className={`num ${v === top ? 'best' : ''}`}>{v}</td>
                      ))
                    })()}
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : (
        <p className="empty card">Select at least two audits to compare them.</p>
      )}
    </div>
  )
}
