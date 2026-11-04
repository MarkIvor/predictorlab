import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, ChevronRight } from 'lucide-react'
import { listModels, type ModelOut } from '../api/endpoints'
import { VerdictBadge, fmtShort } from '../design/components'
import Layout from './Layout'

function modelMetric(m: ModelOut): { hero: string; denom: string } {
  if (m.hero_metric !== undefined && m.hero_metric !== null) {
    return {
      hero: fmtShort(Number(m.hero_metric), 3),
      denom: m.task_type === 'binary' || m.task_type === 'multiclass' ? 'AUC' : 'MAE',
    }
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

  const readyCount = models.filter((m) => m.status === 'ready').length

  return (
    <Layout>
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: 16, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Ангар моделей
          </h2>
          <p style={{ fontSize: 14, color: 'var(--muted)', marginTop: 4 }}>
            {models.length} моделей · {readyCount} готово
          </p>
        </div>
        <button
          onClick={() => nav('/new')}
          style={{
            display: 'flex', alignItems: 'center', gap: '10px',
            background: 'var(--ink)', color: '#101015',
            border: 'none', borderRadius: 'var(--radius)',
            padding: '14px 24px', cursor: 'pointer',
            fontFamily: 'var(--font)', fontSize: '14px', fontWeight: 600,
            letterSpacing: '0.04em', textTransform: 'uppercase',
          }}
        >
          <Plus size={18} /> Новая модель
        </button>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
        gap: 16,
      }}>
        {loading && (
          <div style={{
            background: 'var(--surface)', borderRadius: 'var(--radius)',
            padding: 40, textAlign: 'center', color: 'var(--muted)',
            gridColumn: 'span 2',
          }}>
            Загрузка…
          </div>
        )}
        {!loading && models.length === 0 && (
          <div style={{
            background: 'var(--surface)', borderRadius: 'var(--radius)',
            padding: 48, textAlign: 'center', gridColumn: 'span 2',
            border: '1px dashed var(--line)',
          }}>
            <p style={{ color: 'var(--muted)', fontSize: 15, margin: '0 0 16px' }}>
              Моделей пока нет. Загрузите CSV — Leakage Guard поймает утечки, конформал даст честные интервалы.
            </p>
            <button onClick={() => nav('/new')} style={{
              background: 'var(--ink)', color: '#101015',
              border: 'none', borderRadius: 'var(--radius)',
              padding: '12px 24px', cursor: 'pointer',
              fontFamily: 'var(--font)', fontSize: '14px', fontWeight: 600,
            }}>
              Создать первую модель
            </button>
          </div>
        )}
        {models.map((m) => {
          const { hero, denom } = modelMetric(m)
          const profit = (m as unknown as { profit_scaled?: number }).profit_scaled
          const guard = m.guard_verdict
          return (
            <div
              key={m.id}
              onClick={() => nav(`/m/${m.id}`)}
              style={{
                background: 'var(--surface)',
                borderRadius: 'var(--radius)',
                padding: 24,
                cursor: 'pointer',
                border: '1px solid var(--line)',
                display: 'flex',
                flexDirection: 'column',
                minHeight: 200,
                transition: 'border-color 120ms ease',
              }}
              onMouseEnter={(e) => e.currentTarget.style.borderColor = 'var(--accent)'}
              onMouseLeave={(e) => e.currentTarget.style.borderColor = 'var(--line)'}
            >
              {/* Header row */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
                <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--ink)' }}>{m.name}</div>
                <VerdictBadge verdict={guard || 'OK'} />
              </div>

              {/* Hero metric */}
              <div style={{ display: 'flex', alignItems: 'baseline', marginBottom: 16 }}>
                <span style={{ fontSize: 48, lineHeight: 1, color: 'var(--ink)', letterSpacing: '-0.02em' }}>
                  {hero}
                </span>
                <span style={{ fontSize: 14, color: 'var(--muted)', marginLeft: 10 }}>/ {denom}</span>
              </div>

              {/* Bottom row */}
              <div style={{
                marginTop: 'auto',
                paddingTop: 14,
                borderTop: '1px solid var(--line)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}>
                <span style={{ fontSize: 13, color: 'var(--muted)' }}>
                  {profit !== undefined && profit !== null ? `+${fmtShort(profit)} ₽` : 'PROFIT —'}
                </span>
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: 13, color: 'var(--muted)' }}>
                  {m.status === 'ready' ? `V${m.active_version}` : m.status.toUpperCase()}
                  <ChevronRight size={14} color="var(--accent)" />
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </Layout>
  )
}
