import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { ArrowUpRight } from 'lucide-react'
import { Bar, BarChart as RBarChart, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis } from 'recharts'

export function fmtShort(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  const abs = Math.abs(n)
  if (abs >= 1_000_000_000) return (n / 1_000_000_000).toFixed(digits) + 'B'
  if (abs >= 1_000_000) return (n / 1_000_000).toFixed(digits) + 'M'
  if (abs >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  if (abs >= 100) return n.toFixed(0)
  return Number.isInteger(n) ? String(n) : n.toFixed(Math.max(digits, 2))
}

export function fmtRub(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return fmtShort(n) + ' ₽'
}

export function CountUp({ value, className, digits }: { value: number; className?: string; digits?: number }) {
  const [shown, setShown] = useState(value)
  const from = useRef(value)
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setShown(value)
      return
    }
    const start = performance.now()
    const initial = from.current
    let raf = 0
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 400)
      const eased = 1 - Math.pow(1 - t, 3)
      setShown(initial + (value - initial) * eased)
      if (t < 1) raf = requestAnimationFrame(tick)
      else from.current = value
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value])
  const text = digits !== undefined ? shown.toFixed(digits) : fmtShort(shown)
  return <span className={className}>{text}</span>
}

export function StatTile({ label, value, denominator, total, note, children, onMenu, menu }: {
  label: string
  value: ReactNode
  denominator?: string
  total?: string
  note?: string
  children?: ReactNode
  onMenu?: () => void
  menu?: string
}) {
  return (
    <div className="tile stat-tile">
      <div className="stat-head">
        <span className="tile-label">{label}</span>
        {onMenu && <button className="kebab" onClick={onMenu} title={menu}>⋮</button>}
      </div>
      <div className="stat-value">
        <span className="hero-digit-sm">{value}</span>
        {denominator && <span className="denominator">/ {denominator}</span>}
      </div>
      {children}
      {total && (
        <div className="stat-total">
          <div className="stat-total-line" />
          <span className="muted">{total}</span>
        </div>
      )}
      {note && <div className="stat-note muted">{note}</div>}
    </div>
  )
}

export function AccentTile({ title, description, children, dots, active, geometry = 0 }: {
  title: string
  description?: string
  children?: ReactNode
  dots?: number
  active?: number
  geometry?: number
}) {
  return (
    <div className="tile accent-tile">
      <svg className="accent-geometry" viewBox="0 0 200 120" preserveAspectRatio="none">
        {geometry === 0 && (
          <>
            <path d="M -20 120 Q 60 40 130 100 T 260 60" fill="none" stroke="var(--ink)" strokeOpacity="0.35" strokeWidth="1" />
            <circle cx="150" cy="38" r="30" fill="none" stroke="var(--ink)" strokeOpacity="0.35" strokeWidth="1" />
            <line x1="0" y1="95" x2="200" y2="95" stroke="var(--ink)" strokeOpacity="0.35" strokeWidth="1" />
          </>
        )}
        {geometry === 1 && (
          <>
            <path d="M -10 10 L 60 10 L 60 50 L 130 50" fill="none" stroke="var(--ink)" strokeOpacity="0.35" strokeWidth="1" />
            <circle cx="160" cy="70" r="18" fill="none" stroke="var(--ink)" strokeOpacity="0.35" strokeWidth="1" />
          </>
        )}
      </svg>
      <h2 className="accent-title">{title}</h2>
      {description && <p className="accent-desc">{description}</p>}
      {children}
      {dots !== undefined && (
        <div className="dots">
          {Array.from({ length: dots }).map((_, i) => (
            <span key={i} className={i === (active ?? 0) ? 'dot dot-active' : 'dot'} />
          ))}
        </div>
      )}
    </div>
  )
}

export function CTATile({ title, subtitle, count, total, onClick }: {
  title: string
  subtitle?: string
  count?: string
  total?: string
  onClick: () => void
}) {
  return (
    <button className="tile cta-tile" onClick={onClick}>
      <div className="cta-top">
        <h2 className="cta-title">{title}</h2>
        <span className="cta-arrow"><ArrowUpRight size={15} /></span>
      </div>
      {subtitle && <p className="cta-sub">{subtitle}</p>}
      {count && total && <div className="cta-count">{count} / {total}</div>}
    </button>
  )
}

export function ArrowButton({ onClick, title }: { onClick: () => void; title?: string }) {
  return (
    <button className="arrow-button" onClick={onClick} title={title}>
      <ArrowUpRight size={14} />
    </button>
  )
}

const tooltipStyle = {
  contentStyle: { background: 'var(--surface-2)', border: '1px solid var(--line)', borderRadius: 'var(--radius)', fontFamily: 'var(--font)', fontSize: 12, color: 'var(--ink)' },
  labelStyle: { color: 'var(--muted)' },
  itemStyle: { color: 'var(--ink)' },
}

