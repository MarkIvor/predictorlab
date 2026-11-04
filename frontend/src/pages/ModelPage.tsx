import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronLeft, RotateCw, BarChart3, Sliders, DollarSign, Zap, Code2, FileText, Wrench, Activity } from 'lucide-react'
import { getModel, trainModel, rollbackModel, type ModelOut } from '../api/endpoints'
import { VerdictBadge } from '../design/components'
import Layout from './Layout'
import Overview from './model/Overview'
import Drivers from './model/Drivers'
import WhatIf from './model/WhatIf'
import Profit from './model/Profit'
import PredictTab from './model/PredictTab'
import ApiTab from './model/ApiTab'
import CardTab from './model/CardTab'
import ActionsTab from './model/ActionsTab'
import MonitorTab from './model/MonitorTab'
import TrainingPanel from './model/TrainingPanel'

const TABS = [
  { id: 'OVERVIEW', label: 'Обзор', icon: BarChart3 },
  { id: 'DRIVERS', label: 'Драйверы', icon: Activity },
  { id: 'WHAT-IF', label: 'What-If', icon: Sliders },
  { id: 'PROFIT', label: 'Деньги', icon: DollarSign },
  { id: 'PREDICT', label: 'Прогноз', icon: Zap },
  { id: 'API', label: 'API', icon: Code2 },
  { id: 'CARD', label: 'Карточка', icon: FileText },
  { id: 'ACTIONS', label: 'Действия', icon: Wrench },
  { id: 'MONITOR', label: 'Мониторинг', icon: Activity },
] as const

