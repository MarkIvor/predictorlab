import { useEffect, useState } from 'react'
import { counterfactualApi, getSchema, getJob, patchModel, runPlaybook, type ModelOut } from '../../api/endpoints'
import { fmtShort } from '../../design/components'

type ActionableCfg = {
  min?: number
  max?: number
  direction?: 'up' | 'down' | 'both'
  cost_per_unit?: number
  immutable?: boolean
  allowed_values?: (string | number)[]
  cost_flat?: number
}

export default function ActionsTab({ model, onSaved }: { model: ModelOut; onSaved: () => void }) {
  const [schema, setSchema] = useState<Record<string, { type: string; enum?: string[] }>>({})
  const [cfg, setCfg] = useState<Record<string, ActionableCfg>>({})
  const [record, setRecord] = useState<Record<string, unknown>>({})
  const [cf, setCf] = useState<Record<string, any> | null>(null)
  const [playbookStatus, setPlaybookStatus] = useState('')
  const [playbookJob, setPlaybookJob] = useState<string | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getSchema(model.id).then((s) => {
      setSchema(s.input_schema.properties as Record<string, { type: string; enum?: string[] }>)
      setRecord(s.example || {})
    })
    setCfg((model.actionable as Record<string, ActionableCfg>) || {})
  }, [model.id])

  const saveCfg = async (next: Record<string, ActionableCfg>) => {
    setCfg(next)
    await patchModel(model.id, { actionable: next })
    onSaved()
  }

  const runCf = async () => {
    setBusy(true)
    setCf(null)
    try { setCf(await counterfactualApi(model.id, record)) } finally { setBusy(false) }
  }

  const startPlaybook = async () => {
    if (!file) return
    setBusy(true)
    setPlaybookStatus('Загрузка файла…')
    try {
      const form = new FormData()
      form.append('file', file)
      const { job_id } = await runPlaybook(model.id, form)
      setPlaybookJob(job_id)
      for (;;) {
        const job = await getJob(job_id)
        setPlaybookStatus(job.status === 'running' ? `Ищу действия… ${JSON.stringify(job.progress).slice(0, 90)}` : job.status)
        if (job.status === 'done') { setPlaybookStatus('Готово'); break }
        if (job.status === 'error') { setPlaybookStatus('Ошибка: ' + (job.error || '').slice(0, 120)); break }
        await new Promise((r) => setTimeout(r, 2500))
      }
    } finally { setBusy(false) }
  }

  const features = Object.keys(schema)

  return (
    <div className="bento-grid">
      <div className="tile" style={{ gridColumn: 'span 7' }}>
        <span className="tile-label">РАЗМЕТКА ПРИЗНАКОВ: УПРАВЛЯЕМЫЕ / НЕИЗМЕНЯЕМЫЕ</span>
        <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          Управляемый признак: диапазон + направление + стоимость единицы изменения. Неизменяемый (возраст, регион, история) — заблокирован в контрфактуалах и what-if.
        </p>
        <div style={{ maxHeight: 420, overflowY: 'auto', marginTop: 10 }}>
          {features.map((f) => {
            const c = cfg[f] || {}
            return (
              <div key={f} style={{ borderTop: '1px solid var(--line)', padding: '10px 0' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>{f}</span>
                  <label style={{ fontSize: 11, display: 'flex', gap: 6, alignItems: 'center' }}>
                    <input type="checkbox" checked={!c.immutable && Object.keys(c).length > 0}
                      onChange={(e) => {
                        const next = { ...cfg }
                        if (e.target.checked) next[f] = { direction: 'both', cost_per_unit: 0 }
                        else next[f] = { immutable: true }
                        void saveCfg(next as Record<string, ActionableCfg>)
                      }} />
                    управляемый
                  </label>
                </div>
                {!c.immutable && Object.keys(c).length > 0 && (
                  <div className="form-row" style={{ marginTop: 8 }}>
                    <div className="field"><label>Мин</label><input value={c.min ?? ''} onChange={(e) => setCfg({ ...cfg, [f]: { ...c, min: Number(e.target.value) } as ActionableCfg })} /></div>
                    <div className="field"><label>Макс</label><input value={c.max ?? ''} onChange={(e) => setCfg({ ...cfg, [f]: { ...c, max: Number(e.target.value) } as ActionableCfg })} /></div>
                    <div className="field"><label>Направление</label>
                      <select value={c.direction || 'both'} onChange={(e) => setCfg({ ...cfg, [f]: { ...c, direction: e.target.value as ActionableCfg['direction'] } })}>
                        <option value="both">оба</option><option value="up">только ↑</option><option value="down">только ↓</option>
                      </select></div>
                    <div className="field"><label>Стоимость ₽ / единицу</label><input value={c.cost_per_unit ?? 0} onChange={(e) => setCfg({ ...cfg, [f]: { ...c, cost_per_unit: Number(e.target.value) } as ActionableCfg })} /></div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
        <button className="btn btn-ink" style={{ marginTop: 8 }} onClick={() => saveCfg(cfg)}>СОХРАНИТЬ РАЗМЕТКУ</button>
      </div>

      <div className="tile" style={{ gridColumn: 'span 5' }}>
        <span className="tile-label">МИНИМАЛЬНОЕ ДЕЙСТВИЕ ДЛЯ ОБЪЕКТА</span>
        <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          Ищется самое дешёвое изменение управляемых признаков, переводящее объект через порог. Таймаут поиска на объект ограничен.
        </p>
        <div className="form-row" style={{ marginTop: 10 }}>
          {Object.entries(schema).slice(0, 6).map(([k, p]) => (
            <div className="field" key={k}>
              <label>{k}</label>
              {p.enum ? (
                <select value={String(record[k] ?? '')} onChange={(e) => setRecord({ ...record, [k]: e.target.value })}>
                  {p.enum.map((v) => <option key={v} value={v}>{v}</option>)}
                </select>
              ) : <input value={String(record[k] ?? '')} onChange={(e) => setRecord({ ...record, [k]: e.target.value })} />}
            </div>
          ))}
        </div>
        <button className="btn btn-ink" onClick={runCf} disabled={busy || Object.keys(cfg).length === 0}>{busy ? 'ИЩУ…' : 'ПОДОБРАТЬ ДЕЙСТВИЕ'}</button>
        {cf && (
          <div style={{ marginTop: 14, fontSize: 12, lineHeight: 1.7 }}>
            {cf.found ? (
              <>
                <div><b>Действие:</b> {Object.entries(cf.changes).map(([k, v]) => `${k} → ${String(v)}`).join('; ')}</div>
                <div><b>Стоимость:</b> {fmtShort(cf.cost_rub, 0)} ₽</div>
                <div><b>Вероятность:</b> {fmtShort(cf.probability_before * 100, 1)}% → {fmtShort(cf.probability_after * 100, 1)}%</div>
                <div><b>Ожидаемый ROI:</b> {cf.expected_roi_rub !== null ? `${fmtShort(cf.expected_roi_rub, 0)} ₽` : '—'}</div>
              </>
            ) : <div>{String(cf.detail || 'Действие в заданных рамках не найдено')}</div>}
            <p className="muted" style={{ fontSize: 11 }}>Контрфактуал — ответ модели, а не доказанный причинный эффект.</p>
          </div>
        )}
      </div>

      <div className="tile" style={{ gridColumn: 'span 12' }}>
        <span className="tile-label">ПЛЕЙБУК ДЕЙСТВИЙ (ФОНОВАЯ ЗАДАЧА)</span>
        <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          Загрузите текущую базу объектов (CSV/XLSX). Система отберет объекты выше порога, подберёт действия,
          отсортирует по ожидаемой прибыли и отдаст XLSX/CSV. Объекты с отрицательным ROI помечаются «не трогать».
        </p>
        <div style={{ display: 'flex', gap: 8, marginTop: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <input type="file" accept=".csv,.xlsx,.parquet" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          <button className="btn btn-ink" onClick={startPlaybook} disabled={!file || busy || Object.keys(cfg).length === 0}>ЗАПУСТИТЬ ПЛЕЙБУК</button>
          {playbookJob && playbookStatus === 'Готово' && (
            <>
              <a className="btn" href={`/api/v1/jobs/${playbookJob}/result/playbook.csv`}>CSV ↓</a>
              <a className="btn" href={`/api/v1/jobs/${playbookJob}/result/playbook.xlsx`}>XLSX ↓</a>
            </>
          )}
        </div>
        {playbookJob && <p className="muted" style={{ fontSize: 11, marginTop: 8 }}>{playbookStatus}</p>}
      </div>
    </div>
  )
}
