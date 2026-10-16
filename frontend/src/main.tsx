import { StrictMode, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import './index.css'
import { Home } from './pages/Home'

// Chart-heavy pages are split out so the landing page loads fast.
const ReportPage = lazy(() => import('./pages/Report').then((m) => ({ default: m.ReportPage })))
const Compare = lazy(() => import('./pages/Compare').then((m) => ({ default: m.Compare })))

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="audits/:id" element={<ReportPage />} />
          <Route path="compare" element={<Compare />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
