import { useEffect, useState } from 'react'
import type { Severity } from '../api'

/** Chart colors resolved in JS, because SVG attributes set by Recharts can't read CSS variables reliably. */
const LIGHT = {
  series: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300'],
  good: '#0ca30c',
  warning: '#fab219',
  serious: '#ec835a',
  critical: '#d03b3b',
  minor: '#898781',
  ink: '#0b0b0b',
  ink2: '#52514e',
  muted: '#898781',
  grid: '#e1e0d9',
  axis: '#c3c2b7',
  surface: '#fcfcfb',
}

const DARK: typeof LIGHT = {
  series: ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300'],
  good: '#0ca30c',
  warning: '#fab219',
  serious: '#ec835a',
  critical: '#d03b3b',
  minor: '#898781',
  ink: '#ffffff',
  ink2: '#c3c2b7',
  muted: '#898781',
  grid: '#2c2c2a',
  axis: '#383835',
  surface: '#1a1a19',
}

export type ChartTheme = typeof LIGHT
export function severityColor(colors: ChartTheme, severity: Severity): string {
  return { critical: colors.critical, serious: colors.serious, moderate: colors.warning, minor: colors.minor }[severity]
}

export type ThemeChoice = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'site-auditor-theme'

function readChoice(): ThemeChoice {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    if (value === 'light' || value === 'dark') return value
  } catch {
    /* storage unavailable */
  }
  return 'system'
}

function systemDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

const listeners = new Set<() => void>()
let choice: ThemeChoice = readChoice()

function apply() {
  const root = document.documentElement
  if (choice === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', choice)
  listeners.forEach((l) => l())
}

export function setThemeChoice(next: ThemeChoice) {
  choice = next
  try {
    if (next === 'system') localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, next)
  } catch {
    /* storage unavailable */
  }
  apply()
}

apply()

export function useTheme(): { isDark: boolean; choice: ThemeChoice; colors: ChartTheme } {
  const [, force] = useState(0)
  useEffect(() => {
    const rerender = () => force((n) => n + 1)
    listeners.add(rerender)
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    media.addEventListener('change', rerender)
    return () => {
      listeners.delete(rerender)
      media.removeEventListener('change', rerender)
    }
  }, [])
  const isDark = choice === 'dark' || (choice === 'system' && systemDark())
  return { isDark, choice, colors: isDark ? DARK : LIGHT }
}