export default function ModelPage() {
  const { id, '*': tab } = useParams()
  const modelId = Number(id)
  const active = (TABS as readonly { id: string }[]).find((t) => t.id === tab)?.id || 'OVERVIEW'
  const [model, setModel] = useState<ModelOut | null>(null)
  const [error, setError] = useState('')
  const [trainingJob, setTrainingJob] = useState<string | null>(null)
  const [trainingMode, setTrainingMode] = useState<'quick' | 'full'>('quick')
  const [showModeSelector, setShowModeSelector] = useState(false)

  const reload = () => getModel(modelId).then(setModel).catch((e) => setError(String(e)))

  useEffect(() => { reload() }, [modelId])

  if (error) return <Layout><div className="tile">Модель не найдена</div></Layout>
  if (!model) return <Layout><p className="muted">Загрузка…</p></Layout>

  // Training panel replaces the whole page
  if (trainingJob) {
    return (
      <Layout>
        <TrainingPanel
          jobId={trainingJob}
          mode={trainingMode}
          onComplete={() => { setTrainingJob(null); reload() }}
          onStop={() => { setTrainingJob(null); reload() }}
        />
      </Layout>
    )
  }

  const startTraining = async (mode: 'quick' | 'full') => {
    setShowModeSelector(false)
    setTrainingMode(mode)
    try {
      const r = await trainModel(model.id, { mode })
      if (r.job_id) setTrainingJob(r.job_id)
    } catch (e) {
      setError(String(e))
    }
  }

  const rollback = async () => {
    const versions = (model.versions || []).filter((v) => v.version !== model.active_version)
    if (versions.length > 0) {
      await rollbackModel(model.id, versions[versions.length - 1].version)
      reload()
    }
  }

  return (
    <Layout>
      {/* Model header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <Link to="/" style={{ color: 'var(--muted)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4, fontSize: 13 }}>
            <ChevronLeft size={14} /> Ангар
          </Link>
          <h1 style={{ fontSize: 26, fontWeight: 600, color: 'var(--ink)', margin: '10px 0 6px' }}>
            {model.name}
          </h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <VerdictBadge verdict={model.guard_verdict} />
            <span style={{ color: 'var(--muted)', fontSize: 13 }}>
              {model.task_type === 'binary' ? 'Бинарная классификация' :
               model.task_type === 'regression' ? 'Регрессия' :
               model.task_type === 'multiclass' ? 'Мультикласс' : 'Временной ряд'}
              {' · '}таргет: {model.target_col}
              {' · '}{model.status === 'ready' ? `V${model.active_version}` : model.status}
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 12 }}>
          {(model.versions || []).filter((v) => v.version !== model.active_version).length > 0 && (
            <button onClick={rollback} style={{
              display: 'flex', alignItems: 'center', gap: 8,
              background: 'var(--surface)', color: 'var(--muted)',
              border: '1px solid var(--line)', borderRadius: 'var(--radius)',
              padding: '10px 16px', cursor: 'pointer',
              fontFamily: 'var(--font)', fontSize: 13,
            }}>
              <RotateCw size={14} /> Откатить
            </button>
          )}

          {/* Retrain button + mode selector dropdown */}
          <div style={{ position: 'relative' }}>
            <button onClick={() => setShowModeSelector(!showModeSelector)} style={{
              display: 'flex', alignItems: 'center', gap: 8,
              background: 'var(--ink)', color: '#101015',
              border: 'none', borderRadius: 'var(--radius)',
              padding: '10px 20px', cursor: 'pointer',
              fontFamily: 'var(--font)', fontSize: 13, fontWeight: 600,
            }}>
              <RotateCw size={14} /> Переобучить
            </button>

            {showModeSelector && (
              <div style={{
                position: 'absolute', top: '100%', right: 0, marginTop: 8,
                background: 'var(--surface)', border: '1px solid var(--line)',
                borderRadius: 'var(--radius)', zIndex: 100,
                minWidth: 280, overflow: 'hidden',
                boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
              }}>
                <button onClick={() => startTraining('quick')} style={{
                  width: '100%', padding: '16px 20px', textAlign: 'left',
                  background: 'none', border: 'none', cursor: 'pointer',
                  borderBottom: '1px solid var(--line)',
                  fontFamily: 'var(--font)',
                }}>
                  <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--ink)' }}>Быстро</div>
                  <div style={{ fontSize: 13, color: 'var(--muted)', marginTop: 4 }}>~1–2 минуты</div>
                </button>
                <button onClick={() => startTraining('full')} style={{
                  width: '100%', padding: '16px 20px', textAlign: 'left',
                  background: 'none', border: 'none', cursor: 'pointer',
                  fontFamily: 'var(--font)',
                }}>
                  <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--ink)' }}>Полный поиск</div>
                  <div style={{ fontSize: 13, color: 'var(--muted)', marginTop: 4 }}>~10 минут, Optuna</div>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Close dropdown on outside click */}
      {showModeSelector && (
        <div
          onClick={() => setShowModeSelector(false)}
          style={{ position: 'fixed', inset: 0, zIndex: 99 }}
        />
      )}

      {/* Status banner */}
      {model.status === 'training' && (
        <div style={{
          background: 'var(--accent)', borderRadius: 'var(--radius)',
          padding: '16px 24px', marginBottom: 20,
          color: 'var(--ink)', fontSize: 14,
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <RotateCw size={18} style={{ animation: 'spin 1.5s linear infinite' }} />
          Модель обучается. Дождитесь завершения или нажмите «Переобучить» для нового запуска.
        </div>
      )}
      {model.status === 'draft' && (
        <div style={{
          background: 'var(--surface)', borderRadius: 'var(--radius)',
          padding: '16px 24px', marginBottom: 20,
          border: '1px solid var(--line)',
          color: 'var(--muted)', fontSize: 14,
        }}>
          Модель ещё не обучена. Нажмите «Переобучить» чтобы запустить обучение.
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--line)', marginBottom: 24, overflowX: 'auto' }}>
        {TABS.map(({ id: tabId, label, icon: Icon }) => {
          const isActive = tabId === active
          return (
            <Link
              key={tabId}
              to={`/m/${modelId}/${tabId}`}
              style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '14px 20px',
                color: isActive ? 'var(--ink)' : 'var(--muted)',
                borderBottom: isActive ? '2px solid var(--accent)' : '2px solid transparent',
                fontSize: 14,
                textDecoration: 'none',
                whiteSpace: 'nowrap',
              }}
            >
              <Icon size={15} />
              {label}
            </Link>
          )
        })}
      </div>

      {/* Tab content */}
      {model.status !== 'ready' && active !== 'OVERVIEW' ? (
        <div style={{
          background: 'var(--surface)', borderRadius: 'var(--radius)',
          padding: 40, textAlign: 'center', color: 'var(--muted)',
        }}>
          Этот раздел доступен после обучения модели.
        </div>
      ) : (
        <>
          {active === 'OVERVIEW' && <Overview model={model} />}
          {active === 'DRIVERS' && <Drivers model={model} />}
          {active === 'WHAT-IF' && <WhatIf model={model} />}
          {active === 'PROFIT' && <Profit model={model} onSaved={reload} />}
          {active === 'PREDICT' && <PredictTab model={model} />}
          {active === 'API' && <ApiTab model={model} />}
          {active === 'CARD' && <CardTab model={model} />}
          {active === 'ACTIONS' && <ActionsTab model={model} onSaved={reload} />}
          {active === 'MONITOR' && <MonitorTab model={model} />}
        </>
      )}
    </Layout>
  )
}
