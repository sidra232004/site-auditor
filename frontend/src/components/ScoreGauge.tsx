import { BAND_LABELS, band } from '../lib/format'
import { useTheme } from '../lib/theme'

interface Props {
  score: number
  label?: string
  size?: number
  onClick?: () => void
  pressed?: boolean
}

export function ScoreGauge({ score, label, size = 96, onClick, pressed }: Props) {
  const { colors } = useTheme()
  const b = band(score)
  const stroke = Math.max(6, size / 12)
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const color = b === 'good' ? colors.good : b === 'average' ? colors.warning : colors.critical

  const content = (
    <>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={colors.grid} strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${(score / 100) * circumference} ${circumference}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text
          x="50%"
          y="50%"
          dominantBaseline="central"
          textAnchor="middle"
          className="gauge-value"
          style={{ fontSize: size * 0.3 }}
        >
          {score}
        </text>
      </svg>
      {label && <span className="gauge-label">{label}</span>}
      <span className={`gauge-band ${b}`}>{BAND_LABELS[b]}</span>
      <span className="sr-only">{`${label ?? 'Score'}: ${score} out of 100, ${BAND_LABELS[b]}`}</span>
    </>
  )

  if (onClick) {
    return (
      <button type="button" className="gauge" onClick={onClick} aria-pressed={pressed}>
        {content}
      </button>
    )
  }
  return <div className="gauge">{content}</div>
}

export function ScoreChip({ score }: { score: number | null }) {
  if (score === null) return <span className="chip pending">–</span>
  const b = band(score)
  return (
    <span className={`chip ${b}`} title={BAND_LABELS[b]}>
      {Math.round(score)}
    </span>
  )
}
