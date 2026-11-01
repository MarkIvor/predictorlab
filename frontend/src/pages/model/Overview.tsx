import type { ModelOut } from '../../api/endpoints'
import { AccentTile, BarChart, StatTile, fmtShort } from '../../design/components'

type Metrics = Record<string, any>

export default function Overview({ model }: { model: ModelOut }) {
  const m: Metrics = (model.metrics || {}) as Metrics
  const isBinary = model.task_type === 'binary'
  const isRegression = model.task_type === 'regression'
  const isTs = model.task_type === 'timeseries'
  const ready = model.status === 'ready'

  const heroMetric = isBinary ? m.roc_auc : isTs ? m.mae : isRegression ? m.mae : m.accuracy
  const heroLabel = isBinary ? 'AUC' : 'MAE'

  const drivers: { feature: string; impact: number }[] = m.drivers || []
  const topDrivers = drivers.slice(0, 8)

  const insight = isBinary
    ? `Модель находит ${m.roc_auc ? Math.round((m.roc_auc - 0.5) * 200) : 0}% больше положительных объектов, чем случайный выбор`
    : `Ошибка модели на ${m.lift_pct ? Math.abs(Math.round(m.lift_pct)) : 0}% ${m.lift_pct > 0 ? 'ниже' : 'выше'}, чем у наивного baseline`

  return (
    <div className="bento-grid">
      <div className="tile" style={{ gridColumn: 'span 4', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        {ready ? (
          <>
            <div className="hero-digit">{fmtShort(heroMetric, 3)}</div>
            <span className="tile-label muted" style={{ marginTop: 8 }}>{heroLabel} / HOLDOUT</span>
          </>
        ) : <span className="muted">Модель ещё не обучена</span>}
      </div>
      <StatTile label="LIFT VS BASELINE" value={ready ? (isBinary ? `+${fmtShort((m.lift || 0) * 100, 1)} п.п.` : `${m.lift_pct > 0 ? '+' : ''}${fmtShort(m.lift_pct, 1)}%`) : '—'} note={(m.baseline || {}).detail} />
      <StatTile label="PROFIT / PERIOD" value={model.threshold_info ? `+${fmtShort((model.threshold_info as Record<string, number>).profit_scaled ?? (model.threshold_info as Record<string, number>).profit, 1)} ₽` : '—'} note="Задайте матрицу стоимостей на вкладке PROFIT" />
      <StatTile label="CONFORMAL COVERAGE" value={ready ? `${fmtShort((m.coverage || 0) * 100, 1)}%` : '—'} denominator={`ЦЕЛЬ ${Math.round((m.coverage_target || 0.9) * 100)}%`} />

      {ready && isBinary && (
        <div className="tile" style={{ gridColumn: 'span 5' }}>
          <span className="tile-label">RELIABILITY (КАЛИБРОВКА)</span>
          <BarChart
            data={((m.reliability || []) as { bin: number; predicted: number; actual: number; count: number }[]).map((r) => ({
              label: String(r.bin), value: Math.round(r.actual * 100), hint: `предсказано ${Math.round(r.predicted * 100)}% · фактически ${Math.round(r.actual * 100)}% · n=${r.count ?? '—'}`,
            }))}
            height={160}
            valueFormat={(v) => `${v}%`}
          />
        </div>
      )}
      {ready && topDrivers.length > 0 && (
        <div className="tile" style={{ gridColumn: 'span 7' }}>
          <span className="tile-label">ТОП-ДРАЙВЕРЫ (SHAP)</span>
          <BarChart
            data={topDrivers.map((d) => ({ label: d.feature.length > 14 ? d.feature.slice(0, 13) + '…' : d.feature, value: Math.round(d.impact * 1000) / 1000, hint: d.feature }))}
            height={160}
          />
        </div>
      )}
      <AccentTile title={ready ? 'ЧЕСТНЫЙ ПРОГНОЗ' : 'НАЧНИТЕ ОБУЧЕНИЕ'} description={ready ? insight : 'Данные → цель → проверка → обучение в мастере'} geometry={1} />
    </div>
  )
}
