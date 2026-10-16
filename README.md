---
title: Site Auditor
emoji: 🔍
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
---

# Site Auditor

Enter a website URL and get an interactive report on what's wrong with it: performance, accessibility,
SEO, security, broken links and design. Every problem comes with a plain-English explanation and a fix.

**Stack:** React 19 + TypeScript + Vite + Recharts · Python + FastAPI · SQLAlchemy + SQLite · ReportLab (PDF)

## Features

- **Live URL analysis.** Fetches the page, discovers every script, stylesheet, image and link, and probes them concurrently.
- **Six scored categories (0–100)** plus a weighted overall score:
  | Category | What's checked |
  |---|---|
  | Performance | Server response time, download time, page weight, request count, DOM size, compression, render-blocking scripts, oversized images, cache headers, redirect chains |
  | Accessibility | Alt text, form labels, button and link names, page language, heading order, zoom blocking, landmarks, tabindex, iframe titles, inline color contrast (WCAG) |
  | SEO | Title and meta description, H1s, canonical URL, noindex, Open Graph tags, structured data, robots.txt, sitemap, thin content |
  | Best practices | HTTPS, HSTS, CSP, clickjacking protection, mixed content, version disclosure, doctype, vulnerable jQuery |
  | Design & UX | Mobile viewport, outdated HTML, typeface count, color palette, tiny text, walls of text, call-to-action, favicon, placeholder text, stale copyright year |
  | Links | Broken links and missing resources. Sites that block bots (403/429/999) are reported separately, not counted as broken |
- **Visual report.** Score gauges, metric meters, issues-by-severity chart, page-weight breakdown, link health, a detected font and color palette, and a heading outline.
- **Downloadable PDF audit** for clients and stakeholders.
- **Comparison dashboard.** Benchmark up to 4 sites side by side with a grouped chart and head-to-head table.
- **Optional Google Lighthouse data.** Set `PAGESPEED_API_KEY` to add real-browser Lighthouse scores and Core Web Vitals.
  Without a key this section is simply absent; Google refuses keyless requests (shared daily quota).

> **Where the scores come from:** the six category scores are calculated by Site Auditor itself:
> each starts at 100 and loses points for every issue found by automated checks of the page's HTML,
> HTTP headers and links (Performance also uses timings measured from the server). They are *not*
> Google Lighthouse scores. Lighthouse results, when enabled, are shown in their own clearly labelled section.
- Light and dark themes, responsive down to phone width.

## Running locally

**Backend** (Python 3.11+):

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

**Frontend** (Node 20+), in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to the backend.

**Tests:** `cd backend && pytest`. They run the real analyzers against HTML fixtures, test the SSRF guard, and cover the full API lifecycle including PDF generation, with no network needed.

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/audits` | Start an audit `{ "url": "example.com" }` → `202` with the audit id |
| `GET` | `/api/audits` | Recent audits (`?q=` filter, `?limit=`) |
| `GET` | `/api/audits/{id}` | Status, progress and full report (poll until `status` is `done` or `failed`) |
| `DELETE` | `/api/audits/{id}` | Delete an audit |
| `GET` | `/api/audits/{id}/pdf` | PDF report (`?inline=true` to view in the browser) |
| `GET` | `/api/compare?ids=1,2,3` | Scores and key metrics for several audits |

## Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///backend/audits.db` | SQLite file by default; PostgreSQL: `postgresql+psycopg://user:password@localhost:5432/siteauditor` |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins |
| `PAGESPEED_API_KEY` | – | Enables Google PageSpeed Insights enrichment |
| `ALLOW_PRIVATE_TARGETS` | `false` | Allow auditing localhost/private IPs (dev only) |
| `MAX_LINKS` / `MAX_RESOURCES` | `80` / `60` | How many links and files to probe per audit |
| `MAX_CONCURRENT_AUDITS` | `3` | Audits that may run at once |
| `MAX_PENDING_AUDITS` | `20` | Queued + running audits allowed before new requests get HTTP 429 |
| `AUDIT_TIMEOUT` | `120` | Seconds before a whole audit is stopped |

### Using PostgreSQL instead of SQLite

The app creates its table automatically on startup. With Docker Desktop running (PowerShell):

```powershell
docker run --name siteauditor-db -e POSTGRES_USER=siteauditor -e POSTGRES_PASSWORD=change-me `
  -e POSTGRES_DB=siteauditor -p 5432:5432 -v siteauditor-data:/var/lib/postgresql/data -d postgres:16
$env:DATABASE_URL = "postgresql+psycopg://siteauditor:change-me@localhost:5432/siteauditor"
uvicorn app.main:app --port 8000
```

If the database can't be reached, startup stops after a few seconds with a clear message (password hidden).

### Enabling Google Lighthouse

Create a free API key (Google Cloud Console → APIs & Services → enable "PageSpeed Insights API" → Credentials),
then set it only in your terminal session, never in code or git:

```powershell
$env:PAGESPEED_API_KEY = "your-key-here"
```

The key is sent to Google in a request header, not in the URL, so it never appears in logs.

## How it works

```
POST /api/audits ──► row saved (queued) ──► background task
                                              │
      fetch page (manual redirects, SSRF-checked every hop, timed)
                                              │
      parse HTML ─► discover resources + links ─► concurrent HEAD/GET probes
                                              │
      performance · accessibility · seo · best_practices · design · links
                                              │
      scores + issues + metrics ─► JSON report stored ─► UI polls & renders
```

Each analyzer returns a score, a list of issues (`critical`/`serious`/`moderate`/`minor`, each with
description, recommendation and examples), and the checks that passed. Category scores start at
100 and lose points per issue by severity. Performance blends this with metric scores interpolated
between "good" and "poor" thresholds.

**Security:** the server fetches arbitrary user-supplied URLs, so every request (including each
redirect hop) is resolved and refused if it points at a private, loopback, link-local or cloud-metadata
address. The connection then goes to that exact vetted IP (so DNS can't swap in an internal address
between the check and the request), only web ports are allowed, and HTTPS certificates are still
verified against the real hostname. Responses are size-capped, each request has a timeout, and each
whole audit has a hard deadline.

## Limitations

The audit reads HTML as served and does not execute JavaScript, so content rendered client-side
(single-page apps) is only partially analyzed, and timings are measured from the server, not a real
browser. Enable `PAGESPEED_API_KEY` for real-browser Lighthouse metrics.
