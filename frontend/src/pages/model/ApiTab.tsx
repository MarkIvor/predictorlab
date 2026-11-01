import { useEffect, useState } from 'react'
import { createKey, getSchema, listKeys, getSnippets, type ModelOut } from '../../api/endpoints'
import { StatTile } from '../../design/components'
import { api } from '../../api/client'

export default function ApiTab({ model }: { model: ModelOut }) {
  const [snippetTab, setSnippetTab] = useState<'curl' | 'python' | 'javascript' | 'one_c'>('curl')
  const [snippets, setSnippets] = useState<{ curl: string; python: string; javascript: string; one_c: string; url: string } | null>(null)
  const [keys, setKeys] = useState<{ id: number; name: string; prefix: string; revoked_at: string | null; model_ids: number[] }[]>([])
  const [newKey, setNewKey] = useState('')
  const [sandboxInput, setSandboxInput] = useState('')
  const [sandboxOut, setSandboxOut] = useState('')
  const [stats, setStats] = useState<{ requests: number; latency: number } | null>(null)

  const refresh = () => listKeys().then(setKeys)
  useEffect(() => {
    getSnippets(model.id).then(setSnippets)
    refresh()
    api<{ predictions: unknown[] }>(`/api/v1/models/${model.id}/predict`, { json: { data: [] } }).catch(() => null)
  }, [model.id])

  useEffect(() => {
    getSnippets(model.id).then(() => null)
    getSchema(model.id).then((s) => {
      setSandboxInput(JSON.stringify({ data: [s.example || {}], include: [] }, null, 2))
    })
  }, [model.id])

  const runSandbox = async () => {
    setSandboxOut('…')
    try {
      const body = JSON.parse(sandboxInput)
      const started = performance.now()
      const r = await api<Record<string, unknown>>(`/api/v1/models/${model.id}/predict`, { json: body })
      const ms = Math.round(performance.now() - started)
      setSandboxOut(JSON.stringify(r, null, 2))
      setStats({ requests: (r.predictions as unknown[])?.length || 0, latency: ms })
    } catch (e) {
      setSandboxOut(String(e))
    }
  }

  return (
    <div className="bento-grid">
      <div className="tile" style={{ gridColumn: 'span 8' }}>
        <span className="tile-label">СНИППЕТЫ ПОД СХЕМУ МОДЕЛИ</span>
        <div className="tabbar" style={{ marginTop: 10 }}>
          {(['curl', 'python', 'javascript', 'one_c'] as const).map((t) => (
            <button key={t} className={snippetTab === t ? 'tab active' : 'tab'} onClick={() => setSnippetTab(t)}>
              {t === 'one_c' ? '1С' : t.toUpperCase()}
            </button>
          ))}
        </div>
        {snippets && <pre className="snippet" style={{ marginTop: 10 }}>{snippets[snippetTab]}</pre>}
        <p className="muted" style={{ fontSize: 11, marginTop: 8 }}>Скопируйте свой ключ (создайте ниже) вместо pl_live_ВАШ_КЛЮЧ. Сниппеты выполняются без правок.</p>
      </div>

      <div className="tile" style={{ gridColumn: 'span 4' }}>
        <span className="tile-label">API-КЛЮЧИ</span>
        <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>Ключ хранится хэшем и показывается один раз. Доступ — к выбранным моделям.</p>
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <input style={{ flex: 1 }} value={newKey} onChange={(e) => setNewKey(e.target.value)} placeholder="имя ключа" />
          <button className="btn btn-ink" onClick={async () => {
            const r = await createKey({ name: newKey || 'Ключ', model_ids: [model.id] })
            setSandboxOut((prev) => prev)
            alert(`Ключ создан (сохраните — больше не покажем):\n${r.key}`)
            setNewKey('')
            refresh()
          }}>СОЗДАТЬ</button>
        </div>
        <div style={{ marginTop: 12 }}>
          {keys.map((k) => (
            <div className="leaderboard-row" key={k.id}>
              <span>{k.prefix}… {k.revoked_at ? '(отозван)' : ''}</span>
              <span className="muted">{k.name}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="tile" style={{ gridColumn: 'span 12' }}>
        <span className="tile-label">ПЕСОЧНИЦА</span>
        <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          Запрос уходит от вашего имени (cookie-сессия). Пример тела: {'{ "data": [ { … } ], "include": ["reasons"] }'}
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 10 }}>
          <textarea rows={12} value={sandboxInput} onChange={(e) => setSandboxInput(e.target.value)} style={{ fontFamily: 'var(--font)', fontSize: 11 }} />
          <div>
            <button className="btn btn-ink" onClick={runSandbox}>ОТПРАВИТЬ</button>
            <pre className="snippet" style={{ marginTop: 10, maxHeight: 300, overflow: 'auto' }}>{sandboxOut || '—'}</pre>
          </div>
        </div>
      </div>

      {stats && (
        <>
          <StatTile label="REQUESTS" value={stats.requests} denominator="LAST CALL" />
          <StatTile label="AVG LATENCY" value={`${stats.latency} мс`} note="Измерено в песочнице только что" />
        </>
      )}
      <div className="tile" style={{ gridColumn: 'span 12' }}>
        <span className="tile-label">OPENAPI</span>
        <p style={{ fontSize: 12, marginTop: 8 }}>
          Полная документация контракта: <a href="/docs" target="_blank" rel="noreferrer">/docs</a> · стилизованная страница: <a href="/docs-page" target="_blank" rel="noreferrer">/docs-page</a>
        </p>
      </div>
    </div>
  )
}
