import type { CategoryKey, Severity } from '../api'

export const CATEGORY_LABELS: Record<CategoryKey, string> = {
  performance: 'Performance',
  accessibility: 'Accessibility',
  seo: 'SEO',
  best_practices: 'Best practices',
  design: 'Design & UX',
  links: 'Links',
}

export const CATEGORY_KEYS = Object.keys(CATEGORY_LABELS) as CategoryKey[]

export const CATEGORY_BLURBS: Record<CategoryKey, string> = {
  performance: 'How fast the page loads and how heavy it is.',
  accessibility: 'Whether people with disabilities can use the site.',
  seo: 'How well search engines can find and present the page.',
  best_practices: 'Security headers and modern web standards.',
  design: 'Mobile-friendliness, typography, trust signals and conversion.',
  links: 'Broken links and missing files.',
}

export const SEVERITIES: Severity[] = ['critical', 'serious', 'moderate', 'minor']

export type Band = 'good' | 'average' | 'poor'

export function band(score: number): Band {
  if (score >= 90) return 'good'
  if (score >= 50) return 'average'
  return 'poor'
}

export const BAND_LABELS: Record<Band, string> = {
  good: 'Good',
  average: 'Needs work',
  poor: 'Poor',
}

export function formatBytes(bytes: number): string {
  bytes = Math.round(bytes)
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function plural(n: number, word: string): string {
  return `${n.toLocaleString()} ${word}${n === 1 ? '' : 's'}`
}

export function formatMs(ms: number): string {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(2)} s`
}

export function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

/** Hostnames for a set of audits, with "#id" added when the same site appears more than once. */
export function siteLabels(rows: { id: number; url: string }[]): string[] {
  const names = rows.map((r) => hostname(r.url))
  return names.map((name, i) => (names.filter((n) => n === name).length > 1 ? `${name} #${rows[i].id}` : name))
}

export function timeAgo(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const units: [number, string][] = [[60, 'minute'], [3600, 'hour'], [86400, 'day'], [604800, 'week']]
  let result = ''
  for (const [size, name] of units) {
    if (seconds >= size) {
      const n = Math.floor(seconds / size)
      result = `${n} ${name}${n === 1 ? '' : 's'} ago`
    }
  }
  return result
}
