import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type AuditSummary } from '../api'
import { ScoreChip } from '../components/ScoreGauge'
import { hostname, timeAgo } from '../lib/format'

export function Home() {
  const navigate = useNavigate()
  const [url, setUrl] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [audits, setAudits] = useState<AuditSummary[] | null>(null)
  const [listError, setListError] = useState<string | null>(null)
  const [selected, setSelected] = useState<number[]>([])
  // Delete is permanent, so the first click only arms it; the second click deletes.
  const [confirming, setConfirming] = useState<number | null>(null)

  useEffect(() => {
    api.listAudits().then(setAudits).catch((err: Error) => setListError(err.message))
  }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const audit = await api.createAudit(url)
      navigate(`/audits/${audit.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.')
      setSubmitting(false)
    }
  }

  async function remove(id: number) {
    try {
      await api.deleteAudit(id)
    } catch (err) {
      setListError(err instanceof Error ? err.message : 'Could not delete that audit.')
      return
    }
    setListError(null)
    setAudits((list) => list?.filter((a) => a.id !== id) ?? null)
    setSelected((s) => s.filter((x) => x !== id))
  }

  function toggle(id: number) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : s.length >= 4 ? s : [...s, id]))
  }

  return (
    <>
      <section className="hero">
        <h1>What's wrong with your website?</h1>
        <p>
          Enter any URL for an instant audit of speed, accessibility, SEO, security, broken links and design,
          with a plain-English fix for every problem.
        </p>
        <form className="url-form" onSubmit={submit}>
          <label htmlFor="url" className="sr-only">
            Website URL
          </label>
          <input
            id="url"
            type="text"
            inputMode="url"
            autoComplete="url"
            placeholder="example.com"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
            autoFocus
          />
          <button className="btn btn-primary" type="submit" disabled={submitting || !url.trim()}>
            {submitting ? 'Starting…' : 'Audit website'}
          </button>
        </form>
        {error && (
          <div className="error-box" role="alert">
            {error}
          </div>
        )}
        <div className="feature-row">
          <span>Performance</span>
          <span>Accessibility</span>
          <span>SEO</span>
          <span>Security</span>
          <span>Broken links</span>
          <span>Design review</span>
          <span>PDF export</span>
        </div>
      </section>

      <section className="card">
        <div className="section-head">
          <h2>Recent audits</h2>
          <button
            className="btn btn-sm"
            disabled={selected.length < 2}
            onClick={() => navigate(`/compare?ids=${selected.join(',')}`)}
          >
            Compare selected ({selected.length})
          </button>
        </div>
        {listError && (
          <div className="error-box" role="alert" style={{ marginBottom: 12 }}>
            {listError}
          </div>
        )}
        {audits === null && !listError && <p className="empty">Loading…</p>}
        {audits?.length === 0 && <p className="empty">No audits yet. Run your first one above.</p>}
        {audits && audits.length > 0 && (
          <ul className="audit-list">
            {audits.map((audit) => (
              <li className="audit-row" key={audit.id}>
                <input
                  type="checkbox"
                  aria-label={`Select ${hostname(audit.url)} for comparison`}
                  checked={selected.includes(audit.id)}
                  disabled={audit.status !== 'done' || (!selected.includes(audit.id) && selected.length >= 4)}
                  onChange={() => toggle(audit.id)}
                />
                <ScoreChip score={audit.status === 'done' ? audit.overall_score : null} />
                <div style={{ minWidth: 0 }}>
                  <Link className="url" to={`/audits/${audit.id}`}>
                    {hostname(audit.final_url ?? audit.url)}
                  </Link>
                  <span className="meta">
                    {audit.status === 'failed'
                      ? `Failed: ${audit.error}`
                      : audit.status === 'done'
                        ? timeAgo(audit.created_at)
                        : (audit.progress ?? 'Running…')}
                  </span>
                </div>
                <span className="meta hide-sm">#{audit.id}</span>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => (confirming === audit.id ? remove(audit.id) : setConfirming(audit.id))}
                  onBlur={() => setConfirming((c) => (c === audit.id ? null : c))}
                  aria-label={
                    confirming === audit.id
                      ? `Confirm deleting audit of ${hostname(audit.url)}`
                      : `Delete audit of ${hostname(audit.url)}`
                  }
                  style={confirming === audit.id ? { color: 'var(--critical-ink)' } : undefined}
                >
                  {confirming === audit.id ? 'Confirm?' : 'Delete'}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  )
}
