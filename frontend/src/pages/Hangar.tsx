import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listModels, type ModelOut } from '../api/endpoints'
import { CTATile, StatTile, VerdictBadge, fmtShort } from '../design/components'
import Layout from './Layout'

function modelMetric(m: ModelOut): { hero: string; denom: string } {
  if (m.hero_metric !== undefined && m.hero_metric !== null) {
    return { hero: fmtShort(Number(m.hero_metric), 3), denom: m.task_type === 'binary' || m.task_type === 'multiclass' ? 'AUC' : 'MAE' }
  }
  return { hero: '—', denom: m.task_type === 'binary' || m.task_type === 'multiclass' ? 'AUC' : 'MAE' }
}

export default function Hangar() {
  const [models, setModels] = useState<ModelOut[]>([])
  const [loading, setLoading] = useState(true)
  const nav = useNavigate()

  useEffect(() => {
    listModels().then(setModels).finally(() => setLoading(false))
  }, [])

  return (
    <Layout>
      <div className="bento-grid" style={{ marginTop: 8 }}>
        <CTATile title="NEW MODEL" subtitle="Загрузи данные → цель → честная модель" onClick={() => nav('/new')} />
        {loading && <div className="tile muted" style={{ gridColumn: 'span 6' }}>Загрузка…</div>}
        {!loading && models.length === 0 && (
          <div className="tile" style={{ gridColumn: 'span 6' }}>
            <span className="tile-label">EMPTY HANGAR</span>
            <p className="muted" style={{ margin: '12px 0' }}>Моделей пока нет. Загрузите CSV и обучите первую — утечки поймает Leakage Guard.</p>
          </div>
        )}
        {models.map((m) => {
          const { hero, denom } = modelMetric(m)
          const profit = (m as unknown as { profit_scaled?: number }).profit_scaled
          const guard = m.guard_verdict
          return (
            <div key={m.id} className="tile" style={{ cursor: 'pointer' }} onClick={() => nav(`/m/${m.id}`)}>
              <div className="stat-head">
                <span className="tile-label">{m.name}</span>
                <VerdictBadge verdict={guard || 'OK'} />
              </div>
              <div className="stat-value" style={{ marginTop: 14 }}>
                <span className="hero-digit-sm">{hero}</span>
                <span className="denominator">/ {denom}</span>
              </div>
              <div className="stat-total" style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>PROFIT {profit !== undefined && profit !== null ? `+${fmtShort(profit)} ₽ / MO` : '—'}</span>
                <span className="muted">{m.status === 'ready' ? `V${m.active_version}` : m.status.toUpperCase()}</span>
              </div>
            </div>
          )
        })}
      </div>
      <div style={{ marginTop: 16 }}>
        <StatTile label="TOTAL" value={models.length} denominator="MODELS" total={`${models.filter((m) => m.status === 'ready').length} READY / ${models.length} TOTAL`} />
      </div>
    </Layout>
  )
}
