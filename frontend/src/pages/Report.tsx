import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, type AuditDetail, type CategoryKey, type Report } from '../api'
import { IssueList } from '../components/IssueList'
import { ScoreGauge } from '../components/ScoreGauge'
import { IssuesByCategoryChart, Legend, PageWeightChart } from '../components/charts'
import {
  CATEGORY_BLURBS, CATEGORY_KEYS, CATEGORY_LABELS, SEVERITIES, band, formatBytes, formatMs, hostname, plural,
} from '../lib/format'
import { severityColor, useTheme } from '../lib/theme'

const STEPS = ['Starting', 'Loading page', 'Parsing HTML', 'Checking', 'Reading stylesheets', 'Analysing results']

export function ReportPage() {
  const { id } = useParams()
  // Keyed so navigating between audits starts from a clean slate.
  return <AuditLoader key={id} auditId={Number(id)} />
}

function AuditLoader({ auditId }: { auditId: number }) {
  const [audit, setAudit] = useState<AuditDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let timer: number | undefined
    async function poll() {
      try {
        const data = await api.getAudit(auditId)
        if (cancelled) return
        setAudit(data)
        if (data.status === 'queued' || data.status === 'running') timer = window.setTimeout(poll, 1200)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load audit.')
      }
    }
    poll()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [auditId])

  if (error) return <div className="error-box progress-card">{error}</div>
  if (!audit) return <div className="progress-card"><div className="spinner" /></div>
  if (audit.status === 'failed') return <Failed audit={audit} />
  if (audit.status !== 'done' || !audit.report) return <InProgress audit={audit} />
  return <ReportView audit={audit} report={audit.report} />
}

function InProgress({ audit }: { audit: AuditDetail }) {
  const progress = audit.progress ?? 'Starting'
  const current = Math.max(0, STEPS.findIndex((s) => progress.startsWith(s)))
  return (
    <div className="card progress-card" aria-live="polite">
      <div className="spinner" />
      <h1 style={{ fontSize: 22 }}>Auditing {hostname(audit.url)}</h1>
      <p className="muted small">This usually takes 5–30 seconds.</p>
      <ol className="steps">
        {STEPS.map((step, i) => (
          <li key={step} className={i < current ? 'done' : i === current ? 'current' : 'todo'}>
            {i === current ? progress : step === 'Checking' ? 'Checking resources and links' : step}
          </li>
        ))}
      </ol>
    </div>
  )
}

function Failed({ audit }: { audit: AuditDetail }) {
  const navigate = useNavigate()
  const [retryError, setRetryError] = useState<string | null>(null)

  async function retry() {
    try {
      navigate(`/audits/${(await api.createAudit(audit.url)).id}`)
    } catch (err) {
      setRetryError(err instanceof Error ? err.message : 'Could not start a new audit.')
    }
  }

  return (
    <div className="card progress-card">
      <h1 style={{ fontSize: 22, marginBottom: 12 }}>We couldn't audit {hostname(audit.url)}</h1>
      <div className="error-box" role="alert">{audit.error}</div>
      <div className="report-actions" style={{ justifyContent: 'center' }}>
        <button
          className="btn btn-primary"
          onClick={retry}
        >
          Try again
        </button>
        <Link className="btn" to="/">New audit</Link>
      </div>
      {retryError && <div className="error-box mt-20" role="alert">{retryError}</div>}
    </div>
  )
}

