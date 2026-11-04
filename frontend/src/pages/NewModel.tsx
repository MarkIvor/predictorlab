import { useEffect, useState } from 'react'
import { Upload, Database, ChevronRight, FileSpreadsheet, CheckCircle2, ArrowRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import {
  createModel, getDataset, listDatasets,
  patchModel, recheckModel, trainModel, uploadDataset, llmStatus,
  type DatasetOut, type ModelOut,
} from '../api/endpoints'
import { VerdictBadge, fmtShort } from '../design/components'
import Layout from './Layout'
import TrainingPanel from './model/TrainingPanel'

const STEPS = ['Данные', 'Цель', 'Проверка', 'Обучение', 'Результат'] as const

export default function NewModel() {
  const nav = useNavigate()
  const [step, setStep] = useState(0)
  const [dataset, setDataset] = useState<DatasetOut | null>(null)
  const [model, setModel] = useState<ModelOut | null>(null)
  const [error, setError] = useState('')
  const [trainingJob, setTrainingJob] = useState<string | null>(null)
  const [trainingMode, setTrainingMode] = useState<'quick' | 'full'>('quick')

  const go = (next: number) => { setError(''); setStep(Math.max(0, Math.min(4, next))) }

  // If training is active, show the TrainingPanel instead of everything else
  if (trainingJob && model) {
    return (
      <Layout>
        <TrainingPanel
          jobId={trainingJob}
          mode={trainingMode}
          onComplete={() => { setTrainingJob(null); go(4) }}
          onStop={() => { setTrainingJob(null); go(2) }}
        />
      </Layout>
    )
  }

  return (
    <Layout>
      {/* Step indicator */}
      <div style={{ display: 'flex', gap: 4, alignItems: 'center', marginBottom: 28, flexWrap: 'wrap' }}>
        {STEPS.map((s, i) => (
          <span key={s} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{
              padding: '10px 18px', fontSize: 14,
              color: i === step ? 'var(--ink)' : i < step ? 'var(--ok)' : 'var(--muted)',
              background: i === step ? 'var(--surface-2)' : 'transparent',
              borderRadius: 'var(--radius)',
              fontWeight: i === step ? 600 : 400,
            }}>
              {i + 1}. {s}
            </span>
            {i < STEPS.length - 1 && <ChevronRight size={14} color="var(--line)" />}
          </span>
        ))}
        <span style={{ marginLeft: 'auto', color: 'var(--muted)', fontSize: 13 }}>
          Шаг {step + 1} из 5
        </span>
      </div>

      {error && (
        <div style={{
          background: 'rgba(181,96,90,0.1)', border: '1px solid rgba(181,96,90,0.3)',
          borderRadius: 'var(--radius)', padding: '14px 20px', marginBottom: 16,
          color: 'var(--danger)', fontSize: 14,
        }}>{error}</div>
      )}

      {step === 0 && <DataStep onDataset={(d) => { setDataset(d); go(1) }} onError={setError} />}
      {step === 1 && dataset && (
        <TargetStep dataset={dataset} onModel={(m) => { setModel(m); go(2) }} onError={setError} onBack={() => go(0)} />
      )}
      {step === 2 && model && (
        <HealthStep model={model} onReady={(m) => { setModel(m); go(3) }} onOverride={(m) => { setModel(m); go(3) }} onBack={() => go(1)} />
      )}
      {step === 3 && model && (
        <ModeStep model={model} onStart={(mode, jobId) => { setTrainingMode(mode); setTrainingJob(jobId) }} onBack={() => go(2)} />
      )}
      {step === 4 && model && (
        <ResultStep modelId={model.id} onOpen={() => nav(`/m/${model.id}`)} />
      )}
    </Layout>
  )
}

