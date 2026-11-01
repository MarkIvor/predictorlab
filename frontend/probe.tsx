import type { ModelOut } from '../../api/endpoints'
import { BarChart } from '../../design/components'

type Metrics = Record<string, any>

export default function Drivers({ model }: { model: ModelOut }) {
  const m: Metrics = (model.metrics || {}) as Metrics
  const drivers: { feature: string; impact: number; direction: string }[] = m.drivers || []
  const dependence: Record<string, { feature: string; x: number[]; y: number[] }> = m.dependence || {}
  const top5 = drivers.slice(0, 5)

  if (drivers.length === 0) {
    return <div className="tile"><span className="tile-label">DRIVERS</span><p className="muted" style={{ marginTop: 8 }}>Драйверы появятся после обучения.</p></div>
  }

  return (
    <div className="bento-grid">
      <div className="tile" style={{ gridColumn: 'span 12 }}>
        <span className="tile-label">ГЛОБАЛЬНАЯ ВАЖНОСТЬ (СРЕДНИЙ |SHAP|)</span>
        <BarChart
          data={drivers.slice(0, 15).map((d) => ({
            label: d.feature.length > 18 ? d.feature.slice(0, 17) + '…' : d.feature,
            value: Math.round(d.impact * 1000) / 1000,
            hint: `${d.feature} · ${d.direction === 'up' ? 'повышает' : 'снижает'} прогноз`,
          }))}
          height={260}
        />
      </div>
      {top5.map((d) => {
        const dep = dependence[d.feature]
        return (
          <div className="tile" style={{ gridColumn: 'span 6 }} key={d.feature}>
            <span className="tile-label">DEPENDENCE · {d.feature.toUpperCase()}</span>
            {dep && dep.x && dep.x.length > 1 ? (
              <BarChart
                data={dep.x.map((x, i) => ({ label: String(Math.round(x * 100) / 100), value: Math.round(dep.y[i] * 1000) / 1000, hint: `${d.feature} = ${x}` }))}
                height={150}
              />
            ) : <p className="muted" style={{ marginTop: 8 }}>Нет данных зависимости</p>}
            <p className="muted" style={{ fontSize: 11 }}>Вклад признака в прогноз (SHAP): чем выше бар, тем сильнее значение меняло прогноз.</p>
          </div>
        )
      })}
    </div>
  )
}
