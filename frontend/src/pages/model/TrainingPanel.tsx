import { useEffect, useRef, useState } from 'react'
import { CheckCircle2, Loader2, Square, Trophy, ArrowRight, Brain, Database, ShieldCheck, TrendingUp, Sparkles } from 'lucide-react'
import { sse } from '../../api/client'
import { cancelJob } from '../../api/endpoints'
import { fmtShort } from '../../design/components'

type Stage = {
  key: string
  label: string
  description: string
  icon: React.ReactNode
  estSec: number
}

const STAGES: Stage[] = [
  {
    key: 'prepare',
    label: 'Подготовка данных',
    description: 'Загружаем датасет в память, определяем типы колонок',
    icon: <Database size={20} />,
    estSec: 5,
  },
  {
    key: 'split',
    label: 'Разделение выборки',
    description: 'Out-of-time сплит: последние 20% по времени — контрольная выборка',
    icon: <ShieldCheck size={20} />,
    estSec: 10,
  },
  {
    key: 'candidate',
    label: 'Обучение кандидатов',
    description: 'CatBoost и линейная модель соревнуются на кросс-валидации',
    icon: <Brain size={20} />,
    estSec: 60,
  },
  {
    key: 'calibration',
    label: 'Калибровка вероятностей',
    description: 'Isotonic-регрессия: вероятности соответствуют реальности',
    icon: <TrendingUp size={20} />,
    estSec: 10,
  },
  {
    key: 'uncertainty',
    label: 'Конформальные интервалы',
    description: 'Считаем доверительные границы для каждого прогноза',
    icon: <Sparkles size={20} />,
    estSec: 15,
  },
  {
    key: 'evaluate',
    label: 'Оценка на holdout',
    description: 'Честная проверка на данных, которых модель не видела',
    icon: <TrendingUp size={20} />,
    estSec: 10,
  },
  {
    key: 'explain',
    label: 'SHAP-объяснения',
    description: 'Считаем вклад каждого признака в прогноз',
    icon: <Brain size={20} />,
    estSec: 20,
  },
  {
    key: 'done',
    label: 'Готово',
    description: 'Модель обучена и сохранена',
    icon: <CheckCircle2 size={20} />,
    estSec: 0,
  },
]

