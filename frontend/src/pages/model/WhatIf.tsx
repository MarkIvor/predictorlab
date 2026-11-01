import { useEffect, useMemo, useRef, useState } from 'react'
import { getSchema, whatifApi, type ModelOut, type Prediction } from '../../api/endpoints'
import { WhatIfSlider, fmtShort } from '../../design/components'

type Prop = { type: string; enum?: string[]; example?: unknown }

export default function WhatIf({ model }: { model: ModelOut }) {
  const [schema, setSchema] = useState<Record<string, Prop> | null>(null)
  const [base, setBase] = useState<Record<string, unknown>>({})
  const [changes, setChanges] = useState<Record<string, unknown>>({})
  const [before, setBefore] = useState<Prediction | null>(null)
  const [after, setAfter] = useState<Prediction | null>(null)
  const [busy, setBusy] = useState(false)
  const [immutable, setImmutable] = useState<Record<string, boolean>>({})
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const actionable: Record<string, any> = (model.actionable || {}) as Record<string, any>

  useEffect(() => {
    getSchema(model.id).then((s) => {
      setSchema(s.input_schema.properties as Record<string, Prop>)
      setBase(s.example || {})
      setChanges({})
    })
    const flags: Record<string, boolean> = {}
    for (const [k, v] of Object.entries(actionable)) {
      if (v && (v as Record<string, unknown>).immutable) flags[k] = true
    }
    setImmutable(flags)
  }, [model.id])

  const run = (data: Record<string, unknown>, chg: Record<string, unknown>) => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      setBusy(true)
      try {
        const r = await whatifApi(model.id, data, chg)
        setBefore(r.before)
        setAfter(r.after)
      } finally { setBusy(false) }
    }, 150)
  }

  useEffect(() => {
    if (schema && Object.keys(base).length) run(base, changes)
  }, [schema, base])

  const setValue = (key: string, value: unknown) => {
    const next = { ...changes, [key]: value }
    setChanges(next)
    run(base, next)
  }

  const numericEntries = useMemo(() => Object.entries(schema || {}).filter(([, p]) => p.type === 'number'), [schema])
  const catEntries = useMemo(() => Object.entries(schema || {}).filter(([, p]) => p.type === 'string'), [schema])

  if (!schema) return <p className="muted">Загрузка схемы…</p>
  if (Object.keys(schema).length === 0) return <div className="tile"><p className="muted">Схема модели недоступна</p></div>

  const current = (k: string) => changes[k] !== undefined ? changes[k] : base[k]

  return (
    <div className="bento-grid">
      <div className="tile" style={{ gridColumn: 'span 7' }}>
        <span className="tile-label">ПРИЗНАКИ ОБЪЕКТА (ТИПИЧНЫЙ ОБЪЕКТ — ИЗ ПРИМЕРА МОДЕЛИ)</span>
        <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>Неизменяемые признаки заблокированы (разметка на вкладке ACTIONS).</p>
        {numericEntries.map(([k, p]) => {
          const ex = Number(base[k] ?? (p as { example?: number }).example ?? 0)
          const cfg = (actionable[k] || {}) as Record<string, number | string>
          const min = typeof cfg.min === 'number' ? cfg.min : Math.min(0, ex * 2 - 0.1)
          const max = typeof cfg.max === 'number' ? cfg.max : Math.max(ex * 2 + 0.1, ex + 1)
          const step = (max - min) > 20 ? 1 : (max - min) / 100
          return (
            <WhatIfSlider
              key={k} label={k} value={Number(current(k) ?? ex)} min={min} max={max} step={step}
              disabled={immutable[k]} onChange={(v) => setValue(k, v)}
            />
          )
        })}
        {catEntries.map(([k, p]) => (
          <div className="field" key={k}>
            <label>{k}</label>
            <select value={String(current(k) ?? '')} disabled={immutable[k]} onChange={(e) => setValue(k, e.target.value)}>
              {(p.enum || [String(current(k) ?? '')]).map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
        ))}
      </div>
      <div style={{ gridColumn: 'span 5', display: 'grid', gap: 8 }}>
        <div className="tile">
          <span className="tile-label">СЕЙЧАС</span>
          <ResultBody p={before} />
        </div>
        <div className="tile" style={{ outline: '1px solid var(--accent)', outlineOffset: -1 }}>
          <span className="tile-label">ПОСЛЕ ИЗМЕНЕНИЙ {busy ? '· ПЕРЕСЧЁТ…' : ''}</span>
          <ResultBody p={after} />
        </div>
      </div>
      <div className="tile" style={{ gridColumn: 'span 12', background: 'var(--surface-2)' }}>
        <span className="tile-label">ВНИМАНИЕ</span>
        <p style={{ margin: '6px 0 0', fontSize: 12 }}>Это ответ модели на изменение признака, а не доказанный причинный эффект.</p>
      </div>
    </div>
  )
}

function ResultBody({ p }: { p: Prediction | null }) {
  if (!p) return <p className="muted" style={{ marginTop: 10 }}>…</p>
  const hero = p.probability !== undefined ? fmtShort(p.probability * 100, 1) + '%' : p.prediction !== undefined ? fmtShort(p.prediction) : '—'
  return (
    <>
      <div className="hero-digit-sm" style={{ marginTop: 12 }}>{hero}</div>
      <div style={{ marginTop: 10, fontSize: 12 }}>
        {p.label !== undefined && <div>Класс: <b>{p.label}</b> (порог {p.threshold ?? 0.5})</div>}
        {p.interval_low !== undefined && <div>Интервал 90%: [{fmtShort(p.interval_low, 2)}; {fmtShort(p.interval_high, 2)}]</div>}
        {p.conformal?.prediction_set && <div>Множество: {p.conformal.prediction_set.join(' | ')}</div>}
        <div className="muted">{p.out_of_distribution ? '⚠ Объект вне распределения обучающих данных' : 'В пределах распределения'}</div>
      </div>
    </>
  )
}

