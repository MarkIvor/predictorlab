import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { publicInfo, publicPredict, type Prediction } from '../api/endpoints'
import { fmtShort } from '../design/components'

type Prop = { type: string; enum?: string[]; example?: unknown }

export default function PublicPage() {
  const { slug } = useParams()
  const [info, setInfo] = useState<{ name: string; has_password: boolean; input_schema: { properties: Record<string, Prop> }; example: Record<string, unknown> } | null>(null)
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [password, setPassword] = useState('')
  const [result, setResult] = useState<Prediction | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    publicInfo(slug!).then((i) => {
      setInfo({ name: i.name, has_password: i.has_password, input_schema: { properties: i.input_schema.properties as Record<string, Prop> }, example: i.example })
      setValues(i.example || {})
    }).catch(() => setError('Страница не найдена'))
  }, [slug])

  const submit = async () => {
    setBusy(true)
    setError('')
    setResult(null)
    try {
      const r = await publicPredict(slug!, values, password || undefined)
      setResult(r.prediction)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally { setBusy(false) }
  }

  return (
    <div className="page" style={{ maxWidth: 760, margin: '0 auto' }}>
      <h1 className="brand" style={{ margin: '16px 0' }}>{info?.name || 'PREDICTORLAB'}</h1>
      {!info && <div className="tile"><p>{error || 'Загрузка…'}</p></div>}
      {info && (
        <div className="bento-grid">
          <div className="tile" style={{ gridColumn: 'span 6' }}>
            <span className="tile-label">ФОРМА ПРОГНОЗА</span>
            <div style={{ marginTop: 12 }}>
              {Object.entries(info.input_schema.properties).map(([k, p]) => (
                <div className="field" key={k}>
                  <label>{k}</label>
                  {p.enum ? (
                    <select value={String(values[k] ?? '')} onChange={(e) => setValues({ ...values, [k]: e.target.value })}>
                      {p.enum.map((v) => <option key={v} value={v}>{v}</option>)}
                    </select>
                  ) : (
                    <input value={String(values[k] ?? '')}
                      onChange={(e) => setValues({ ...values, [k]: p.type === 'number' ? Number(e.target.value) : e.target.value })} />
                  )}
                </div>
              ))}
              {info.has_password && (
                <div className="field"><label>Пароль страницы</label><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
              )}
              {error && <p style={{ color: 'var(--danger)', fontSize: 12 }}>{error}</p>}
              <button className="btn btn-ink" style={{ width: '100%' }} onClick={submit} disabled={busy}>{busy ? '…' : 'ПРЕДСКАЗАТЬ'}</button>
            </div>
          </div>
          <div className="tile" style={{ gridColumn: 'span 6' }}>
            <span className="tile-label">РЕЗУЛЬТАТ</span>
            {result ? (
              <>
                <div className="hero-digit" style={{ marginTop: 12 }}>
                  {result.probability !== undefined ? fmtShort(result.probability * 100, 1) + '%' : fmtShort(result.prediction)}
                </div>
                <div style={{ marginTop: 12, fontSize: 12, lineHeight: 1.7 }}>
                  {result.label !== undefined && <div>Класс: <b>{result.label}</b></div>}
                  {result.interval_low !== undefined && <div>90% интервал: [{fmtShort(result.interval_low, 2)}; {fmtShort(result.interval_high, 2)}]</div>}
                  {result.conformal && <div>Множество: {result.conformal.prediction_set.join(' | ')}</div>}
                  {result.out_of_distribution && <div className="muted">⚠ Объект вне распределения</div>}
                  {(result.top_reasons || []).length > 0 && (
                    <div style={{ marginTop: 10 }}>
                      {(result.top_reasons || []).slice(0, 3).map((r, i) => <div key={i} className="muted">{r.text}</div>)}
                    </div>
                  )}
                </div>
              </>
            ) : <p className="muted" style={{ marginTop: 12 }}>Заполните форму и нажмите «Предсказать»</p>}
          </div>
        </div>
      )}
      <p className="muted" style={{ fontSize: 10, marginTop: 16 }}>Powered by PredictorLab — честные интервалы, никакого волшебства.</p>
    </div>
  )
}
