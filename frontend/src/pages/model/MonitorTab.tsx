import { useEffect, useState } from 'react'
import { getMonitor, runMonitor, type ModelOut } from '../../api/endpoints'
import { DataTable, VerdictBadge, fmtShort } from '../../design/components'
import { api } from '../../api/client'

type Report = {
  id: number
  window_days: number
  status: string
  psi_prediction: number | null
  top_psi: Record<string, number>
  live_metrics: Record<string, unknown> | null
  report: Record<string, unknown> | null
  created_at: string
}

export default function MonitorTab({ model }: { model: ModelOut }) {
  const [reports, setReports] = useState<Report[]>([])
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [predictions, setPredictions] = useState<Record<string, unknown>[]>([])
  const [schedule, setSchedule] = useState({ enabled: false, interval_days: '30', mode: 'quick' })

  const refresh = () => {
    getMonitor(model.id).then(setReports)
    api<Record<string, unknown>[]>(`/api/models/${model.id}/predictions?limit=30`).then(setPredictions).catch(() => null)
  }
  useEffect(() => { refresh() }, [model.id])
  useEffect(() => {
    const s = (model.schedule || {}) as Record<string, unknown>
    setSchedule({ enabled: Boolean(s.enabled), interval_days: String(s.interval_days || 30), mode: String(s.mode || 'quick') })
  }, [model.schedule])

  const run = async () => {
    setBusy(true)
    try {
      await runMonitor(model.id)
      for (let i = 0; i < 20; i++) {
        await new Promise((r) => setTimeout(r, 3000))
        const list = await getMonitor(model.id)
        if (list.length && list[0].report) { setReports(list); break }
      }
    } finally { setBusy(false) }
  }

  return (
    <div className="bento-grid">
      <div className="tile" style={{ gridColumn: 'span 12', display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <span className="tile-label" style={{ marginRight: 'auto' }}>МОНІТОРИНГ: ДРЕЙФ И ЖИВЫЕ МЕТРИКИ</span>
        <label style={{ fontSize: 11, display: 'flex', gap: 6, alignItems: 'center' }}>
          <input type="checkbox" checked={schedule.enabled} onChange={(e) => setSchedule({ ...schedule, enabled: e.target.checked })} />
          переобучение по расписанию
        </label>
        {schedule.enabled && (
          <>
            <input style={{ width: 80 }} value={schedule.interval_days} onChange={(e) => setSchedule({ ...schedule, interval_days: e.target.value })} placeholder="дней" />
            <select value={schedule.mode} onChange={(e) => setSchedule({ ...schedule, mode: e.target.value })}>
              <option value="quick">quick</option><option value="full">full</option>
            </select>
          </>
        )}
        <button className="btn" onClick={async () => {
          await api(`/api/models/${model.id}`, { method: 'PATCH', json: { schedule: schedule.enabled ? { enabled: true, interval_days: Number(schedule.interval_days) || 30, mode: schedule.mode } : null } })
        }}>СОХРАНИТЬ РАСПИСАНИЕ</button>
        <button className="btn btn-ink" onClick={run} disabled={busy}>{busy ? 'СЧИТАЮ…' : 'ПРОВЕРИТЬ ДРЕЙФ СЕЙЧАС'}</button>
      </div>

      {reports.length > 0 ? reports.slice(0, 2).map((r) => (
        <div className="tile" key={r.id} style={{ gridColumn: 'span 6' }}>
          <div className="stat-head">
            <span className="tile-label">ОКНО {r.window_days}Д · {new Date(r.created_at).toLocaleDateString('ru-RU')}</span>
            <VerdictBadge verdict={r.status} />
          </div>
          <div style={{ marginTop: 10, fontSize: 12, lineHeight: 1.7 }}>
            <div>Прогнозов в окне: {String((r.report as Record<string, number>)?.n_predictions ?? '—')}</div>
            <div>Откликов (feedback): {String((r.report as Record<string, number>)?.n_feedback ?? '—')}</div>
            <div>Дрейф распределения прогнозов: PSI {r.psi_prediction !== null ? fmtShort(r.psi_prediction, 3) : '—'} (WARN &gt; 0.1, DRIFT &gt; 0.25)</div>
            {Object.keys(r.top_psi || {}).length > 0 && (
              <div>Топ PSI признаков: {Object.entries(r.top_psi).slice(0, 5).map(([k, v]) => `${k}=${fmtShort(v, 2)}`).join(', ')}</div>
            )}
            {r.live_metrics && Object.keys(r.live_metrics).length > 0 && (
              <div>Live-метрики: {Object.entries(r.live_metrics).map(([k, v]) => `${k}=${String(v)}`).join(' · ')}</div>
            )}
          </div>
        </div>
      )) : (
        <div className="tile" style={{ gridColumn: 'span 12' }}>
          <p className="muted">Отчётов дрейфа ещё нет — нажмите «Проверить дрейф». PSI считается по признакам и распределению прогнозов против обучающей выборки.</p>
        </div>
      )}

      <div className="tile" style={{ gridColumn: 'span 5' }}>
        <span className="tile-label">ОБРАТНАЯ СВЯЗЬ: ФАКТИЧЕСКИЕ ИСХОДЫ</span>
        <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>Приём фактов: по prediction_id из лога или по entity_id. Из них считаются live-метрики.</p>
        <textarea rows={4} style={{ width: '100%', marginTop: 10, fontFamily: 'var(--font)', fontSize: 11 }}
          placeholder='{"prediction_id": "prd_…", "actual": 1}' value={feedback} onChange={(e) => setFeedback(e.target.value)} />
        <button className="btn btn-ink" style={{ marginTop: 8 }} onClick={async () => {
          try {
            await api(`/api/models/${model.id}/feedback`, { json: JSON.parse(feedback) })
            setFeedback('')
            alert('Принято')
          } catch (e) { alert(String(e)) }
        }}>ОТПРАВИТЬ</button>
      </div>

      <div className="tile" style={{ gridColumn: 'span 7' }}>
        <span className="tile-label">ЛОГ ПРОГНОЗОВ (ПДн МАСКИРУЮТСЯ)</span>
        <div style={{ marginTop: 8, maxHeight: 300, overflowY: 'auto' }}>
          <DataTable
            columns={[
              { key: 'prediction_id', label: 'PREDICTION' },
              { key: 'mode', label: 'РЕЖИМ' },
              { key: 'entity_id', label: 'СУЩНОСТЬ' },
              { key: 'latency_ms', label: 'MS', align: 'right' },
              { key: 'created_at', label: 'ВРЕМЯ', format: (v) => new Date(String(v)).toLocaleString('ru-RU') },
            ]}
            rows={predictions as unknown as Record<string, unknown>[]}
          />
        </div>
      </div>

      {(model.versions || []).length > 1 && (
        <div className="tile" style={{ gridColumn: 'span 12' }}>
          <span className="tile-label">ВЕРСИИ И ОТКАТ</span>
          <DataTable
            columns={[
              { key: 'version', label: 'V', align: 'right' },
              { key: 'created_at', label: 'ОБУЧЕНА', format: (v) => new Date(String(v)).toLocaleString('ru-RU') },
              { key: 'guard_verdict', label: 'GUARD', format: (v) => <VerdictBadge verdict={String(v || 'OK')} /> },
              { key: 'active', label: 'АКТИВНА' },
            ]}
            rows={(model.versions || []).map((v) => ({ ...v, active: v.version === model.active_version ? '●' : '' }))}
          />
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            {(model.versions || []).filter((v) => v.version !== model.active_version).map((v) => (
              <button key={v.version} className="btn" onClick={async () => {
                await api(`/api/models/${model.id}/rollback`, { json: { version: v.version } })
                window.location.reload()
              }}>ОТКАТ К V{v.version}</button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
