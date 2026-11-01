import { useEffect, useState } from 'react'
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceDot } from 'recharts'
import { setProfit, type ModelOut } from '../../api/endpoints'
import { StatTile, fmtShort } from '../../design/components'

type Info = Record<string, any>

export default function Profit({ model, onSaved }: { model: ModelOut; onSaved: () => void }) {
  const existing: Info = (model.cost_matrix || {}) as Info
  const [form, setForm] = useState<Record<string, string>>({
    benefit_tp: String(existing.benefit_tp ?? ''),
    action_cost: String(existing.action_cost ?? ''),
    fn_cost: String(existing.fn_cost ?? ''),
    capacity: String(existing.capacity ?? ''),
    period_label: String((model.threshold_info as Info)?.period_label ?? 'holdout = 1 месяц'),
    scale: String((model.threshold_info as Info)?.scale ?? 1),
    cost_over: String(existing.cost_over ?? ''),
    cost_under: String(existing.cost_under ?? ''),
  })
  const [info, setInfo] = useState<Info>((model.threshold_info || {}) as Info)
  const [busy, setBusy] = useState(false)
  const [showFormulas, setShowFormulas] = useState(false)

  useEffect(() => { setInfo((model.threshold_info || {}) as Info) }, [model.threshold_info])

  if (model.task_type === 'multiclass') {
    return <div className="tile"><span className="tile-label">PROFIT</span><p className="muted" style={{ marginTop: 8 }}>Порог по деньгам поддерживается для бинарной классификации и регрессии.</p></div>
  }
  if (model.task_type === 'regression') {
    const reg = info as Record<string, number>
    return (
      <div className="bento-grid">
        <div className="tile" style={{ gridColumn: 'span 6' }}>
          <span className="tile-label">АСИММЕТРИЧНАЯ СТОИМОСТЬ ОШИБКИ</span>
          <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>Недопрогноз и перепрогноз стоят по-разному? Задайте стоимость на единицу ошибки.</p>
          <div className="form-row" style={{ marginTop: 12 }}>
            <div className="field"><label>Стоимость перепрогноза (за единицу)</label>
              <input value={form.cost_over ?? ''} onChange={(e) => setForm({ ...form, cost_over: e.target.value })} /></div>
            <div className="field"><label>Стоимость недопрогноза (за единицу)</label>
              <input value={form.cost_under ?? ''} onChange={(e) => setForm({ ...form, cost_under: e.target.value })} /></div>
          </div>
          <button className="btn btn-ink" disabled={busy || !form.cost_over || !form.cost_under} onClick={async () => {
            setBusy(true)
            try {
              const r = await setProfit(model.id, { cost_over: Number(form.cost_over), cost_under: Number(form.cost_under), scale: 1 })
              setInfo(r as Info)
              onSaved()
            } finally { setBusy(false) }
          }}>ПЕРЕСЧИТАТЬ</button>
        </div>
        {reg.cost_total !== undefined && (
          <StatTile label="ЭКОНОМИЯ VS МЕДИАНА" value={`${fmtShort(reg.saving, 1)} ₽`} note={`Стоимость прогнозов: ${fmtShort(reg.cost_total, 1)} ₽ против baseline ${fmtShort(reg.cost_baseline, 1)} ₽`} />
        )}
      </div>
    )
  }

  const curve: { threshold: number; profit: number }[] = info.curve || []
  const bestPoint = { threshold: info.threshold, profit: info.profit }

  return (
    <div className="bento-grid">
      <div className="tile" style={{ gridColumn: 'span 5' }}>
        <span className="tile-label">МАТРИЦА СТОИМОСТЕЙ, ₽</span>
        <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>Порог выбирается там, где прибыль максимальна — а не там, где F1 красивее.</p>
        <div className="form-row" style={{ marginTop: 12 }}>
          <div className="field"><label>Выгода от верно найденного (TP)</label><input value={form.benefit_tp} onChange={(e) => setForm({ ...form, benefit_tp: e.target.value })} /></div>
          <div className="field"><label>Стоимость действия (на TP и FP)</label><input value={form.action_cost} onChange={(e) => setForm({ ...form, action_cost: e.target.value })} /></div>
          <div className="field"><label>Потери от пропуска (FN)</label><input value={form.fn_cost} onChange={(e) => setForm({ ...form, fn_cost: e.target.value })} /></div>
          <div className="field"><label>Ёмкость: не больше объектов за период</label><input value={form.capacity} onChange={(e) => setForm({ ...form, capacity: e.target.value })} placeholder="опционально — top-K" /></div>
          <div className="field"><label>Период (подпись)</label><input value={form.period_label} onChange={(e) => setForm({ ...form, period_label: e.target.value })} /></div>
          <div className="field"><label>Масштаб к базе</label><input value={form.scale} onChange={(e) => setForm({ ...form, scale: e.target.value })} placeholder="напр. 12 (месяцы → год)" /></div>
        </div>
        <button className="btn btn-ink" disabled={busy || !form.benefit_tp || !form.action_cost} onClick={async () => {
          setBusy(true)
          try {
            const body: Record<string, unknown> = {
              benefit_tp: Number(form.benefit_tp), action_cost: Number(form.action_cost),
              fn_cost: Number(form.fn_cost || 0), period_label: form.period_label, scale: Number(form.scale || 1),
            }
            if (form.capacity) body.capacity = Number(form.capacity)
            const r = await setProfit(model.id, body)
            setInfo(r as Info)
            onSaved()
          } finally { setBusy(false) }
        }}>ПЕРЕСЧИТАТЬ ПОРОГ</button>
      </div>

      <div className="tile" style={{ gridColumn: 'span 7' }}>
        <span className="tile-label">КРИВАЯ ПРИБЫЛИ ПО ПОРОГУ (HOLDOUT)</span>
        {curve.length > 0 ? (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={curve} margin={{ top: 20, right: 16, left: 0, bottom: 4 }}>
              <XAxis dataKey="threshold" tick={{ fill: 'var(--muted)', fontSize: 10, fontFamily: 'var(--font)' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: 'var(--muted)', fontSize: 10, fontFamily: 'var(--font)' }} axisLine={false} tickLine={false} tickFormatter={(v) => fmtShort(v, 1)} />
              <Tooltip
                contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--line)', fontFamily: 'var(--font)', fontSize: 12 }}
                formatter={(v) => [fmtShort(Number(v), 1) + ' ₽', 'прибыль']}
              />
              <Line type="monotone" dataKey="profit" stroke="var(--stone)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
              {bestPoint.threshold !== undefined && (
                <ReferenceDot x={bestPoint.threshold} y={bestPoint.profit} r={4} fill="var(--accent)" stroke="none" />
              )}
            </LineChart>
          </ResponsiveContainer>
        ) : <p className="muted" style={{ marginTop: 12 }}>Задайте матрицу стоимостей, чтобы увидеть кривую.</p>}
      </div>

      {info.profit !== undefined && (
        <>
          <div className="tile" style={{ gridColumn: 'span 4' }}>
            <span className="tile-label">ПОРОГ ПО ПРИБЫЛИ</span>
            <div className="hero-digit" style={{ fontSize: 48, marginTop: 12 }}>{fmtShort(info.threshold, 3)}</div>
            <span className="denominator">ВМЕСТО 0.5</span>
          </div>
          <StatTile label="ПРИБЫЛЬ ЗА ПЕРИОД" value={`+${fmtShort(info.profit_scaled ?? info.profit, 1)}`} denominator="₽" note={`Против «наугад» +${fmtShort(info.vs_random, 1)} ₽ и «обрабатывать всех» +${fmtShort(info.vs_all, 1)} ₽ · ${info.period_label || ''}`} />
          <div className="tile" style={{ gridColumn: 'span 4' }}>
            <span className="tile-label">ФОРМУЛЫ</span>
            <button className="btn" style={{ marginTop: 8 }} onClick={() => setShowFormulas(!showFormulas)}>{showFormulas ? 'СКРЫТЬ' : 'РАСКРЫТЬ'}</button>
            {showFormulas && (
              <ul style={{ fontSize: 11, marginTop: 12, paddingLeft: 16 }}>
                {(info.formulas || []).map((f: string, i: number) => <li key={i} style={{ marginBottom: 6 }}>{f}</li>)}
              </ul>
            )}
            <p className="muted" style={{ fontSize: 11, marginTop: 10 }}>
              Допущения: TP {fmtShort(info.assumptions?.benefit_tp)} ₽ · действие {fmtShort(info.assumptions?.action_cost)} ₽ ·
              пропуск {fmtShort(info.assumptions?.fn_cost)} ₽ · holdout {info.assumptions?.n_holdout} объектов
              {info.capacity ? ` · ёмкость ${info.capacity}` : ''}
            </p>
          </div>
        </>
      )}
    </div>
  )
}