function ReportView({ audit, report }: { audit: AuditDetail; report: Report }) {
  const navigate = useNavigate()
  const [tab, setTab] = useState<CategoryKey>(() => worstCategory(report))
  const [rerunning, setRerunning] = useState(false)
  const totalIssues = SEVERITIES.reduce((n, s) => n + report.issue_counts[s], 0)

  const [actionError, setActionError] = useState<string | null>(null)

  async function rerun() {
    setRerunning(true)
    setActionError(null)
    try {
      const next = await api.createAudit(audit.url)
      navigate(`/audits/${next.id}`)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not start a new audit.')
      setRerunning(false)
    }
  }

  function selectCategory(key: CategoryKey) {
    setTab(key)
    document.getElementById('details')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="grid">
      <section className="card report-head">
        <ScoreGauge score={report.scores.overall} size={148} />
        <div style={{ minWidth: 0 }}>
          <p className="muted small" style={{ margin: '0 0 4px' }}>
            Audit #{audit.id} · {new Date(report.fetched_at).toLocaleString()}
          </p>
          <h1>{report.page.title || hostname(report.final_url)}</h1>
          <a className="final-url" href={report.final_url} target="_blank" rel="noopener noreferrer">
            {report.final_url} ↗
          </a>
          <div className="severity-summary" aria-label="Issues by severity">
            <span><b>{totalIssues}</b> issues</span>
            {SEVERITIES.map((s) => (
              <span key={s} className="legend-item">
                <span className={`severity-dot ${s}`} aria-hidden="true" />
                <b>{report.issue_counts[s]}</b> {s}
              </span>
            ))}
          </div>
          <div className="report-actions">
            <a className="btn btn-primary" href={api.pdfUrl(audit.id)} download>
              Download PDF
            </a>
            <button className="btn" onClick={rerun} disabled={rerunning}>
              {rerunning ? 'Starting…' : 'Re-run audit'}
            </button>
            <Link className="btn" to={`/compare?ids=${audit.id}`}>Compare with…</Link>
          </div>
          {actionError && <div className="error-box mt-20" role="alert">{actionError}</div>}
        </div>
      </section>

      <section className="card" aria-label="Category scores">
        <div className="category-gauges">
          {CATEGORY_KEYS.map((key) => (
            <ScoreGauge
              key={key}
              score={report.scores[key]}
              label={CATEGORY_LABELS[key]}
              size={80}
              onClick={() => selectCategory(key)}
              pressed={tab === key}
            />
          ))}
        </div>
        <p className="muted small" style={{ margin: '14px 0 0', textAlign: 'center' }}>
          Scores are calculated by Site Auditor from automated checks of this page's HTML, headers and links.
          {report.pagespeed && !report.pagespeed.error
            ? ' Google Lighthouse results are shown separately below.'
            : ' They are not Google Lighthouse scores.'}
        </p>
      </section>

      <div className="grid grid-2">
        <MetricsCard report={report} />
        <section className="card">
          <h2 className="card-title">Where the problems are</h2>
          <p className="card-sub">Issues found in each category, by severity.</p>
          <IssuesByCategoryChart report={report} />
        </section>
      </div>

      <section className="card" id="details" style={{ scrollMarginTop: 80 }}>
        <div className="tabs" role="tablist" aria-label="Audit categories">
          {CATEGORY_KEYS.map((key) => (
            <button
              key={key}
              role="tab"
              className="tab"
              aria-selected={tab === key}
              onClick={() => setTab(key)}
            >
              {CATEGORY_LABELS[key]}
              <span className="count">{report.categories[key].issues.length}</span>
            </button>
          ))}
        </div>
        <div role="tabpanel">
          <p className="card-sub">
            {CATEGORY_BLURBS[tab]} Score: <strong>{report.scores[tab]}/100</strong>
          </p>
          <IssueList category={report.categories[tab]} />
        </div>
      </section>

      <div className="grid grid-2">
        <WeightCard report={report} />
        <LinksCard report={report} />
      </div>

      <DesignCard report={report} />
      {report.pagespeed && <PageSpeedCard report={report} />}
    </div>
  )
}

function worstCategory(report: Report): CategoryKey {
  return CATEGORY_KEYS.reduce((worst, key) => (report.scores[key] < report.scores[worst] ? key : worst))
}

