import { useEffect, useState } from 'react'
import { getJob, getSchema, predictApi, type ModelOut, type Prediction, type Reason } from '../../api/endpoints'
import { fmtShort } from '../../design/components'
import { api } from '../../api/client'

type Prop = { type: string; enum?: string[]; format?: string; example?: unknown; title?: string }

export default function PredictTab({ model }: { model: ModelOut }) {
  const [schema, setSchema] = useState<Record<string, Prop> | null>(null)
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [result, setResult] = useState<Prediction | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [batchJob, setBatchJob] = useState<string | null>(null)
  const [batchStatus, setBatchStatus] = useState('')
  const [file, setFile] = useState<File | null>(null)

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
    } finally { setBusy(false) }
  }

  const startBatch = async () => {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('include', 'reasons')
      const r = await api<{ job_id: string }>(`/api/v1/models/${model.id}/predict/batch`, { form })
      setBatchJob(r.job_id)
      setBatchStatus('В очереди')
      for (;;) {
        const job = await getJob(r.job_id)
        setBatchStatus(job.status === 'running' ? `Считаю… ${JSON.stringify(job.progress).slice(0, 80)}` : job.status)
        if (job.status === 'done') { setBatchStatus('Готово'); break }
        if (job.status === 'error') { setError(job.error || 'Ошибка'); break }
        if (job.status === 'cancelled') { setError('Отменено'); break }
        await new Promise((res) => setTimeout(res, 2000))
      }
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }

  if (!schema) return <p className="muted">Загрузка схемы…</p>

  const reasons: Reason[] = result?.top_reasons || []

  return (
    <div className="bento-grid">
      <div className="tile" style={{ gridColumn: 'span 6' }}>
        <span className="tile-label">ОДИНОЧНЫЙ ПРОГНОЗ</span>
        <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>Пропуски допустимы — модель умеет их обрабатывать. Неизвестные поля игнорируются.</p>
        {Object.entries(schema).map(([k, p]) => (
          <div className="field" key={k}>
            <label>{k}</label>
            {p.enum ? (
              <select value={String(values[k] ?? '')} onChange={(e) => setValues({ ...values, [k]: e.target.value })}>
                {p.enum.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            ) : p.type === 'boolean' ? (
              <select value={String(values[k] ?? '')} onChange={(e) => setValues({ ...values, [k]: e.target.value })}>
                {['true', 'false'].map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            ) : (
              <input
                value={String(values[k] ?? '')}
                onChange={(e) => setValues({ ...values, [k]: p.type === 'number' ? Number(e.target.value) : e.target.value })}
              />
            )}
          </div>
        ))}
        {error && <p style={{ color: 'var(--danger)', fontSize: 12 }}>{error}</p>}
        <button className="btn btn-ink" onClick={predict} disabled={busy}>{busy ? 'СЧИТАЮ…' : 'ПРЕДСКАЗАТЬ'}</button>
      </div>

      <div style={{ gridColumn: 'span 6', display: 'grid', gap: 8 }}>
        {result && (
          <div className="tile">
            <span className="tile-label">РЕЗУЛЬТАТ</span>
            <div className="hero-digit" style={{ marginTop: 12 }}>
              {result.probability !== undefined ? fmtShort(result.probability * 100, 1) + '%' : fmtShort(result.prediction)}
            </div>
            <span className="denominator">{result.probability !== undefined ? 'ВЕРОЯТНОСТЬ' : 'ПРОГНОЗ'}</span>
            <div style={{ marginTop: 12, fontSize: 12, lineHeight: 1.7 }}>
              {result.label !== undefined && <div>Класс: <b>{result.label}</b> · решение: {result.decision ? 'ДА' : 'НЕТ'} (порог {result.threshold})</div>}
              {result.interval_low !== undefined && <div>90% интервал: [{fmtShort(result.interval_low, 2)}; {fmtShort(result.interval_high, 2)}]</div>}
              {result.conformal && <div>Конформальное множество: {result.conformal.prediction_set.join(' | ')} (покрытие {Math.round(result.conformal.coverage * 100)}%)</div>}
              <div className="muted">{result.out_of_distribution ? '⚠ OOD: объект вне распределения' : 'В пределах распределения'}</div>
            </div>
            {reasons.length > 0 && (
              <>
                <span className="tile-label" style={{ marginTop: 16, display: 'block' }}>ПРИЧИНЫ</span>
                {reasons.map((r, i) => (
                  <div className="reason" key={i}>
                    <span>{r.text || `${r.feature} = ${String(r.value)}`}</span>
                    <span className={r.impact >= 0 ? 'impact-up' : 'impact-down'}>
                      {r.impact >= 0 ? '+' : ''}{fmtShort(r.impact * 100, 1)} п.п.
                    </span>
                  </div>
                ))}
              </>
            )}
            {warnings.map((w, i) => <p key={i} className="muted" style={{ fontSize: 11 }}>{w}</p>)}
          </div>
        )}
        <div className="tile">
          <span className="tile-label">ПАКЕТНЫЙ ПРОГНОЗ (CSV / XLSX)</span>
          <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>Фоновая задача. Файл: prediction, probability, интервалы, ood; top_reasons — только для top-{1000} рисковых.</p>
          <input type="file" accept=".csv,.xlsx,.parquet" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button className="btn btn-ink" onClick={startBatch} disabled={!file || busy}>ЗАПУСТИТЬ</button>
            {batchJob && batchStatus === 'Готово' && (
              <>
                <a className="btn" href={`/api/v1/jobs/${batchJob}/result/predictions.csv`}>CSV ↓</a>
                <a className="btn" href={`/api/v1/jobs/${batchJob}/result/predictions.xlsx`}>XLSX ↓</a>
              </>
            )}
          </div>
          {batchJob && <p className="muted" style={{ fontSize: 11, marginTop: 8 }}>Задача {batchJob}: {batchStatus}</p>}
        </div>
      </div>
    </div>
  )
}