/* === Step 1: Data === */
function DataStep({ onDataset, onError }: {
  onDataset: (d: DatasetOut) => void
  onError: (e: string) => void
}) {
  const [mode, setMode] = useState<'upload' | 'existing'>('upload')
  const [busy, setBusy] = useState(false)
  const [datasets, setDatasets] = useState<{ id: string; name: string; nrows: number }[]>([])
  const [file, setFile] = useState<File | null>(null)
  const [sampleRows, setSampleRows] = useState('')

  useEffect(() => { listDatasets().then(setDatasets) }, [])

  const doUpload = async () => {
    if (!file) return
    setBusy(true)
    try {
      const form = new FormData()
      form.append('file', file)
      if (sampleRows) form.append('sample_rows', sampleRows)
      onDataset(await uploadDataset(form))
    } catch (e) {
      onError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(500px, 1fr))', gap: 16 }}>
      <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 8 }}>
        <button onClick={() => setMode('upload')} style={{
          padding: '12px 24px', fontSize: 14, fontWeight: mode === 'upload' ? 600 : 400,
          background: mode === 'upload' ? 'var(--surface-2)' : 'var(--surface)',
          border: '1px solid var(--line)', borderRadius: 'var(--radius)',
          color: mode === 'upload' ? 'var(--ink)' : 'var(--muted)', cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: 8, fontFamily: 'var(--font)',
        }}>
          <Upload size={16} /> Загрузить файл
        </button>
        <button onClick={() => setMode('existing')} style={{
          padding: '12px 24px', fontSize: 14, fontWeight: mode === 'existing' ? 600 : 400,
          background: mode === 'existing' ? 'var(--surface-2)' : 'var(--surface)',
          border: '1px solid var(--line)', borderRadius: 'var(--radius)',
          color: mode === 'existing' ? 'var(--ink)' : 'var(--muted)', cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: 8, fontFamily: 'var(--font)',
        }}>
          <Database size={16} /> Существующий датасет
        </button>
      </div>

      {mode === 'upload' && (
        <div style={{
          background: 'var(--surface)', borderRadius: 'var(--radius)',
          padding: 32, border: '2px dashed var(--line)',
          gridColumn: 'span 2', textAlign: 'center',
        }}>
          <FileSpreadsheet size={48} color="var(--muted)" style={{ margin: '0 auto 16px' }} />
          <p style={{ fontSize: 16, color: 'var(--ink)', margin: '0 0 8px' }}>Загрузите CSV, XLSX или Parquet</p>
          <p style={{ fontSize: 13, color: 'var(--muted)', margin: '0 0 20px' }}>
            Кодировка и разделитель — автоматически (включая cp1251). ПДн исключаются из обучения.
          </p>
          <input type="file" accept=".csv,.xlsx,.parquet" onChange={(e) => setFile(e.target.files?.[0] || null)}
            style={{ fontSize: 14, padding: '12px', background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: 'var(--radius)', color: 'var(--ink)', width: '80%' }} />
          <div style={{ marginTop: 16, marginBottom: 20 }}>
            <input value={sampleRows} onChange={(e) => setSampleRows(e.target.value)}
              placeholder="Случайная выборка строк (опционально)"
              style={{ width: '80%', padding: '12px 16px', fontSize: 14, background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: 'var(--radius)', color: 'var(--ink)', fontFamily: 'var(--font)' }} />
          </div>
          <button onClick={doUpload} disabled={!file || busy} style={{
            padding: '14px 40px', fontSize: 14, fontWeight: 600,
            background: 'var(--ink)', color: '#101015', border: 'none',
            borderRadius: 'var(--radius)', cursor: busy ? 'wait' : 'pointer',
            fontFamily: 'var(--font)', opacity: !file || busy ? 0.4 : 1,
          }}>
            {busy ? 'Загружаем…' : 'Загрузить'}
          </button>
        </div>
      )}

      {mode === 'existing' && (
        <div style={{
          background: 'var(--surface)', borderRadius: 'var(--radius)',
          padding: 24, border: '1px solid var(--line)', gridColumn: 'span 2',
        }}>
          {datasets.length === 0 ? (
            <p style={{ color: 'var(--muted)', fontSize: 14, textAlign: 'center', padding: 40 }}>Датасетов нет</p>
          ) : (
            datasets.map((d) => (
              <div key={d.id} onClick={async () => {
                setBusy(true)
                try { onDataset(await getDataset(d.id)) } catch (e) { onError(String(e)) } finally { setBusy(false) }
              }}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '16px 20px', border: '1px solid var(--line)',
                  borderRadius: 'var(--radius)', marginBottom: 8, cursor: 'pointer',
                }}
                onMouseEnter={(e) => e.currentTarget.style.borderColor = 'var(--accent)'}
                onMouseLeave={(e) => e.currentTarget.style.borderColor = 'var(--line)'}
              >
                <div>
                  <div style={{ fontSize: 15, color: 'var(--ink)' }}>{d.name}</div>
                  <div style={{ fontSize: 13, color: 'var(--muted)' }}>{d.nrows.toLocaleString('ru-RU')} строк</div>
                </div>
                <ChevronRight size={18} color="var(--accent)" />
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}

/* === Step 2: Target === */
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

  const create = async () => {
    setBusy(true)
    try {
      if (eventTime !== (dataset.event_time_col || '')) {
        const { api } = await import('../api/client')
        await api(`/api/datasets/${dataset.id}`, { method: 'PATCH', json: { event_time_col: eventTime || null, entity_col: entity || null } })
      }
      onModel(await createModel({
        dataset_id: dataset.id, name: `Модель: ${dataset.name}`,
        target_col: target, task_type: taskType || null,
        event_time_col: eventTime || null, entity_col: entity || null,
      }))
    } catch (e) {
      onError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const inputStyle: React.CSSProperties = {
    width: '100%', padding: '14px', fontSize: 15,
    background: 'var(--bg)', border: '1px solid var(--line)',
    borderRadius: 'var(--radius)', color: 'var(--ink)',
    fontFamily: 'var(--font)',
  }
  const labelStyle: React.CSSProperties = {
    display: 'block', fontSize: 12, textTransform: 'uppercase',
    color: 'var(--muted)', marginBottom: 8,
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
      <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 28, border: '1px solid var(--line)' }}>
        <h3 style={{ fontSize: 14, textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 24 }}>Что предсказываем?</h3>
        <div style={{ marginBottom: 20 }}>
          <label style={labelStyle}>Колонка-цель</label>
          <select value={target} onChange={(e) => setTarget(e.target.value)} style={inputStyle}>
            <option value="">— выберите —</option>
            {usable.map((c) => <option key={c.name} value={c.name}>{c.name} ({c.type})</option>)}
          </select>
        </div>
        <div style={{ marginBottom: 20 }}>
          <label style={labelStyle}>Тип задачи</label>
          <select value={taskType} onChange={(e) => setTaskType(e.target.value)} style={inputStyle}>
            <option value="">Автоматически</option>
            <option value="binary">Бинарная классификация</option>
            <option value="regression">Регрессия</option>
          </select>
        </div>
        <div style={{ marginBottom: 20 }}>
          <label style={labelStyle}>Время события (для честного сплита)</label>
          <select value={eventTime} onChange={(e) => setEventTime(e.target.value)} style={inputStyle}>
            <option value="">— нет —</option>
            {dataset.columns.filter((c) => c.type === 'datetime').map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
          </select>
        </div>
        <div style={{ marginBottom: 24 }}>
          <label style={labelStyle}>Сущность (для group split)</label>
          <select value={entity} onChange={(e) => setEntity(e.target.value)} style={inputStyle}>
            <option value="">— нет —</option>
            {dataset.columns.filter((c) => c.type === 'id' || c.uniqueness > 0.5).map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
          </select>
        </div>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'space-between' }}>
          <button onClick={onBack} style={{ padding: '12px 24px', fontSize: 14, background: 'var(--surface-2)', color: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 'var(--radius)', cursor: 'pointer', fontFamily: 'var(--font)' }}>← Назад</button>
          <button onClick={create} disabled={!target || busy} style={{ padding: '12px 32px', fontSize: 14, fontWeight: 600, background: 'var(--ink)', color: '#101015', border: 'none', borderRadius: 'var(--radius)', cursor: 'pointer', fontFamily: 'var(--font)', opacity: !target || busy ? 0.4 : 1 }}>
            {busy ? 'Проверяем…' : 'Проверить данные →'}
          </button>
        </div>
      </div>
      <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 28, border: '1px solid var(--line)' }}>
        <h3 style={{ fontSize: 14, textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 24 }}>Датасет «{dataset.name}»</h3>
        <div style={{ display: 'flex', gap: 32, marginBottom: 24 }}>
          <div>
            <div style={{ fontSize: 40, fontWeight: 600, color: 'var(--ink)' }}>{dataset.nrows.toLocaleString('ru-RU')}</div>
            <div style={{ fontSize: 12, color: 'var(--muted)', textTransform: 'uppercase' }}>строк</div>
          </div>
          <div>
            <div style={{ fontSize: 40, fontWeight: 600, color: 'var(--ink)' }}>{dataset.ncols}</div>
            <div style={{ fontSize: 12, color: 'var(--muted)', textTransform: 'uppercase' }}>колонок</div>
          </div>
        </div>
        {llmOn && (
          <div style={{ marginTop: 24 }}>
            <label style={labelStyle}>Опишите цель словами (LLM)</label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="кто не купит в следующие 45 дней"
                style={{ flex: 1, padding: '12px 16px', fontSize: 14, background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: 'var(--radius)', color: 'var(--ink)', fontFamily: 'var(--font)' }} />
              <button onClick={async () => {
                setLlmBusy(true)
                try {
                  const { api } = await import('../api/client')
                  const r = await api<{ target_col: string | null; task_type: string | null }>('/api/llm/target-from-words', { json: { goal, dataset_id: dataset.id } })
                  if (r.target_col) setTarget(r.target_col)
                  if (r.task_type) setTaskType(r.task_type)
                } catch (e) { onError('LLM недоступна') } finally { setLlmBusy(false) }
              }} disabled={llmBusy || !goal} style={{ padding: '12px 20px', fontSize: 13, background: 'var(--accent)', color: 'var(--ink)', border: 'none', borderRadius: 'var(--radius)', cursor: 'pointer', fontFamily: 'var(--font)' }}>
                {llmBusy ? '…' : 'Предложить'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

/* === Step 3: Health === */
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
      const { getModel } = await import('../api/endpoints')
      const full = await getModel(current.id)
      full.guard_report = updated
      setCurrent(full)
      if (updated.verdict !== 'BLOCK') onReady(full)
    } finally { setBusy(false) }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h3 style={{ fontSize: 18, color: 'var(--ink)' }}>Проверка данных — Leakage Guard</h3>
        <VerdictBadge verdict={report?.verdict || 'OK'} />
      </div>
      {(report?.checks || []).length === 0 && (
        <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 40, textAlign: 'center', border: '1px solid var(--ok)' }}>
          <p style={{ color: 'var(--ok)', fontSize: 16 }}>Замечаний нет — утечек не найдено.</p>
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(400px, 1fr))', gap: 12 }}>
        {(report?.checks || []).map((c, i) => (
          <div key={i} style={{
            background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 20,
            border: `1px solid ${c.verdict === 'BLOCK' ? 'var(--danger)' : c.verdict === 'WARN' ? 'var(--warn)' : 'var(--line)'}`,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
              <span style={{ fontSize: 14, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--muted)' }}>
                {c.id.replace(/_/g, ' ')}
              </span>
              <VerdictBadge verdict={c.verdict} />
            </div>
            <p style={{ fontSize: 14, color: 'var(--ink)', lineHeight: 1.6, margin: 0 }}>{c.detail}</p>
          </div>
        ))}
      </div>
      {report?.verdict === 'BLOCK' && (
        <div style={{ background: 'rgba(181,96,90,0.1)', border: '1px solid var(--danger)', borderRadius: 'var(--radius)', padding: 24, marginTop: 20 }}>
          <h4 style={{ fontSize: 16, color: 'var(--danger)', margin: '0 0 12px' }}>Обнаружена утечка целевой переменной</h4>
          <p style={{ fontSize: 14, color: 'var(--ink)', lineHeight: 1.7, margin: '0 0 16px' }}>
            Результаты показаны не будут: модель выучила бы признак, который известен только ПОСЛЕ события.
          </p>
          <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
            <button onClick={excludeAndProceed} disabled={busy} style={{ padding: '12px 24px', fontSize: 14, fontWeight: 600, background: 'var(--ink)', color: '#101015', border: 'none', borderRadius: 'var(--radius)', cursor: 'pointer', fontFamily: 'var(--font)' }}>
              Исключить ({blockCols.join(', ')}) и продолжить
            </button>
            <label style={{ fontSize: 14, display: 'flex', gap: 8, alignItems: 'center', color: 'var(--muted)', cursor: 'pointer' }}>
              <input type="checkbox" checked={override} onChange={(e) => setOverride(e.target.checked)} style={{ transform: 'scale(1.4)' }} />
              Понимаю риск — снять блок
            </label>
            {override && (
              <button onClick={() => onOverride(current)} style={{ padding: '12px 24px', fontSize: 14, background: 'var(--surface)', color: 'var(--danger)', border: '1px solid var(--danger)', borderRadius: 'var(--radius)', cursor: 'pointer', fontFamily: 'var(--font)' }}>
                Продолжить с утечкой
              </button>
            )}
          </div>
        </div>
      )}
      {report?.verdict !== 'BLOCK' && (
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 24 }}>
          <button onClick={onBack} style={{ padding: '12px 24px', fontSize: 14, background: 'var(--surface-2)', color: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 'var(--radius)', cursor: 'pointer', fontFamily: 'var(--font)' }}>← Назад</button>
          <button onClick={() => onReady(current)} style={{ padding: '14px 32px', fontSize: 14, fontWeight: 600, background: 'var(--ink)', color: '#101015', border: 'none', borderRadius: 'var(--radius)', cursor: 'pointer', fontFamily: 'var(--font)' }}>
            Обучить модель →
          </button>
        </div>
      )}
    </div>
  )
}

/* === Step 4: Mode selection → starts TrainingPanel === */
function ModeStep({ model, onStart, onBack }: {
  model: ModelOut
  onStart: (mode: 'quick' | 'full', jobId: string) => void
  onBack: () => void
}) {
  const [busy, setBusy] = useState(false)

  const launch = async (mode: 'quick' | 'full') => {
    setBusy(true)
    try {
      const r = await trainModel(model.id, { mode })
      if (r.job_id) onStart(mode, r.job_id)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(380px, 1fr))', gap: 16 }}>
      <button onClick={() => launch('quick')} disabled={busy} style={{
        background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 32,
        border: '2px solid var(--line)', cursor: 'pointer', textAlign: 'left',
        fontFamily: 'var(--font)', transition: 'border-color 120ms',
      }}
        onMouseEnter={(e) => e.currentTarget.style.borderColor = 'var(--accent)'}
        onMouseLeave={(e) => e.currentTarget.style.borderColor = 'var(--line)'}
      >
        <div style={{ fontSize: 20, fontWeight: 600, color: 'var(--ink)' }}>Быстро</div>
        <div style={{ fontSize: 14, color: 'var(--muted)', marginTop: 8, lineHeight: 1.6 }}>
          CatBoost с дефолтными параметрами + линейная модель. Результат за 1–2 минуты.
        </div>
        <div style={{ marginTop: 16, fontSize: 13, color: 'var(--accent)' }}>~1–2 мин →</div>
      </button>

      <button onClick={() => launch('full')} disabled={busy} style={{
        background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 32,
        border: '2px solid var(--line)', cursor: 'pointer', textAlign: 'left',
        fontFamily: 'var(--font)', transition: 'border-color 120ms',
      }}
        onMouseEnter={(e) => e.currentTarget.style.borderColor = 'var(--accent)'}
        onMouseLeave={(e) => e.currentTarget.style.borderColor = 'var(--line)'}
      >
        <div style={{ fontSize: 20, fontWeight: 600, color: 'var(--ink)' }}>Полный поиск</div>
        <div style={{ fontSize: 14, color: 'var(--muted)', marginTop: 8, lineHeight: 1.6 }}>
          Optuna подбирает гиперпараметры CatBoost и LightGBM в пределах бюджета времени.
        </div>
        <div style={{ marginTop: 16, fontSize: 13, color: 'var(--accent)' }}>~10 мин →</div>
      </button>

      <div style={{ gridColumn: '1 / -1' }}>
        <button onClick={onBack} style={{
          padding: '12px 24px', fontSize: 14,
          background: 'var(--surface-2)', color: 'var(--ink)',
          border: '1px solid var(--line)', borderRadius: 'var(--radius)',
          cursor: 'pointer', fontFamily: 'var(--font)',
        }}>← Назад</button>
      </div>
    </div>
  )
}

/* === Step 5: Result === */
function ResultStep({ modelId, onOpen }: { modelId: number; onOpen: () => void }) {
  const [model, setModel] = useState<ModelOut | null>(null)
  useEffect(() => {
    import('../api/endpoints').then(({ getModel }) => getModel(modelId).then(setModel))
  }, [modelId])
  const metrics = (model?.metrics || {}) as Record<string, number>

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
      <div style={{
        gridColumn: '1 / -1',
        background: 'var(--accent)', borderRadius: 'var(--radius)',
        padding: '40px 32px', textAlign: 'center', color: 'var(--ink)',
      }}>
        <CheckCircle2 size={48} style={{ margin: '0 auto 16px' }} />
        <h2 style={{ fontSize: 28, textTransform: 'uppercase', letterSpacing: '0.02em', margin: 0 }}>
          Модель готова
        </h2>
        <p style={{ fontSize: 15, marginTop: 12, opacity: 0.85 }}>
          Метрики посчитаны на holdout, которого модель не видела.
        </p>
        <button onClick={onOpen} style={{
          marginTop: 24, padding: '16px 40px', fontSize: 16, fontWeight: 600,
          background: 'var(--ink)', color: '#101015', border: 'none',
          borderRadius: 'var(--radius)', cursor: 'pointer', fontFamily: 'var(--font)',
          display: 'inline-flex', alignItems: 'center', gap: 8,
        }}>
          Открыть модель <ArrowRight size={18} />
        </button>
      </div>
      <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 28, border: '1px solid var(--line)', textAlign: 'center' }}>
        <div style={{ fontSize: 12, color: 'var(--muted)', textTransform: 'uppercase' }}>ROC-AUC</div>
        <div style={{ fontSize: 48, fontWeight: 600, marginTop: 12, color: 'var(--ink)' }}>
          {metrics.roc_auc !== undefined ? fmtShort(metrics.roc_auc, 3) : '—'}
        </div>
      </div>
      <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 28, border: '1px solid var(--line)', textAlign: 'center' }}>
        <div style={{ fontSize: 12, color: 'var(--muted)', textTransform: 'uppercase' }}>LIFT</div>
        <div style={{ fontSize: 48, fontWeight: 600, marginTop: 12, color: 'var(--ok)' }}>
          {metrics.lift !== undefined ? `+${fmtShort(metrics.lift * 100, 1)}` : '—'}
        </div>
      </div>
      <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 28, border: '1px solid var(--line)', textAlign: 'center' }}>
        <div style={{ fontSize: 12, color: 'var(--muted)', textTransform: 'uppercase' }}>CONFORMAL</div>
        <div style={{ fontSize: 48, fontWeight: 600, marginTop: 12, color: 'var(--ink)' }}>
          {metrics.coverage !== undefined ? `${fmtShort(metrics.coverage * 100, 1)}%` : '—'}
        </div>
      </div>
    </div>
  )
}