export function BarChart({ data, height = 180, activeIndex, valueFormat }: {
  data: { label: string; value: number; hint?: string }[]
  height?: number
  activeIndex?: number
  valueFormat?: (v: number) => string
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RBarChart data={data} margin={{ top: 18, right: 4, left: 4, bottom: 0 }}>
        <XAxis dataKey="label" tick={{ fill: 'var(--muted)', fontSize: 10, fontFamily: 'var(--font)' }} axisLine={false} tickLine={false} />
        <Tooltip
          {...tooltipStyle}
          cursor={{ fill: 'var(--surface-2)' }}
          formatter={(v) => [valueFormat ? valueFormat(Number(v)) : fmtShort(Number(v)), '']}
          labelFormatter={(l, payload) => (payload?.[0]?.payload as { hint?: string })?.hint || String(l)}
        />
        <Bar dataKey="value" isAnimationActive={false}>
          {data.map((_, i) => (
            <Cell key={i} fill={i === activeIndex ? 'var(--accent)' : 'var(--stone)'} />
          ))}
        </Bar>
      </RBarChart>
    </ResponsiveContainer>
  )
}

export function CurveChart({ data, xKey, yKey, height = 220, markerX }: {
  data: Record<string, number>[]
  xKey: string
  yKey: string
  height?: number
  markerX?: number
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <XAxis dataKey={xKey} tick={{ fill: 'var(--muted)', fontSize: 10, fontFamily: 'var(--font)' }} axisLine={false} tickLine={false} />
        <Tooltip {...tooltipStyle} cursor={{ stroke: 'var(--line)' }} />
        <Line type="monotone" dataKey={yKey} stroke="var(--stone)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
        {markerX !== undefined && (
          <Line dataKey="__marker" data={data.map((d) => ({ ...d, __marker: Math.abs(d[yKey as keyof typeof d] as number) > 1e12 ? null : null }))} stroke="none" />
        )}
      </LineChart>
    </ResponsiveContainer>
  )
}

export function RingGauge({ value, max = 1, label, size = 130, format }: {
  value: number
  max?: number
  label: string
  size?: number
  format?: (v: number) => string
}) {
  const pct = Math.max(0, Math.min(1, value / max))
  const stroke = 3
  const r = (size - stroke * 2) / 2
  const c = 2 * Math.PI * r
  return (
    <div className="ring-gauge" style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-2)" strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--accent)" strokeWidth={stroke}
          strokeDasharray={`${c * pct} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} strokeLinecap="butt"
        />
      </svg>
      <div className="ring-center">
        <span className="ring-value">{format ? format(value) : fmtShort(value)}</span>
        <span className="ring-label">{label}</span>
      </div>
    </div>
  )
}

export function ProgressBar({ value }: { value: number }) {
  return (
    <div className="progress-track">
      <div className="progress-fill" style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
    </div>
  )
}

export function PeriodToggle({ periods, active, onSelect }: {
  periods: string[]
  active: string
  onSelect: (p: string) => void
}) {
  return (
    <div className="period-toggle">
      {periods.map((p) => (
        <button key={p} className={p === active ? 'period active' : 'period'} onClick={() => onSelect(p)}>{p}</button>
      ))}
    </div>
  )
}

export function DataTable<T extends Record<string, unknown>>({ columns, rows, onRow }: {
  columns: { key: string; label: string; align?: 'left' | 'right'; format?: (v: unknown, row: T) => ReactNode }[]
  rows: T[]
  onRow?: (row: T) => void
}) {
  return (
    <div className="data-table">
      <table>
        <thead>
          <tr>{columns.map((c) => <th key={c.key} style={{ textAlign: c.align === 'right' ? 'right' : 'left' }}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} onClick={onRow ? () => onRow(row) : undefined} className={onRow ? 'clickable' : ''}>
              {columns.map((c) => (
                <td key={c.key} style={{ textAlign: c.align === 'right' ? 'right' : 'left' }}>
                  {c.format ? c.format(row[c.key], row) : (row[c.key] as ReactNode) ?? '—'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function VerdictBadge({ verdict }: { verdict: string }) {
  const cls = verdict === 'OK' ? 'ok' : verdict === 'WARN' ? 'warn' : 'danger'
  return <span className={`verdict ${cls}`}>{verdict}</span>
}

export function EmptyState({ label, text, actionLabel, onAction }: {
  label: string
  text?: string
  actionLabel?: string
  onAction?: () => void
}) {
  return (
    <div className="tile empty-state">
      <span className="tile-label">{label}</span>
      {text && <p className="muted" style={{ margin: '12px 0' }}>{text}</p>}
      {actionLabel && onAction && <div style={{ display: 'flex', justifyContent: 'flex-end' }}><ArrowButton onClick={onAction} title={actionLabel} /></div>}
    </div>
  )
}

export function ErrorTile({ label, text, actionLabel, onAction }: {
  label: string
  text: string
  actionLabel?: string
  onAction?: () => void
}) {
  return (
    <div className="tile" style={{ borderColor: 'var(--danger)', borderWidth: 1, borderStyle: 'solid' }}>
      <span className="tile-label" style={{ color: 'var(--danger)' }}>{label}</span>
      <p style={{ margin: '12px 0' }}>{text}</p>
      {actionLabel && onAction && <button className="btn btn-accent" onClick={onAction}>{actionLabel}</button>}
    </div>
  )
}

export function WhatIfSlider({ label, value, min, max, step, onChange, disabled }: {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
  disabled?: boolean
}) {
  const filled = ((value - min) / Math.max(max - min, 1e-9)) * 100
  return (
    <div className={`whatif-slider ${disabled ? 'disabled' : ''}`}>
      <div className="whatif-slider-head">
        <span>{label}</span>
        <span className="muted">{value}</span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value} disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ '--filled': `${filled}%` } as CSSProperties}
      />
    </div>
  )
}
