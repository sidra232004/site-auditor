import type { ReactNode } from 'react'
import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import type { CategoryKey, CompareRow, Report } from '../api'
import { CATEGORY_KEYS, CATEGORY_LABELS, SEVERITIES, formatBytes, siteLabels } from '../lib/format'
import { severityColor, useTheme, type ChartTheme } from '../lib/theme'

interface TooltipRow {
  color: string
  label: string
  value: ReactNode
}

function TooltipBox({ title, rows }: { title: ReactNode; rows: TooltipRow[] }) {
  return (
    <div className="chart-tooltip">
      <div className="tt-title">{title}</div>
      {rows.map((row) => (
        <div className="tt-row" key={row.label}>
          <span className="legend-swatch" style={{ background: row.color }} />
          {row.label}
          <b>{row.value}</b>
        </div>
      ))}
    </div>
  )
}

export function Legend({ items }: { items: { color: string; label: string }[] }) {
  return (
    <div className="legend">
      {items.map((item) => (
        <span className="legend-item" key={item.label}>
          <span className="legend-swatch" style={{ background: item.color }} />
          {item.label}
        </span>
      ))}
    </div>
  )
}

const axisProps = (colors: ChartTheme) => ({
  tick: { fill: colors.muted, fontSize: 12 },
  axisLine: { stroke: colors.axis },
  tickLine: false,
})

/** Stacked bars: how many issues of each severity each category has. */
export function IssuesByCategoryChart({ report }: { report: Report }) {
  const { colors } = useTheme()
  const data = CATEGORY_KEYS.map((key) => {
    const row: Record<string, string | number> = { name: CATEGORY_LABELS[key] }
    for (const s of SEVERITIES) row[s] = report.categories[key].issues.filter((i) => i.severity === s).length
    return row
  })
  return (
    <>
      <Legend items={SEVERITIES.map((s) => ({ color: severityColor(colors, s), label: s[0].toUpperCase() + s.slice(1) }))} />
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }} barCategoryGap="28%">
          <CartesianGrid horizontal={false} stroke={colors.grid} />
          <XAxis type="number" allowDecimals={false} {...axisProps(colors)} />
          <YAxis type="category" dataKey="name" width={104} {...axisProps(colors)} tick={{ fill: colors.ink2, fontSize: 12.5 }} />
          <Tooltip
            cursor={{ fill: colors.grid, opacity: 0.5 }}
            content={({ active, payload, label }) =>
              active && payload?.length ? (
                <TooltipBox
                  title={label}
                  rows={SEVERITIES.map((s) => ({
                    color: severityColor(colors, s),
                    label: s[0].toUpperCase() + s.slice(1),
                    value: (payload[0].payload as Record<string, number>)[s],
                  }))}
                />
              ) : null
            }
          />
          {SEVERITIES.map((s) => (
            <Bar key={s} dataKey={s} stackId="a" fill={severityColor(colors, s)} stroke={colors.surface} strokeWidth={2} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </>
  )
}

const KIND_LABELS: Record<string, string> = {
  html: 'HTML',
  script: 'JavaScript',
  stylesheet: 'CSS',
  image: 'Images',
  other: 'Media & other',
}

/** Page weight by resource type. */
export function PageWeightChart({ report }: { report: Report }) {
  const { colors } = useTheme()
  const data = report.metrics.breakdown
    .map((b) => ({ ...b, name: KIND_LABELS[b.kind] ?? b.kind, kb: Math.round(b.bytes / 102.4) / 10 }))
    .sort((a, b) => b.bytes - a.bytes)
  return (
    <ResponsiveContainer width="100%" height={Math.max(140, data.length * 44)}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 56, top: 4, bottom: 4 }} barCategoryGap="30%">
        <CartesianGrid horizontal={false} stroke={colors.grid} />
        <XAxis type="number" {...axisProps(colors)} tickFormatter={(v: number) => `${v} KB`} />
        <YAxis type="category" dataKey="name" width={104} {...axisProps(colors)} tick={{ fill: colors.ink2, fontSize: 12.5 }} />
        <Tooltip
          cursor={{ fill: colors.grid, opacity: 0.5 }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null
            const row = payload[0].payload as (typeof data)[number]
            return (
              <TooltipBox
                title={row.name}
                rows={[
                  { color: colors.series[0], label: 'Size', value: formatBytes(row.bytes) },
                  { color: 'transparent', label: 'Files', value: row.count },
                ]}
              />
            )
          }}
        />
        <Bar
          dataKey="kb"
          fill={colors.series[0]}
          radius={[0, 4, 4, 0]}
          label={{ position: 'right', fill: colors.ink2, fontSize: 12, formatter: (v: unknown) => `${v} KB` }}
        />
      </BarChart>
    </ResponsiveContainer>
  )
}

/** Grouped bars: each category's score for every compared site. */
export function CompareChart({ rows }: { rows: CompareRow[] }) {
  const { colors } = useTheme()
  const keys: (CategoryKey | 'overall')[] = ['overall', ...CATEGORY_KEYS]
  const data = keys.map((key) => {
    const row: Record<string, string | number> = { name: key === 'overall' ? 'Overall' : CATEGORY_LABELS[key] }
    rows.forEach((r) => (row[`s${r.id}`] = r.scores[key]))
    return row
  })
  const labels = siteLabels(rows)
  const series = rows.map((r, i) => ({ key: `s${r.id}`, label: labels[i], color: colors.series[i] }))
  return (
    <>
      <Legend items={series} />
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={data} margin={{ left: -12, right: 8, top: 8, bottom: 4 }} barCategoryGap="22%" barGap={2}>
          <CartesianGrid vertical={false} stroke={colors.grid} />
          <XAxis dataKey="name" {...axisProps(colors)} tick={{ fill: colors.ink2, fontSize: 12 }} interval={0} />
          <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} {...axisProps(colors)} axisLine={false} />
          <Tooltip
            cursor={{ fill: colors.grid, opacity: 0.5 }}
            content={({ active, payload, label }) =>
              active && payload?.length ? (
                <TooltipBox
                  title={label}
                  rows={series.map((s) => ({
                    color: s.color,
                    label: s.label,
                    value: (payload[0].payload as Record<string, number>)[s.key],
                  }))}
                />
              ) : null
            }
          />
          {series.map((s) => (
            <Bar key={s.key} dataKey={s.key} name={s.label} fill={s.color} radius={[4, 4, 0, 0]} maxBarSize={28} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </>
  )
}