export default function TrainingPanel({
  jobId,
  mode,
  onComplete,
  onStop,
}: {
  jobId: string
  mode: 'quick' | 'full'
  onComplete: () => void
  onStop: () => void
}) {
  const [stageIdx, setStageIdx] = useState(0)
  const [leaderboard, setLeaderboard] = useState<{ name: string; cv_metric: number }[]>([])
  const [elapsed, setElapsed] = useState(0)
  const [done, setDone] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [stopped, setStopped] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const startTimeRef = useRef<number | null>(null)
  const startTime = { get current() { return startTimeRef.current ??= Date.now() } }

  useEffect(() => {
    const timer = setInterval(() => {
      if (!done) setElapsed(Math.round((Date.now() - startTime.current) / 1000))
    }, 1000)
    return () => clearInterval(timer)
  }, [done])

  useEffect(() => {
    abortRef.current = new AbortController()
    const signal = abortRef.current.signal

    const run = async () => {
      try {
        for await (const ev of sse(`/api/jobs/${jobId}/events`, signal)) {
          if (ev.event === 'stage') {
            const d = (ev.data as { data?: { stage?: string; message?: string } })?.data
            const stageKey = d?.stage
            const idx = STAGES.findIndex((s) => s.key === stageKey)
            if (idx >= 0) setStageIdx(idx)
          }
          if (ev.event === 'candidate') {
            const d = (ev.data as { data?: { leaderboard?: { name: string; cv_metric: number }[] } })?.data
            if (d?.leaderboard) setLeaderboard(d.leaderboard)
          }
          if (ev.event === 'ensemble') {
            const d = (ev.data as { data?: { ensemble?: { members: string[]; cv_metric: number } } })?.data
            if (d?.ensemble) {
              setLeaderboard((prev) => [
                ...prev,
                { name: `Ансамбль (${d.ensemble!.members.join(' + ')})`, cv_metric: d.ensemble!.cv_metric },
              ])
            }
          }
          if (ev.event === 'done') {
            const d = ev.data as { status?: string; error?: string }
            if (d?.status === 'error') {
              setErrorMsg(d.error || 'Ошибка обучения')
            } else {
              setDone(true)
              setStageIdx(STAGES.length - 1)
              setTimeout(() => onComplete(), 1500)
            }
          }
        }
      } catch {
        // stream ended
      }
    }

    run()
    return () => abortRef.current?.abort()
  }, [jobId])

  const handleStop = async () => {
    setStopped(true)
    abortRef.current?.abort()
    await cancelJob(jobId).catch(() => {})
    onStop()
  }
  const totalEstSec = mode === 'quick' ? 90 : 600
  const progressPct = Math.min(100, ((stageIdx + 1) / STAGES.length) * 100)
  const remainingEst = Math.max(0, Math.round(totalEstSec * (1 - progressPct / 100)))

  const formatTime = (s: number) => {
    if (s < 60) return `${s} сек`
    const m = Math.floor(s / 60)
    const sec = s % 60
    return sec > 0 ? `${m} мин ${sec} сек` : `${m} мин`
  }

  const isTraining = !done && !stopped && !errorMsg

  return (
    <div style={{
      maxWidth: 680,
      margin: '40px auto',
      background: 'var(--surface)',
      borderRadius: 'var(--radius)',
      border: '1px solid var(--line)',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        background: 'var(--accent)',
        padding: '32px 32px 28px',
        color: 'var(--ink)',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2 style={{ fontSize: 22, fontWeight: 600, margin: 0, textTransform: 'uppercase', letterSpacing: '0.02em' }}>
              {done ? 'Модель обучена' : errorMsg ? 'Ошибка' : stopped ? 'Остановлено' : 'Обучение'}
            </h2>
            <p style={{ fontSize: 14, margin: '8px 0 0', opacity: 0.85 }}>
              {done ? 'Метрики посчитаны на holdout. Открываем модель…' :
               errorMsg ? errorMsg :
               mode === 'quick' ? 'Режим «Быстро» — CatBoost + линейная модель' :
               'Режим «Полный поиск» — Optuna по CatBoost и LightGBM'}
            </p>
          </div>
          {!done && !stopped && !errorMsg && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              color: 'var(--ink)', fontSize: 20, fontWeight: 600,
            }}>
              <Loader2 size={24} className="spin" style={{ animation: 'spin 1.5s linear infinite' }} />
            </div>
          )}
        </div>
      </div>

      {/* Progress bar */}
      <div style={{ padding: '0 32px', background: 'var(--surface)' }}>
        <div style={{ height: 4, background: 'var(--surface-2)', borderRadius: 2, overflow: 'hidden' }}>
          <div style={{
            height: '100%', width: `${progressPct}%`,
            background: done ? 'var(--ok)' : 'var(--accent)',
            transition: 'width 500ms ease',
          }} />
        </div>
      </div>

      {/* Stage list */}
      <div style={{ padding: '24px 32px' }}>
        {STAGES.slice(0, STAGES.length - 1).map((stage, i) => {
          const isCurrent = i === stageIdx && isTraining
          const isPast = i < stageIdx
          const isDone = done || isPast

          return (
            <div key={stage.key} style={{
              display: 'flex', alignItems: 'flex-start', gap: 16,
              padding: '12px 0',
              opacity: isDone || isCurrent ? 1 : 0.4,
              transition: 'opacity 200ms',
            }}>
              {/* Icon */}
              <div style={{
                width: 40, height: 40, borderRadius: '50%',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: isDone ? 'var(--ok)' : isCurrent ? 'var(--accent)' : 'var(--surface-2)',
                color: isDone ? '#101015' : 'var(--ink)',
                flexShrink: 0,
                transition: 'background 200ms',
              }}>
                {isDone ? <CheckCircle2 size={18} /> : isCurrent ?
                  <Loader2 size={18} style={{ animation: 'spin 1.5s linear infinite' }} /> :
                  stage.icon}
              </div>

              {/* Text */}
              <div style={{ flex: 1 }}>
                <div style={{
                  fontSize: 15,
                  fontWeight: isCurrent ? 600 : 400,
                  color: isCurrent ? 'var(--ink)' : isDone ? 'var(--stone)' : 'var(--muted)',
                }}>
                  {stage.label}
                </div>
                <div style={{
                  fontSize: 13,
                  color: 'var(--muted)',
                  marginTop: 2,
                }}>
                  {stage.description}
                </div>
              </div>

              {/* Status */}
              <div style={{
                fontSize: 12,
                color: isDone ? 'var(--ok)' : isCurrent ? 'var(--accent)' : 'var(--muted)',
                whiteSpace: 'nowrap',
              }}>
                {isDone ? '✓' : isCurrent ? '…' : ''}
              </div>
            </div>
          )
        })}
      </div>

      {/* Leaderboard */}
      {leaderboard.length > 0 && (
        <div style={{
          padding: '20px 32px', borderTop: '1px solid var(--line)',
          background: 'var(--bg)',
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.06em',
            color: 'var(--muted)', marginBottom: 12,
          }}>
            <Trophy size={14} /> Лидерборд кандидатов
          </div>
          {leaderboard.map((c, i) => (
            <div key={c.name} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '10px 16px', marginBottom: 4,
              borderRadius: 'var(--radius)',
              background: i === 0 ? 'var(--accent)' : 'var(--surface)',
              color: i === 0 ? 'var(--ink)' : 'var(--muted)',
              fontSize: 14,
            }}>
              <span style={{ fontWeight: i === 0 ? 600 : 400 }}>
                {i === 0 && '🏆 '}{c.name}
              </span>
              <span style={{ fontWeight: 600 }}>
                {c.name.includes('Ансамбль') ? fmtShort(c.cv_metric, 4) :
                 c.cv_metric < 1 ? fmtShort(c.cv_metric, 4) : fmtShort(c.cv_metric, 1)}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Footer: time + stop */}
      <div style={{
        padding: '16px 32px',
        borderTop: '1px solid var(--line)',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        background: 'var(--surface)',
      }}>
        <div style={{ fontSize: 13, color: 'var(--muted)' }}>
          {isTraining ? (
            <>
              Прошло: <b style={{ color: 'var(--ink)' }}>{formatTime(elapsed)}</b>
              {' · '}осталось: ~<b style={{ color: 'var(--ink)' }}>{formatTime(remainingEst)}</b>
            </>
          ) : done ? (
            <span style={{ color: 'var(--ok)', display: 'flex', alignItems: 'center', gap: 6 }}>
              <CheckCircle2 size={16} /> Завершено за {formatTime(elapsed)}
            </span>
          ) : stopped ? (
            'Остановлено пользователем'
          ) : (
            errorMsg
          )}
        </div>
        {isTraining && (
          <button
            onClick={handleStop}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '10px 20px', fontSize: 13,
              background: 'var(--surface)', color: 'var(--danger)',
              border: '1px solid var(--danger)', borderRadius: 'var(--radius)',
              cursor: 'pointer', fontFamily: 'var(--font)',
            }}
          >
            <Square size={12} /> Остановить
          </button>
        )}
        {done && (
          <button
            onClick={onComplete}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '10px 24px', fontSize: 13, fontWeight: 600,
              background: 'var(--ink)', color: '#101015',
              border: 'none', borderRadius: 'var(--radius)',
              cursor: 'pointer', fontFamily: 'var(--font)',
            }}
          >
            Открыть модель <ArrowRight size={14} />
          </button>
        )}
      </div>
    </div>
  )
}
