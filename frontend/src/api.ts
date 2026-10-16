export type Severity = 'critical' | 'serious' | 'moderate' | 'minor'
export type CategoryKey = 'performance' | 'accessibility' | 'seo' | 'best_practices' | 'design' | 'links'
export type AuditStatus = 'queued' | 'running' | 'done' | 'failed'
export type Scores = Record<CategoryKey | 'overall', number>

export interface Issue {
  id: string
  severity: Severity
  title: string
  description: string
  recommendation: string
  count: number
  examples: string[]
}

export interface Category {
  score: number
  issues: Issue[]
  passed: string[]
}

export interface LinkItem {
  url: string
  status: number | null
  state: 'ok' | 'redirect' | 'blocked' | 'broken'
  internal: boolean
  error: string | null
  final_url: string | null
}

export interface Report {
  requested_url: string
  final_url: string
  fetched_at: string
  status_code: number
  page: {
    title: string | null
    description: string | null
    server: string | null
    truncated: boolean
    redirects: string[]
  }
  scores: Scores
  metrics: {
    ttfb_ms: number
    load_ms: number
    html_bytes: number
    page_weight_kb: number
    request_count: number
    dom_elements: number
    redirects: number
    unknown_sizes: number
    breakdown: { kind: string; count: number; bytes: number }[]
    largest_resources: { url: string; kind: string; bytes: number }[]
  }
  links: {
    found: number
    checked: number
    ok: number
    redirect: number
    broken: number
    blocked: number
    internal: number
    external: number
    broken_resources: { url: string; kind: string; status: number | null; error: string | null }[]
    items: LinkItem[]
  }
  design: {
    fonts: string[]
    colors: string[]
    headings: { level: number; text: string }[]
    images: number
    word_count: number
  }
  categories: Record<CategoryKey, Category>
  issue_counts: Record<Severity, number>
  pagespeed: {
    strategy: string
    error?: string | null
    categories: Record<string, number>
    metrics: { id: string; label: string; value: string | null; score: number | null }[]
  } | null
}

export interface AuditSummary {
  id: number
  url: string
  final_url: string | null
  status: AuditStatus
  progress: string | null
  error: string | null
  overall_score: number | null
  scores: Scores | null
  created_at: string
  completed_at: string | null
}

export interface AuditDetail extends AuditSummary {
  report: Report | null
}

export interface CompareRow {
  id: number
  url: string
  created_at: string
  scores: Scores
  metrics: Record<'ttfb_ms' | 'load_ms' | 'page_weight_kb' | 'request_count' | 'dom_elements' | 'broken_links', number>
  issue_counts: Record<Severity, number>
}

const SERVER_DOWN = "Can't reach the Site Auditor server. Make sure the backend is running, then try again."

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new Error(SERVER_DOWN)
  }
  if (!response.ok) {
    let message = `Something went wrong on the server (HTTP ${response.status}).`
    let detail: unknown
    try {
      detail = (await response.json()).detail
    } catch {
      // A non-JSON 5xx means the dev proxy couldn't reach the backend at all.
      if (response.status >= 500) message = SERVER_DOWN
    }
    if (typeof detail === 'string') message = detail
    else if (Array.isArray(detail) && detail[0]?.msg) message = 'Please enter a valid website URL.'
    throw new Error(message)
  }
  return (response.status === 204 ? undefined : await response.json()) as T
}

export const api = {
  createAudit: (url: string) =>
    request<AuditSummary>('/audits', { method: 'POST', body: JSON.stringify({ url }) }),
  listAudits: () => request<AuditSummary[]>('/audits'),
  getAudit: (id: number) => request<AuditDetail>(`/audits/${id}`),
  deleteAudit: (id: number) => request<void>(`/audits/${id}`, { method: 'DELETE' }),
  compare: (ids: number[]) => request<CompareRow[]>(`/compare?ids=${ids.join(',')}`),
  pdfUrl: (id: number) => `/api/audits/${id}/pdf`,
}
