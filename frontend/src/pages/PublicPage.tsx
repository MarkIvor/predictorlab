import { useEffect, useState } from 'react'
import { Lock, Loader2, TrendingUp, ShieldCheck, Zap } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { publicInfo, publicPredict, type Prediction } from '../api/endpoints'
import { fmtShort } from '../design/components'

export default function PublicPage() {
  const { slug } = useParams()
  const [info, setInfo] = useState<{
    name: string; task_type: string; has_password: boolean
    input_schema: { properties: Record<string, Record<string, unknown>> }
    example: Record<string, unknown>
  } | null>(null)
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [password, setPassword] = useState('')
  const [needPassword, setNeedPassword] = useState(false)
  const [result, setResult] = useState<Prediction | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    publicInfo(slug!).then((i) => {
      setInfo(i)
      setValues(i.example || {})
      setNeedPassword(i.has_password)
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
    } finally {
      setBusy(false)
    }
  }

  if (!info) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <p style={{ color: 'var(--muted)', fontSize: 16 }}>{error || 'Загрузка…'}</p>
      </div>
    )
  }

  const entries = Object.entries(info.input_schema.properties)
  const half = Math.ceil(entries.length / 2)
  const leftCols = entries.slice(0, half)
  const rightCols = entries.slice(half)

  const renderField = ([k, p]: [string, Record<string, unknown>]) => (
    <div key={k} style={{ marginBottom: 16 }}>
      <label style={{
        display: 'block', fontSize: 13, textTransform: 'uppercase',
        letterSpacing: '0.04em', color: 'var(--muted)', marginBottom: 6,
      }}>
        {k}
      </label>
      {(p as { enum?: string[] }).enum ? (
        <select
          value={String(values[k] ?? '')}
          onChange={(e) => setValues({ ...values, [k]: e.target.value })}
          style={{
            width: '100%', padding: '14px', fontSize: 15,
            background: 'var(--bg)', border: '1px solid var(--line)',
            borderRadius: 'var(--radius)', color: 'var(--ink)', fontFamily: 'var(--font)',
          }}
        >
          {(p as { enum: string[] }).enum.map((v) => <option key={v} value={v}>{v}</option>)}
        </select>
      ) : (
        <input
          value={String(values[k] ?? '')}
          onChange={(e) =>
            setValues({ ...values, [k]: (p as { type: string }).type === 'number' ? Number(e.target.value) : e.target.value })
          }
          style={{
            width: '100%', padding: '14px', fontSize: 15,
            background: 'var(--bg)', border: '1px solid var(--line)',
            borderRadius: 'var(--radius)', color: 'var(--ink)', fontFamily: 'var(--font)',
          }}
        />
      )}
    </div>
  )

  return (
    <div style={{
      minHeight: '100vh', background: 'var(--bg)',
      display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
      padding: '48px 24px',
    }}>
      <div style={{ width: '100%', maxWidth: 800 }}>
        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <div style={{
            fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.08em',
            color: 'var(--muted)', marginBottom: 8,
          }}>
            Форма предсказания
          </div>
          <h1 style={{ fontSize: 28, fontWeight: 600, color: 'var(--ink)', margin: 0 }}>
            {info.name}
          </h1>
          <p style={{ fontSize: 14, color: 'var(--muted)', marginTop: 12, lineHeight: 1.6 }}>
            Заполните признаки — модель предскажет результат с доверительным интервалом.
            {' '}Никакой регистрации не требуется.
          </p>
        </div>

        {/* Password prompt */}
        {needPassword && !result && (
          <div style={{
            background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 32,
            border: '1px solid var(--line)', textAlign: 'center', marginBottom: 20,
          }}>
            <Lock size={32} color="var(--muted)" style={{ margin: '0 auto 16px' }} />
            <p style={{ fontSize: 15, color: 'var(--ink)', margin: '0 0 20px' }}>
              Эта форма защищена паролем
            </p>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Введите пароль"
              style={{
                width: 300, padding: '14px 18px', fontSize: 15,
                background: 'var(--bg)', border: '1px solid var(--line)',
                borderRadius: 'var(--radius)', color: 'var(--ink)', fontFamily: 'var(--font)',
                textAlign: 'center',
              }}
            />
            <button onClick={submit} disabled={!password || busy} style={{
              display: 'block', margin: '16px auto 0', padding: '14px 40px', fontSize: 14, fontWeight: 600,
              background: 'var(--ink)', color: '#101015', border: 'none',
              borderRadius: 'var(--radius)', cursor: 'pointer', fontFamily: 'var(--font)',
              opacity: !password || busy ? 0.4 : 1,
            }}>
              {busy ? 'Проверяем…' : 'Войти'}
            </button>
          </div>
        )}

        {/* Form */}
        {!result && (
          <div style={{
            background: 'var(--surface)', borderRadius: 'var(--radius)',
            padding: '32px 36px', border: '1px solid var(--line)',
          }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 24px' }}>
              <div>{leftCols.map(renderField)}</div>
              <div>{rightCols.map(renderField)}</div>
            </div>

            {error && (
              <div style={{
                color: 'var(--danger)', fontSize: 14,
                padding: '12px 16px', marginBottom: 16,
                background: 'rgba(181,96,90,0.1)', borderRadius: 'var(--radius)',
                border: '1px solid rgba(181,96,90,0.3)',
              }}>
                {error}
              </div>
            )}

            <button onClick={submit} disabled={busy} style={{
              width: '100%', padding: '18px 0', fontSize: 16, fontWeight: 600,
              background: 'var(--ink)', color: '#101015', border: 'none',
              borderRadius: 'var(--radius)', cursor: busy ? 'wait' : 'pointer',
              fontFamily: 'var(--font)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
              marginTop: 8,
            }}>
              {busy ? <><Loader2 size={20} className="spin" /> Считаем…</> : <><Zap size={20} /> Предсказать</>}
            </button>
          </div>
        )}

        {/* Result */}
        {result && (
          <div style={{ display: 'grid', gap: 16 }}>
            <div style={{
              background: 'var(--accent)', borderRadius: 'var(--radius)', padding: '40px 36px',
              color: 'var(--ink)', textAlign: 'center',
            }}>
              <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.06em', opacity: 0.8, marginBottom: 12 }}>
                Результат прогноза
              </div>
              <div style={{ fontSize: 72, fontWeight: 600, lineHeight: 1, letterSpacing: '-0.02em' }}>
                {result.probability !== undefined
                  ? `${fmtShort(result.probability * 100, 1)}%`
                  : fmtShort(result.prediction)}
              </div>
              <div style={{ fontSize: 16, marginTop: 12, opacity: 0.85 }}>
                {result.probability !== undefined ? 'вероятность события' : 'прогнозное значение'}
              </div>
              {result.label !== undefined && (
                <div style={{
                  display: 'inline-block', marginTop: 16, padding: '8px 20px',
                  background: result.decision ? 'rgba(181,96,90,0.3)' : 'rgba(126,154,134,0.3)',
                  borderRadius: 'var(--radius)', fontSize: 14, fontWeight: 600,
                }}>
                  {result.label}
                </div>
              )}
            </div>

            {/* Details */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              {result.interval_low !== undefined && (
                <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 20, border: '1px solid var(--line)' }}>
                  <TrendingUp size={18} color="var(--accent)" style={{ marginBottom: 8 }} />
                  <div style={{ fontSize: 12, textTransform: 'uppercase', color: 'var(--muted)' }}>Доверительный интервал 90%</div>
                  <div style={{ fontSize: 20, fontWeight: 600, color: 'var(--ink)', marginTop: 8 }}>
                    [{fmtShort(result.interval_low, 2)} — {fmtShort(result.interval_high, 2)}]
                  </div>
                  <p style={{ fontSize: 12, color: 'var(--muted)', margin: '4px 0 0' }}>
                    С 90% уверенностью результат будет в этих пределах
                  </p>
                </div>
              )}
              {result.conformal?.prediction_set && (
                <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 20, border: '1px solid var(--line)' }}>
                  <ShieldCheck size={18} color="var(--accent)" style={{ marginBottom: 8 }} />
                  <div style={{ fontSize: 12, textTransform: 'uppercase', color: 'var(--muted)' }}>Уверенность модели</div>
                  <div style={{ fontSize: 20, fontWeight: 600, color: 'var(--ink)', marginTop: 8 }}>
                    {result.conformal.prediction_set.join(' или ')}
                  </div>
                  <p style={{ fontSize: 12, color: 'var(--muted)', margin: '4px 0 0' }}>
                    {result.conformal.prediction_set.length > 1
                      ? 'Модель не уверена — возможны оба варианта'
                      : 'Модель уверена в ответе'}
                  </p>
                </div>
              )}
            </div>

            {/* Reasons */}
            {(result.top_reasons || []).length > 0 && (
              <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 24, border: '1px solid var(--line)' }}>
                <div style={{ fontSize: 12, textTransform: 'uppercase', color: 'var(--muted)', letterSpacing: '0.04em', marginBottom: 12 }}>
                  Почему модель дала такой прогноз
                </div>
                {(result.top_reasons || []).slice(0, 5).map((r, i) => (
                  <div key={i} style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '10px 0', borderBottom: i < 4 ? '1px solid var(--line)' : 'none',
                    fontSize: 14,
                  }}>
                    <span style={{ color: 'var(--ink)' }}>{r.text || `${r.feature} = ${String(r.value)}`}</span>
                    <span style={{ color: r.impact >= 0 ? 'var(--danger)' : 'var(--ok)', fontWeight: 600 }}>
                      {r.impact >= 0 ? '+' : ''}{fmtShort(r.impact * 100, 1)} п.п.
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* OOD warning */}
            {result.out_of_distribution && (
              <div style={{
                background: 'rgba(194,164,94,0.15)', borderRadius: 'var(--radius)', padding: '16px 20px',
                border: '1px solid var(--warn)', fontSize: 14, color: 'var(--warn)',
              }}>
                ⚠ Объект сильно отличается от тех, на которых модель обучалась — прогноз может быть менее точным.
              </div>
            )}

            {/* New prediction button */}
            <button onClick={() => setResult(null)} style={{
              alignSelf: 'center', padding: '14px 32px', fontSize: 14,
              background: 'var(--surface)', color: 'var(--ink)',
              border: '1px solid var(--line)', borderRadius: 'var(--radius)',
              cursor: 'pointer', fontFamily: 'var(--font)',
            }}>
              ← Новый прогноз
            </button>
          </div>
        )}

        {/* Footer */}
        <div style={{ textAlign: 'center', marginTop: 40, fontSize: 11, color: 'var(--muted)' }}>
          Powered by <b>PredictorLab</b> — честные интервалы, никакого волшебства
        </div>
      </div>
    </div>
  )
}
