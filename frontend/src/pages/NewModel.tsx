import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { sse, ApiError } from '../api/client'
import {
  buildFeatures, cancelJob, createModel, getDataset, getJob, listConnections, listDatasets,
  patchDataset, patchModel, recheckModel, trainModel, uploadDataset, createConnection, testConnection,
  llmStatus, type DatasetOut, type ModelOut,
} from '../api/endpoints'
import { AccentTile, ArrowButton, RingGauge, StatTile, VerdictBadge, fmtShort } from '../design/components'
import Layout from './Layout'

const STEPS = ['DATA', 'TARGET', 'HEALTH', 'TRAIN', 'RESULT'] as const

export default function NewModel() {
  const nav = useNavigate()
  const [step, setStep] = useState(0)
  const [dataset, setDataset] = useState<DatasetOut | null>(null)
  const [model, setModel] = useState<ModelOut | null>(null)
  const [error, setError] = useState('')

  const go = (next: number) => { setError(''); setStep(Math.max(0, Math.min(4, next))) }

  return (
    <Layout title="НОВАЯ МОДЕЛЬ">
      <div className="steps" style={{ margin: '12px 2px' }}>
        {STEPS.map((s, i) => (
          <span key={s}>
            <span className={`step ${i === step ? 'active' : ''} ${i < step ? 'done' : ''}`}>{s}</span>
            {i < STEPS.length - 1 && <span className="step-arrow">→</span>}
          </span>
        ))}
        <span className="muted" style={{ marginLeft: 'auto', fontSize: 11 }}>STEP {step + 1} / 5</span>
      </div>
      {error && <div className="tile" style={{ borderColor: 'var(--danger)', borderStyle: 'solid', borderWidth: 1, marginBottom: 8 }}>
        <span className="tile-label" style={{ color: 'var(--danger)' }}>ОШИБКА</span>
        <p style={{ margin: '8px 0 0' }}>{error}</p>
      </div>}
      {step === 0 && <DataStep onDataset={(d) => { setDataset(d); go(1) }} onError={setError} />}
      {step === 1 && dataset && (
        <TargetStep dataset={dataset} onModel={(m) => { setModel(m); go(2) }} onError={setError} onBack={() => go(0)} />
      )}
      {step === 2 && model && (
        <HealthStep model={model}
          onReady={(m) => { setModel(m); go(3) }} onOverride={(m) => { setModel(m); go(3) }} onBack={() => go(1)} />
      )}
      {step === 3 && model && (
        <TrainStep model={model} onDone={() => go(4)} onError={setError} onBack={() => go(2)} />
      )}
      {step === 4 && model && (
        <ResultStep modelId={model.id} onOpen={() => nav(`/m/${model.id}`)} />
      )}
    </Layout>
  )
}