// Mirrors the backend thresholds in audit/performance.py.
const METRIC_DEFS = [
  { key: 'ttfb_ms', label: 'Server response', good: 600, poor: 2500, fmt: formatMs, note: 'Time to first byte' },
  { key: 'load_ms', label: 'HTML download', good: 1000, poor: 5000, fmt: formatMs, note: 'Full HTML received' },
  { key: 'page_weight_kb', label: 'Page weight', good: 1500, poor: 6000, fmt: (v: number) => formatBytes(v * 1024), note: 'HTML + discovered files' },
  { key: 'request_count', label: 'Requests', good: 40, poor: 150, fmt: String, note: 'Files referenced in HTML' },
  { key: 'dom_elements', label: 'DOM elements', good: 1000, poor: 4000, fmt: (v: number) => v.toLocaleString(), note: 'Page complexity' },
] as const

function MetricsCard({ report }: { report: Report }) {
  const { colors } = useTheme()
  return (
    <section className="card">
      <h2 className="card-title">Speed & size</h2>
      <p className="card-sub">Measured from our server. Bars fill up as metrics get better.</p>
      <div className="metric-tiles">
        {METRIC_DEFS.map((m) => {
          const value = report.metrics[m.key]
          const score = value <= m.good ? 100 : value >= m.poor ? 0 : (100 * (m.poor - value)) / (m.poor - m.good)
          const b = band(score)
          const color = b === 'good' ? colors.good : b === 'average' ? colors.warning : colors.critical
          return (
            <div className="metric" key={m.key}>
              <div className="metric-label">{m.label}</div>
              <div className="metric-value">{m.fmt(value)}</div>
              <div className="meter" role="meter" aria-valuenow={Math.round(score)} aria-valuemin={0} aria-valuemax={100} aria-label={`${m.label} rating`}>
                <span style={{ width: `${Math.max(4, score)}%`, background: color }} />
              </div>
              <div className="metric-note">{m.note}</div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function WeightCard({ report }: { report: Report }) {
  const { metrics } = report
  return (
    <section className="card">
      <h2 className="card-title">What the page is made of</h2>
      <p className="card-sub">
        Download size by file type
        {metrics.unknown_sizes > 0 && ` (${metrics.unknown_sizes} files didn't report a size)`}.
      </p>
      <PageWeightChart report={report} />
      {metrics.largest_resources.length > 0 && (
        <div className="table-wrap mt-20">
          <table className="data-table">
            <thead>
              <tr><th>Largest files</th><th className="num">Size</th></tr>
            </thead>
            <tbody>
              {metrics.largest_resources.slice(0, 5).map((r) => (
                <tr key={r.url}>
                  <td className="url-cell">{r.url.replace(/^https?:\/\//, '')}</td>
                  <td className="num">{formatBytes(r.bytes)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function LinksCard({ report }: { report: Report }) {
  const { colors } = useTheme()
  const { links } = report
  const parts = [
    { key: 'ok', label: 'Working', value: links.ok, color: colors.good },
    { key: 'redirect', label: 'Redirected', value: links.redirect, color: colors.series[0] },
    { key: 'blocked', label: 'Blocked bots', value: links.blocked, color: colors.warning },
    { key: 'broken', label: 'Broken', value: links.broken, color: colors.critical },
  ]
  const problems = links.items.filter((i) => i.state !== 'ok')
  return (
    <section className="card">
      <h2 className="card-title">Link health</h2>
      <p className="card-sub">
        Checked {links.checked} of {links.found} links ({links.internal} internal, {links.external} external).
      </p>
      {links.checked > 0 ? (
        <>
          <Legend items={parts.map((p) => ({ color: p.color, label: `${p.label} (${p.value})` }))} />
          <div className="stacked-bar" role="img" aria-label={parts.map((p) => `${p.value} ${p.label}`).join(', ')}>
            {parts.filter((p) => p.value > 0).map((p) => (
              <span key={p.key} style={{ flex: p.value, background: p.color }} title={`${p.label}: ${p.value}`} />
            ))}
          </div>
        </>
      ) : (
        <p className="empty">No links found on this page.</p>
      )}
      {(problems.length > 0 || links.broken_resources.length > 0) && (
        <div className="table-wrap" style={{ maxHeight: 320, overflowY: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr><th>Status</th><th>URL</th></tr>
            </thead>
            <tbody>
              {links.broken_resources.map((r) => (
                <tr key={`res-${r.url}`}>
                  <td><span className="state broken">{r.status ?? 'Error'} · {r.kind}</span></td>
                  <td className="url-cell">{r.url}</td>
                </tr>
              ))}
              {problems.map((item) => (
                <tr key={item.url}>
                  <td>
                    <span className={`state ${item.state}`}>
                      {item.status ?? 'Error'} · {item.state}
                    </span>
                  </td>
                  <td className="url-cell">
                    <a href={item.url} target="_blank" rel="noopener noreferrer">{item.url}</a>
                    {item.error && <div className="muted small">{item.error}</div>}
                    {item.final_url && <div className="muted small">→ {item.final_url}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function DesignCard({ report }: { report: Report }) {
  const { design } = report
  return (
    <section className="card">
      <h2 className="card-title">Design snapshot</h2>
      <p className="card-sub">The typefaces, colors and content structure we detected.</p>
      <div className="grid grid-3">
        <div>
          <h3 className="small muted" style={{ marginBottom: 8 }}>Typefaces ({design.fonts.length})</h3>
          {design.fonts.length ? (
            <ul className="font-list">
              {design.fonts.map((f) => <li key={f} style={{ fontFamily: `"${f}", system-ui` }}>{f}</li>)}
            </ul>
          ) : <p className="muted small">Only system fonts detected.</p>}
          <h3 className="small muted" style={{ margin: '18px 0 8px' }}>Content</h3>
          <p className="small" style={{ margin: 0 }}>
            {plural(design.word_count, 'word')} · {plural(design.images, 'image')} · {plural(design.headings.length, 'heading')}
          </p>
        </div>
        <div>
          <h3 className="small muted" style={{ marginBottom: 8 }}>Color palette ({design.colors.length})</h3>
          {design.colors.length ? (
            <div className="swatches">
              {design.colors.map((c) => (
                <span key={c} className="swatch" style={{ background: c }} title={c} aria-label={c} role="img" />
              ))}
            </div>
          ) : <p className="muted small">No colors found in CSS.</p>}
        </div>
        <div>
          <h3 className="small muted" style={{ marginBottom: 8 }}>Heading outline</h3>
          {design.headings.length ? (
            <ul className="outline">
              {design.headings.map((h, i) => (
                <li key={i} style={{ paddingLeft: (h.level - 1) * 12 }}>
                  <span className="tag">H{h.level}</span>{h.text || <em className="muted">(empty)</em>}
                </li>
              ))}
            </ul>
          ) : <p className="muted small">No headings found.</p>}
        </div>
      </div>
    </section>
  )
}

function PageSpeedCard({ report }: { report: Report }) {
  const { colors } = useTheme()
  const psi = report.pagespeed!
  if (psi.error) {
    return (
      <section className="card">
        <h2 className="card-title">Google Lighthouse (mobile)</h2>
        <div className="error-box" role="status">Lighthouse data is unavailable for this audit: {psi.error}</div>
      </section>
    )
  }
  return (
    <section className="card">
      <h2 className="card-title">Google Lighthouse (mobile)</h2>
      <p className="card-sub">Lab data from Google PageSpeed Insights, measured in a real browser.</p>
      <div className="category-gauges" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))' }}>
        {Object.entries(psi.categories).map(([key, score]) => (
          <ScoreGauge key={key} score={score} size={72} label={key.replace('-', ' ').replace(/^./, (c) => c.toUpperCase())} />
        ))}
      </div>
      <div className="metric-tiles mt-20">
        {psi.metrics.map((m) => {
          const s = (m.score ?? 0) * 100
          const severity = s >= 90 ? 'minor' : s >= 50 ? 'moderate' : 'critical'
          return (
            <div className="metric" key={m.id}>
              <div className="metric-label">{m.label}</div>
              <div className="metric-value">{m.value ?? '–'}</div>
              <div className="meter">
                <span style={{ width: `${Math.max(4, s)}%`, background: s >= 90 ? colors.good : severityColor(colors, severity) }} />
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
