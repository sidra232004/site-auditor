import { Suspense } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { setThemeChoice, useTheme } from '../lib/theme'

export function Layout() {
  const { isDark } = useTheme()
  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <NavLink to="/" className="brand" aria-label="Site Auditor home">
            <img src="/favicon.svg" width={26} height={26} alt="" />
            <span className="brand-name">Site Auditor</span>
          </NavLink>
          <nav className="nav" aria-label="Main">
            <NavLink to="/" end>
              New audit
            </NavLink>
            <NavLink to="/compare">Compare</NavLink>
          </nav>
          <button
            type="button"
            className="btn btn-ghost btn-sm theme-toggle"
            onClick={() => setThemeChoice(isDark ? 'light' : 'dark')}
            aria-label={`Switch to ${isDark ? 'light' : 'dark'} theme`}
          >
            {isDark ? '☀' : '☾'}
          </button>
        </div>
      </header>
      <main className="container">
        <Suspense fallback={<div className="progress-card"><div className="spinner" /></div>}>
          <Outlet />
        </Suspense>
      </main>
    </>
  )
}