function DataStep({ onDataset, onError }: {
  onDataset: (d: DatasetOut) => void
  onError: (e: string) => void
}) {
  const [mode, setMode] = useState<'upload' | 'existing' | 'features'>('upload')
  const [busy, setBusy] = useState(false)
  const [datasets, setDatasets] = useState<{ id: string; name: string; nrows: number }[]>([])
  const [file, setFile] = useState<File | null>(null)
  const [sampleRows, setSampleRows] = useState('')

  const refresh = useCallback(() => { listDatasets().then(setDatasets) }, [])
  useEffect(() => { refresh() }, [refresh])

  const doUpload = async () => {
    if (!file) return
    setBusy(true)
    try {
      const form = new FormData()
      form.append('file', file)
      if (sampleRows) form.append('sample_rows', sampleRows)
      const d = await uploadDataset(form)
      onDataset(d)
    } catch (e) {
      onError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="bento-grid" style={{ marginTop: 8 }}>
      <div className="tile" style={{ gridColumn: 'span 12' }}>
        <div className="tabbar">
          <button className={mode === 'upload' ? 'tab active' : 'tab'} onClick={() => setMode('upload')}>ФАЙЛ</button>
          <button className={mode === 'existing' ? 'tab active' : 'tab'} onClick={() => setMode('existing')}>ГОТОВЫЙ ДАТАСЕТ</button>
          <button className={mode === 'features' ? 'tab active' : 'tab'} onClick={() => setMode('features')}>СОБРАТЬ ИЗ БД</button>
        </div>
      </div>

      {mode === 'upload' && (
        <div className="tile" style={{ gridColumn: 'span 7' }}>
          <span className="tile-label">ЗАГРУЗКА CSV / XLSX / PARQUET</span>
          <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
            Кодировка и разделитель определяются автоматически (включая cp1251). ПДн-колонки исключаются из обучения по умолчанию.
          </p>
          <div className="field" style={{ marginTop: 12 }}>
            <label>Файл</label>
            <input type="file" accept=".csv,.xlsx,.parquet" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          </div>
          <div className="field">
            <label>Случайная выборка строк (если данных слишком много)</label>
            <input value={sampleRows} onChange={(e) => setSampleRows(e.target.value)} placeholder="например, 100000 — пусто = без выборки" />
          </div>
          <button className="btn btn-ink" disabled={!file || busy} onClick={doUpload}>{busy ? 'ЗАГРУЗКА…' : 'ЗАГРУЗИТЬ'}</button>
        </div>
      )}

      {mode === 'existing' && (
        <div className="tile" style={{ gridColumn: 'span 12' }}>
          <span className="tile-label">ДАТАСЕТЫ</span>
          <div style={{ marginTop: 12 }}>
            {datasets.map((d) => (
              <div key={d.id} className="leaderboard-row" style={{ cursor: 'pointer' }} onClick={async () => {
                setBusy(true)
                try { onDataset(await getDataset(d.id)) } catch (e) { onError(String(e)) } finally { setBusy(false) }
              }}>
                <span>{d.name}</span>
                <span className="muted">{d.nrows.toLocaleString('ru-RU')} строк →</span>
              </div>
            ))}
            {datasets.length === 0 && <p className="muted">Датасетов нет — загрузите файл.</p>}
          </div>
        </div>
      )}

      {mode === 'features' && <FeaturesBuilder onDataset={onDataset} onError={onError} />}
    </div>
  )
}

function FeaturesBuilder({ onDataset, onError }: { onDataset: (d: DatasetOut) => void; onError: (e: string) => void }) {
  const [connections, setConnections] = useState<{ id: number; name: string; db_type: string }[]>([])
  const [showNew, setShowNew] = useState(false)
  const [dbType, setDbType] = useState('sqlite')
  const [params, setParams] = useState<Record<string, string>>({})
  const [cfg, setCfg] = useState({
    main_table: '', main_key: '', datetime_col: '', horizon_days: '45', n_snapshots: '4',
    target_table: '', target_fk: '', target_dt: '', min_count: '1',
  })
  const [children, setChildren] = useState<{ table: string; fk: string; datetime_col: string; windows: string }[]>([])
  const [busy, setBusy] = useState(false)

  useEffect(() => { listConnections().then((c) => { setConnections(c); if (c.length === 0) setShowNew(true) }) }, [])

  const newParam = (key: string, val: string) => setParams((p) => ({ ...p, [key]: val }))

  const createConn = async () => {
    setBusy(true)
    try {
      await createConnection({ name: params.name || dbType, db_type: dbType, params })
      const c = await listConnections()
      setConnections(c)
      setShowNew(false)
    } catch (e) { onError(e instanceof ApiError ? e.message : String(e)) } finally { setBusy(false) }
  }

  const build = async () => {
    if (!connections[0]) return
    setBusy(true)
    try {
      const body = {
        name: `Витрина ${cfg.main_table}`,
        config: {
          connection_id: connections[0].id,
          main_table: cfg.main_table, main_key: cfg.main_key,
          datetime_col: cfg.datetime_col || null,
          main_columns: [],
          snapshot_mode: 'rolling',
          n_snapshots: Number(cfg.n_snapshots) || 4,
          horizon_days: Number(cfg.horizon_days) || 45,
          children: children.filter((c) => c.table).map((c) => ({
            table: c.table, fk: c.fk, datetime_col: c.datetime_col,
            windows: (c.windows || '7,30,90').split(',').map(Number).filter(Boolean),
            rfm: true,
            agg_columns: [],
          })),
          target: { table: cfg.target_table, fk: cfg.target_fk, datetime_col: cfg.target_dt, type: 'count_in_window', min_count: Number(cfg.min_count) || 1 },
        },
      }
      const { job_id } = await buildFeatures(body)
      const d = await pollJob(job_id)
      onDataset(await getDataset(d.dataset_id as string))
    } catch (e) { onError(e instanceof ApiError ? e.message : String(e)) } finally { setBusy(false) }
  }

  return (
    <div className="tile" style={{ gridColumn: 'span 12' }}>
      <span className="tile-label">СБОРЩИК ФИЧАЙ ИЗ НЕСКОЛЬКИХ ТАБЛИЦ (POINT-IN-TIME)</span>
      <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
        Все агрегаты считаются только по событиям до точки отсечки T0; таргет — по окну [T0, T0+горизонт). SQL всегда виден.
      </p>
      {showNew ? (
        <div style={{ marginTop: 12 }}>
          <div className="form-row">
            <div className="field">
              <label>Тип БД</label>
              <select value={dbType} onChange={(e) => setDbType(e.target.value)}>
                <option value="sqlite">SQLite</option><option value="postgresql">PostgreSQL</option>
                <option value="mysql">MySQL</option><option value="clickhouse">ClickHouse</option>
              </select>
            </div>
            {(dbType === 'sqlite' ? ['database'] : ['host', 'port', 'database', 'username', 'password']).map((k) => (
              <div className="field" key={k}>
                <label>{k}</label>
                <input value={params[k] || ''} onChange={(e) => newParam(k, e.target.value)} />
              </div>
            ))}
          </div>
          <button className="btn" onClick={createConn} disabled={busy}>ПОДКЛЮЧИТЬ</button>
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 8, marginTop: 12, alignItems: 'center' }}>
          <span>Подключение: <b>{connections[0]?.name}</b> ({connections[0]?.db_type})</span>
          <button className="btn" onClick={async () => { const t = await testConnection(connections[0].id); onError(t.ok ? `Подключение ок, таблиц: ${t.tables.length}` : (t.error || 'Не удалось подключиться')) }}>ПРОВЕРИТЬ</button>
        </div>
      )}
      {!showNew && (
        <div style={{ marginTop: 16 }}>
          <div className="form-row">
            {([['main_table', 'Главная таблица'], ['main_key', 'Ключ сущности'], ['datetime_col', 'Время события (главная, опц.)'],
              ['horizon_days', 'Горизонт, дней'], ['n_snapshots', 'Срезов T0'],
              ['target_table', 'Таблица таргета'], ['target_fk', 'FK таргета'], ['target_dt', 'Время события таргета'], ['min_count', 'Мин. событий = 1']] as const).map(([k, label]) => (
              <div className="field" key={k}>
                <label>{label}</label>
                <input value={(cfg as Record<string, string>)[k]} onChange={(e) => setCfg((c) => ({ ...c, [k]: e.target.value }))} />
              </div>
            ))}
          </div>
          <span className="tile-label" style={{ marginTop: 12 }}>ДОЧЕРНИЕ ТАБЛИЦЫ</span>
          {children.map((c, i) => (
            <div className="form-row" key={i} style={{ marginTop: 8 }}>
              <div className="field"><label>Таблица</label><input value={c.table} onChange={(e) => setChildren((cs) => cs.map((x, j) => j === i ? { ...x, table: e.target.value } : x))} /></div>
              <div className="field"><label>FK</label><input value={c.fk} onChange={(e) => setChildren((cs) => cs.map((x, j) => j === i ? { ...x, fk: e.target.value } : x))} /></div>
              <div className="field"><label>Время события</label><input value={c.datetime_col} onChange={(e) => setChildren((cs) => cs.map((x, j) => j === i ? { ...x, datetime_col: e.target.value } : x))} /></div>
              <div className="field"><label>Окна, дней</label><input value={c.windows} placeholder="7,30,90" onChange={(e) => setChildren((cs) => cs.map((x, j) => j === i ? { ...x, windows: e.target.value } : x))} /></div>
            </div>
          ))}
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <button className="btn" onClick={() => setChildren((c) => [...c, { table: '', fk: '', datetime_col: '', windows: '7,30,90' }])}>+ ТАБЛИЦА</button>
            <button className="btn btn-ink" onClick={build} disabled={busy || !cfg.main_table || !cfg.target_table}>
              {busy ? 'СБОРКА…' : 'СОБРАТЬ ВИТРИНУ'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

async function pollJob(jobId: string, onProgress?: (p: Record<string, unknown>) => void): Promise<Record<string, unknown>> {
  for (;;) {
    const job = await getJob(jobId)
    onProgress?.(job.progress || {})
    if (job.status === 'done') return job.progress
    if (job.status === 'error') throw new Error(job.error || 'Задача упала')
    if (job.status === 'cancelled') throw new Error('Задача отменена')
    await new Promise((r) => setTimeout(r, 1500))
  }
}

function TargetStep({ dataset, onModel, onError, onBack }: {
  dataset: DatasetOut
  onModel: (m: ModelOut) => void
  onError: (e: string) => void
  onBack: () => void
}) {
  const [target, setTarget] = useState('')
  const [taskType, setTaskType] = useState('')
  const [eventTime, setEventTime] = useState(dataset.event_time_col || '')
  const [entity, setEntity] = useState(dataset.entity_col || '')
  const [goal, setGoal] = useState('')
  const [llmOn, setLlmOn] = useState(false)
  const [llmBusy, setLlmBusy] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => { llmStatus().then((s) => setLlmOn(s.enabled)) }, [])

  const usable = dataset.columns.filter((c) => !c.excluded || c.name === target)

  const suggest = async () => {
    setLlmBusy(true)
    try {
      const { api } = await import('../api/client')
      const r = await api<{ target_col: string | null; task_type: string | null; explanation: string }>('/api/llm/target-from-words', { json: { goal, dataset_id: dataset.id } })
      if (r.target_col) setTarget(r.target_col)
      if (r.task_type) setTaskType(r.task_type)
    } catch (e) { onError(e instanceof ApiError ? e.message : 'LLM недоступна') } finally { setLlmBusy(false) }
  }

  const create = async () => {
    setBusy(true)
    try {
      if (eventTime !== (dataset.event_time_col || '')) await patchDataset(dataset.id, { event_time_col: eventTime || null, entity_col: entity || null })
      else if (entity !== (dataset.entity_col || '')) await patchDataset(dataset.id, { entity_col: entity || null })
      const m = await createModel({
        dataset_id: dataset.id, name: `Модель по «${dataset.name}»`,
        target_col: target, task_type: taskType || null,
        event_time_col: eventTime || null, entity_col: entity || null,
      })
      onModel(m)
    } catch (e) { onError(e instanceof ApiError ? e.message : String(e)) } finally { setBusy(false) }
  }

  return (
    <div className="bento-grid" style={{ marginTop: 8 }}>
      <div className="tile" style={{ gridColumn: 'span 5' }}>
        <span className="tile-label">ТАРГЕТ</span>
        <div className="field" style={{ marginTop: 12 }}>
          <label>Колонка-цель</label>
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">— выберите —</option>
            {usable.map((c) => <option key={c.name} value={c.name}>{c.name} ({c.type})</option>)}
          </select>
        </div>
        <div className="field">
          <label>Тип задачи</label>
          <select value={taskType} onChange={(e) => setTaskType(e.target.value)}>
            <option value="">Определить автоматически</option>
            <option value="binary">Бинарная классификация</option>
            <option value="multiclass">Мультикласс</option>
            <option value="regression">Регрессия</option>
            <option value="timeseries">Временной ряд</option>
          </select>
        </div>
        <div className="field">
          <label>Время события (для честного out-of-time сплита)</label>
          <select value={eventTime} onChange={(e) => setEventTime(e.target.value)}>
            <option value="">— нет —</option>
            {dataset.columns.filter((c) => c.type === 'datetime').map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Сущность (для group split)</label>
          <select value={entity} onChange={(e) => setEntity(e.target.value)}>
            <option value="">— нет —</option>
            {dataset.columns.filter((c) => c.type === 'id' || c.uniqueness > 0.5).map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
          </select>
        </div>
      </div>
      <div className="tile" style={{ gridColumn: 'span 7' }}>
        <span className="tile-label">ДАННЫЕ</span>
        <div style={{ display: 'flex', gap: 24, marginTop: 12 }}>
          <div>
            <div className="hero-digit-sm">{dataset.nrows.toLocaleString('ru-RU')}</div>
            <span className="tile-label muted">СТРОК</span>
          </div>
          <div>
            <div className="hero-digit-sm">{dataset.ncols}</div>
            <span className="tile-label muted">КОЛОНОК</span>
          </div>
        </div>
        {llmOn && (
          <div style={{ marginTop: 16 }}>
            <span className="tile-label">ЦЕЛЬ СЛОВАМИ (LLM)</span>
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <input style={{ flex: 1 }} value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="кто из клиентов не купит в следующие 45 дней" />
              <button className="btn" onClick={suggest} disabled={llmBusy || !goal}>{llmBusy ? '…' : 'ПРЕДЛОЖИТЬ'}</button>
            </div>
            <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>LLM видит только схему и статистики. Сырые строки не уходят.</p>
          </div>
        )}
      </div>
      <div className="wizard-nav" style={{ gridColumn: 'span 12' }}>
        <button className="btn" onClick={onBack}>← ДАННЫЕ</button>
        <button className="btn btn-ink" onClick={create} disabled={!target || busy}>{busy ? 'ПРОВЕРКА…' : 'ПРОВЕРИТЬ ЗДОРОВЬЕ →'}</button>
      </div>
    </div>
  )
}

function HealthStep({ model, onReady, onOverride, onBack }: {
  model: ModelOut
  onReady: (m: ModelOut) => void
  onOverride: (m: ModelOut) => void
  onBack: () => void
}) {
  const [current, setCurrent] = useState<ModelOut>(model)
  const [busy, setBusy] = useState(false)
  const [override, setOverride] = useState(false)
  const report = current.guard_report
  const blockCols = (report?.checks || []).filter((c) => c.verdict === 'BLOCK').map((c) => c.column).filter(Boolean)

  const excludeAndProceed = async () => {
    setBusy(true)
    try {
      const cols = Array.from(new Set([...(current.excluded_cols || []), ...blockCols]))
      await patchModel(current.id, { excluded_cols: cols })
      const updated = await recheckModel(current.id)
      const full = await getModelQuiet(current.id)
      full.guard_report = updated
      setCurrent(full)
      if (updated.verdict !== 'BLOCK') onReady(full)
    } finally { setBusy(false) }
  }

  return (
    <div className="bento-grid" style={{ marginTop: 8 }}>
      <div className="tile" style={{ gridColumn: 'span 12', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="tile-label">ЗДОРОВЬЕ ДАННЫХ · LEAKAGE GUARD</span>
        <VerdictBadge verdict={report?.verdict || 'OK'} />
      </div>
      {(report?.checks || []).map((c, i) => (
        <div className="tile" key={i} style={{ gridColumn: 'span 6' }}>
          <div className="stat-head">
            <span className="tile-label">{c.id.replace(/_/g, ' ').toUpperCase()}</span>
            <VerdictBadge verdict={c.verdict} />
          </div>
          <p style={{ fontSize: 12, marginTop: 10 }}>{c.detail}</p>
        </div>
      ))}
      {(report?.checks || []).length === 0 && (
        <div className="tile" style={{ gridColumn: 'span 12' }}>
          <p className="muted">Замечаний нет — утечек не найдено, данные сбалансированы.</p>
        </div>
      )}
      {report?.verdict === 'BLOCK' && (
        <div className="tile" style={{ gridColumn: 'span 12', borderColor: 'var(--danger)', borderStyle: 'solid', borderWidth: 1 }}>
          <span className="tile-label" style={{ color: 'var(--danger)' }}>ОБНАРУЖЕНА ВЕРОЯТНАЯ УТЕЧКА ЦЕЛЕВОЙ ПЕРЕМЕННОЙ</span>
          <p style={{ fontSize: 13, marginTop: 8 }}>
            Результаты показаны не будут: модель выучила бы признак, который известен только ПОСЛЕ события.
            Например, «дата расторжения» известна только у уже ушедших клиентов.
          </p>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 12, flexWrap: 'wrap' }}>
            <button className="btn btn-accent" onClick={excludeAndProceed} disabled={busy}>
              ИСКЛЮЧИТЬ ({blockCols.join(', ')}) И ПЕРЕОБУЧИТЬ ПРОВЕРКУ
            </button>
            <label style={{ fontSize: 12, display: 'flex', gap: 6, alignItems: 'center' }}>
              <input type="checkbox" checked={override} onChange={(e) => setOverride(e.target.checked)} />
              Я понимаю риск: снять блок (фиксируется в Model Card)
            </label>
            {override && <button className="btn btn-danger" onClick={() => onOverride({ ...current })}>ПРОДОЛЖИТЬ С УТЕЧКОЙ</button>}
          </div>
        </div>
      )}
      <div className="wizard-nav" style={{ gridColumn: 'span 12' }}>
        <button className="btn" onClick={onBack}>← ЦЕЛЬ</button>
        {report?.verdict !== 'BLOCK' && (
          <button className="btn btn-ink" onClick={() => onReady(current)}>ОБУЧИТЬ →</button>
        )}
      </div>
    </div>
  )
}

async function getModelQuiet(id: number) {
  const { getModel } = await import('../api/endpoints')
  return getModel(id)
}

function TrainStep({ model, onDone, onError, onBack }: {
  model: ModelOut
  onDone: () => void
  onError: (e: string) => void
  onBack: () => void
}) {
  const [mode, setMode] = useState<'quick' | 'full'>('quick')
  const [running, setRunning] = useState(false)
  const [leaderboard, setLeaderboard] = useState<{ name: string; cv_metric: number }[]>([])
  const [stage, setStage] = useState('')
  const [pct, setPct] = useState(0)
  const abort = useRef<AbortController | null>(null)

  const start = async () => {
    setRunning(true)
    setLeaderboard([])
    setStage('Запуск…')
    try {
      const { job_id } = await trainModel(model.id, { mode })
      abort.current = new AbortController()
      let done = false
      for await (const ev of sse(`/api/jobs/${job_id}/events`, abort.current.signal)) {
        if (ev.event === 'stage') {
          const d = ev.data as { data?: { stage?: string; message?: string } }
          setStage(d?.data?.message || d?.data?.stage || '')
          if (d?.data?.stage === 'split') setPct(0.15)
          if (d?.data?.stage === 'final_fit') setPct(0.55)
          if (d?.data?.stage === 'uncertainty') setPct(0.7)
          if (d?.data?.stage === 'evaluate') setPct(0.8)
          if (d?.data?.stage === 'explain') setPct(0.9)
          if (d?.data?.stage === 'done') setPct(1)
        }
        if (ev.event === 'candidate') {
          const d = ev.data as { data?: { leaderboard?: { name: string; cv_metric: number }[] } }
          if (d?.data?.leaderboard) setLeaderboard(d.data.leaderboard)
          setPct((p) => Math.max(p, 0.3))
        }
        if (ev.event === 'done') {
          done = true
          setPct(1)
          break
        }
      }
      if (done) onDone()
      else {
        const job = await getJob(job_id)
        if (job.status === 'error') throw new Error(job.error || 'Ошибка обучения')
        if (job.status === 'done') onDone()
      }
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }

  const stop = async () => {
    abort.current?.abort()
    const jobs = running ? await lastTrainJob(model.id) : null
    if (jobs) await cancelJob(jobs)
  }

  return (
    <div className="bento-grid" style={{ marginTop: 8 }}>
      <div className="tile" style={{ gridColumn: 'span 5' }}>
        <span className="tile-label">РЕЖИМ ОБУЧЕНИЯ</span>
        <div className="tabbar" style={{ marginTop: 12 }}>
          <button className={mode === 'quick' ? 'tab active' : 'tab'} onClick={() => setMode('quick')} disabled={running}>QUICK</button>
          <button className={mode === 'full' ? 'tab active' : 'tab'} onClick={() => setMode('full')} disabled={running}>FULL</button>
        </div>
        <p className="muted" style={{ fontSize: 12, marginTop: 12 }}>
          {mode === 'quick'
            ? 'CatBoost с дефолтными параметрами + линейный baseline. Около 1–2 минут.'
            : 'Optuna по CatBoost и LightGBM в пределах бюджета времени (TRAIN_TIME_BUDGET_SEC). По истечении — лучший найденный.'}
        </p>
        <div style={{ marginTop: 16 }}>
          {!running
            ? <button className="btn btn-ink" onClick={start} disabled={running}>{running ? '…' : 'ЗАПУСТИТЬ ОБУЧЕНИЕ'}</button>
            : <button className="btn btn-danger" onClick={stop}>ОСТАНОВИТЬ (СОХРАНИТ ЛУЧШИЙ)</button>}
          {!running && <button className="btn" style={{ marginLeft: 8 }} onClick={onBack}>← НАЗАД</button>}
        </div>
      </div>
      <div className="tile" style={{ gridColumn: 'span 4', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <RingGauge value={pct} max={1} label="PROGRESS" format={(v) => `${Math.round(v * 100)}%`} />
      </div>
      <div className="tile" style={{ gridColumn: 'span 3' }}>
        <span className="tile-label">ЛИДЕРБОД</span>
        <div style={{ marginTop: 8, minHeight: 120 }}>
          {leaderboard.length === 0 && <p className="muted" style={{ fontSize: 12 }}>{stage || 'Ожидание запуска'}</p>}
          {leaderboard.map((c, i) => (
            <div key={c.name} className={`leaderboard-row ${i === 0 ? 'best' : ''}`}>
              <span>{c.name}</span>
              <span>{fmtShort(c.cv_metric, 4)}</span>
            </div>
          ))}
          {leaderboard.length > 0 && <p className="muted" style={{ fontSize: 11, marginTop: 8 }}>{stage}</p>}
        </div>
      </div>
    </div>
  )
}

async function lastTrainJob(modelId: number): Promise<string | null> {
  const { api } = await import('../api/client')
  const jobs = await api<{ id: string; type: string; status: string; model_id: number }[]>('/api/jobs?all=1').catch(() => [] as { id: string; type: string; status: string; model_id: number }[])
  const running = jobs.find((j: { type: string; model_id: number; status: string }) => j.type === 'train' && j.model_id === modelId && j.status === 'running')
  return running?.id || null
}

function ResultStep({ modelId, onOpen }: { modelId: number; onOpen: () => void }) {
  const [model, setModel] = useState<ModelOut | null>(null)
  useEffect(() => { getModelQuiet(modelId).then(setModel) }, [modelId])
  const metrics = (model?.metrics || {}) as Record<string, number>
  return (
    <div className="bento-grid" style={{ marginTop: 8 }}>
      <AccentTile title="МОДЕЛЬ ГОТОВА" description="Метрики посчитаны на holdout, которого модель не видела" geometry={0}>
        <div style={{ marginTop: 20 }}><ArrowButton onClick={onOpen} title="Открыть модель" /></div>
      </AccentTile>
      <StatTile label="ROC-AUC / HOLDOUT" value={metrics.roc_auc !== undefined ? fmtShort(metrics.roc_auc, 3) : '—'} denominator={metrics.roc_auc !== undefined ? '' : 'нет'} />
      <StatTile label="LIFT VS BASELINE" value={metrics.lift !== undefined ? `+${fmtShort(metrics.lift * 100, 1)} п.п.` : '—'} denominator="" />
      <StatTile label="CONFORMAL COVERAGE" value={metrics.coverage !== undefined ? `${fmtShort(metrics.coverage * 100, 1)}%` : '—'} denominator={`ЦЕЛЬ ${Math.round((metrics.coverage_target || 0.9) * 100)}%`} />
      <div className="tile" style={{ gridColumn: 'span 12', display: 'flex', justifyContent: 'flex-end' }}>
        <button className="btn btn-ink" onClick={onOpen}>ОТКРЫТЬ СТРАНИЦУ МОДЕЛИ →</button>
      </div>
    </div>
  )
}
