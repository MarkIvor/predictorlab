import type { ModelOut } from '../../api/endpoints'
import { AccentTile, BarChart, fmtShort } from '../../design/components'
import { HelpCircle, TrendingUp, Target, DollarSign, ShieldCheck } from 'lucide-react'

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

  const lift = isBinary ? (m.lift || 0) * 100 : (m.lift_pct || 0)

  return (
    <div>
      {/* What does this mean? — объяснение для нетехнического пользователя */}
      {ready && (
        <div style={{
          background: 'var(--surface)', borderRadius: 'var(--radius)', padding: '24px 28px',
          border: '1px solid var(--line)', marginBottom: 20,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
            <HelpCircle size={18} color="var(--accent)" />
            <span style={{ fontSize: 14, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--muted)' }}>
              Что это значит?
            </span>
          </div>
          <div style={{ fontSize: 15, color: 'var(--ink)', lineHeight: 1.7 }}>
            {isBinary ? (
              <>
                Модель предсказывает вероятность события «{model.target_col}» для каждого объекта.
                {' '}<b style={{ color: 'var(--accent)' }}>AUC = {fmtShort(heroMetric, 3)}</b> — это качество:
                чем ближе к 1, тем лучше модель отличает объекты с событием от объектов без события.
                {' '}Случайное угадывание = 0.5, идеальная модель = 1.0.
                {' '}<b style={{ color: 'var(--ok)' }}>Lift +{fmtShort(lift, 1)} п.п.</b> — насколько модель лучше случайного угадывания.
              </>
            ) : (
              <>
                Модель предсказывает числовое значение «{model.target_col}».
                {' '}<b style={{ color: 'var(--accent)' }}>MAE = {fmtShort(heroMetric, 0)}</b> — средняя ошибка прогноза в тех же единицах, что и таргет.
                {' '}Чем меньше — тем точнее. Наивный baseline (всегда предсказывать медиану) даёт MAE = {fmtShort(m.baseline_mae, 0)}.
                {' '}<b style={{ color: 'var(--ok)' }}>Lift {m.lift_pct > 0 ? '+' : ''}{fmtShort(m.lift_pct, 1)}%</b> — насколько модель точнее наивного.
              </>
            )}
          </div>
        </div>
      )}

      {/* Key metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12, marginBottom: 20 }}>
        <div style={{
          background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 24,
          border: '1px solid var(--line)', textAlign: 'center',
        }}>
          <Target size={20} color="var(--accent)" style={{ margin: '0 auto 8px' }} />
          <div style={{ fontSize: 12, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            {heroLabel}
          </div>
          <div style={{ fontSize: 48, fontWeight: 600, color: 'var(--ink)', marginTop: 8 }}>
            {ready ? fmtShort(heroMetric, 3) : '—'}
          </div>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 4 }}>HOLDOUT</div>
        </div>

        <div style={{
          background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 24,
          border: '1px solid var(--line)', textAlign: 'center',
        }}>
          <TrendingUp size={20} color="var(--ok)" style={{ margin: '0 auto 8px' }} />
          <div style={{ fontSize: 12, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            LIFT VS BASELINE
          </div>
          <div style={{ fontSize: 48, fontWeight: 600, color: 'var(--ok)', marginTop: 8 }}>
            {ready ? (isBinary ? `+${fmtShort(lift, 1)}` : `${lift > 0 ? '+' : ''}${fmtShort(lift, 1)}%`) : '—'}
          </div>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 4 }}>
            {isBinary ? 'П.П.' : ''}
          </div>
        </div>

        <div style={{
          background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 24,
          border: '1px solid var(--line)', textAlign: 'center',
        }}>
          <DollarSign size={20} color="var(--warn)" style={{ margin: '0 auto 8px' }} />
          <div style={{ fontSize: 12, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            PROFIT / PERIOD
          </div>
          <div style={{ fontSize: 48, fontWeight: 600, color: 'var(--warn)', marginTop: 8 }}>
            {model.threshold_info
              ? `+${fmtShort((model.threshold_info as Record<string, number>).profit_scaled ?? (model.threshold_info as Record<string, number>).profit, 1)}`
              : '—'}
          </div>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 4 }}>₽</div>
        </div>

        <div style={{
          background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 24,
          border: '1px solid var(--line)', textAlign: 'center',
        }}>
          <ShieldCheck size={20} color="var(--accent)" style={{ margin: '0 auto 8px' }} />
          <div style={{ fontSize: 12, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            CONFORMAL COVERAGE
          </div>
          <div style={{ fontSize: 48, fontWeight: 600, color: 'var(--ink)', marginTop: 8 }}>
            {ready ? `${fmtShort((m.coverage || 0) * 100, 1)}%` : '—'}
          </div>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 4 }}>
            ЦЕЛЬ {Math.round((m.coverage_target || 0.9) * 100)}%
          </div>
        </div>
      </div>

      {/* Charts */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(400px, 1fr))', gap: 12 }}>
        {ready && isBinary && (m.reliability || []).length > 0 && (
          <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 24, border: '1px solid var(--line)' }}>
            <span style={{ fontSize: 12, textTransform: 'uppercase', color: 'var(--muted)', letterSpacing: '0.04em' }}>
              Калибровка: предсказанная вероятность vs реальная
            </span>
            <p style={{ fontSize: 13, color: 'var(--muted)', margin: '8px 0 12px' }}>
              Если модель говорит «вероятность 70%», у скольких объектов событие действительно наступает?
            </p>
            <BarChart
              data={(m.reliability || []).map((r: { bin: number; predicted: number; actual: number }) => ({
                label: String(Math.round(r.predicted * 100)) + '%',
                value: Math.round(r.actual * 100),
                hint: `предсказано ${Math.round(r.predicted * 100)}% · фактически ${Math.round(r.actual * 100)}%`,
              }))}
              height={200}
              valueFormat={(v) => `${v}%`}
            />
          </div>
        )}

        {ready && topDrivers.length > 0 && (
          <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 24, border: '1px solid var(--line)' }}>
            <span style={{ fontSize: 12, textTransform: 'uppercase', color: 'var(--muted)', letterSpacing: '0.04em' }}>
              Что сильнее всего влияет на прогноз
            </span>
            <p style={{ fontSize: 13, color: 'var(--muted)', margin: '8px 0 12px' }}>
              SHAP-анализ: чем выше бар, тем сильнее признак влияет на прогноз.
            </p>
            <BarChart
              data={topDrivers.map((d) => ({
                label: d.feature.length > 16 ? d.feature.slice(0, 15) + '…' : d.feature,
                value: Math.round(d.impact * 1000) / 1000,
                hint: d.feature,
              }))}
              height={200}
            />
          </div>
        )}

        <AccentTile
          title={ready ? 'ЧЕСТНЫЙ ПРОГНОЗ' : 'НАЧНИТЕ ОБУЧЕНИЕ'}
          description={
            ready
              ? isBinary
                ? `Модель находит на ${Math.round(lift)} п.п. больше объектов с событием, чем случайный выбор.`
                : `Модель точнее наивного подхода на ${Math.abs(Math.round(lift))}%.`
              : 'Данные → цель → проверка → обучение в мастере'
          }
          geometry={1}
        />
      </div>
    </div>
  )
}
