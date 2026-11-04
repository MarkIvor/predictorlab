import { useEffect, useState } from 'react'
import { getSchema, predictApi, type ModelOut, type Prediction } from '../../api/endpoints'
import { fmtShort } from '../../design/components'

type Prop = { type: string; enum?: string[]; format?: string; example?: unknown }

export default function PredictTab({ model }: { model: ModelOut }) {
  const [schema, setSchema] = useState<Record<string, Prop> | null>(null)
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [result, setResult] = useState<Prediction | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getSchema(model.id).then((s) => {
      setSchema(s.input_schema.properties as Record<string, Prop>)
      setValues(s.example || {})
    })
  }, [model.id])

  const predict = async () => {
    setBusy(true)
    setError('')
    setResult(null)
    try {
      const r = await predictApi(model.id, [values], ['reasons'])
      setResult(r.predictions[0])
      setWarnings(r.warnings || [])
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  if (!schema) return <p className="muted">Загрузка схемы…</p>

  const entries = Object.entries(schema)
  const half = Math.ceil(entries.length / 2)
  const leftCols = entries.slice(0, half)
  const rightCols = entries.slice(half)

  const renderField = ([k, p]: [string, Prop]) => (
    <div className="field" key={k}>
      <label>{k}</label>
      {p.enum ? (
        <select value={String(values[k] ?? '')} onChange={(e) => setValues({ ...values, [k]: e.target.value })} style={{ width: '100%' }}>
          {p.enum.map((v) => <option key={v} value={v}>{v}</option>)}
        </select>
      ) : p.type === 'boolean' ? (
        <select value={String(values[k] ?? '')} onChange={(e) => setValues({ ...values, [k]: e.target.value })} style={{ width: '100%' }}>
          {['true', 'false'].map((v) => <option key={v} value={v}>{v}</option>)}
        </select>
      ) : (
        <input
          value={String(values[k] ?? '')}
          onChange={(e) => setValues({ ...values, [k]: p.type === 'number' ? Number(e.target.value) : e.target.value })}
          style={{ width: '100%' }}
        />
      )}
    </div>
  )

  return (
    <div className="bento-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(380px, 1fr))' }}>
      <div className="tile" style={{ gridColumn: 'span 1' }}>
        <span className="tile-label">ОДИНОЧНЫЙ ПРОГНОЗ</span>
        <p className="muted" style={{ fontSize: 13, marginTop: 8, marginBottom: 16 }}>
          Заполните признаки объекта. Пропуски допустимы — модель умеет их обрабатывать.
        </p>
        <div className="form-row">
          {leftCols.map(renderField)}
        </div>
        <div className="form-row">
          {rightCols.map(renderField)}
        </div>
        {error && <p style={{ color: 'var(--danger)', fontSize: 13, marginBottom: 12 }}>{error}</p>}
        <button className="btn btn-ink" onClick={predict} disabled={busy} style={{ width: '100%', padding: '12px 0', fontSize: 14 }}>
          {busy ? 'СЧИТАЮ…' : 'ПРЕДСКАЗАТЬ'}
        </button>
      </div>

      <div style={{ gridColumn: 'span 1', display: 'grid', gap: 12 }}>
        {result && (
          <div className="tile">
            <span className="tile-label">РЕЗУЛЬТАТ</span>
            <div style={{ marginTop: 16 }}>
              <span className="hero-digit-sm">
                {result.probability !== undefined ? fmtShort(result.probability * 100, 1) + '%' : fmtShort(result.prediction)}
              </span>
              <span className="denominator" style={{ marginLeft: 8 }}>
                {result.probability !== undefined ? 'ВЕРОЯТНОСТЬ' : 'ПРОГНОЗ'}
              </span>
            </div>
            <div style={{ marginTop: 16, fontSize: 14, lineHeight: 1.7 }}>
              {result.label !== undefined && (
                <div><b>Класс:</b> {result.label} · решение: {result.decision ? 'ДА' : 'НЕТ'} (порог {result.threshold})</div>
              )}
              {result.interval_low !== undefined && (
                <div><b>90% интервал:</b> [{fmtShort(result.interval_low, 2)}; {fmtShort(result.interval_high, 2)}]</div>
              )}
              {result.conformal && (
                <div><b>Конформальное множество:</b> {result.conformal.prediction_set.join(' | ')}</div>
              )}
              <div className="muted" style={{ marginTop: 8 }}>
                {result.out_of_distribution ? '⚠ OOD: объект вне распределения' : 'В пределах распределения'}
              </div>
            </div>
            {(result.top_reasons || []).length > 0 && (
              <div style={{ marginTop: 20 }}>
                <span className="tile-label" style={{ display: 'block', marginBottom: 8 }}>ПРИЧИНЫ</span>
                {(result.top_reasons || []).map((r, i) => (
                  <div className="reason" key={i}>
                    <span>{r.text || `${r.feature} = ${String(r.value)}`}</span>
                    <span className={r.impact >= 0 ? 'impact-up' : 'impact-down'}>
                      {r.impact >= 0 ? '+' : ''}{fmtShort(r.impact * 100, 1)} п.п.
                    </span>
                  </div>
                ))}
              </div>
            )}
            {warnings.map((w, i) => <p key={i} className="muted" style={{ fontSize: 12, marginTop: 8 }}>{w}</p>)}
          </div>
        )}
      </div>
    </div>
  )
}
