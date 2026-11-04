import { useEffect, useState } from 'react'
import { Users, Brain, Webhook, Key, Database } from 'lucide-react'
import {
  adminStats, adminLlm, adminPutLlm, adminUsers, adminCreateUser, adminPatchUser,
  adminWebhooks, adminCreateWebhook, listKeys, listConnections, llmStatus, mcpConfig
} from '../api/endpoints'
import { DataTable, VerdictBadge, fmtShort } from '../design/components'
import Layout from './Layout'

type Tab = 'users' | 'llm' | 'keys' | 'connections' | 'webhooks'

export default function Admin() {
  const [tab, setTab] = useState<Tab>('users')
  const [stats, setStats] = useState<Record<string, number> | null>(null)
  const [users, setUsers] = useState<{ id: number; email: string; display_name: string; role: string; must_change_password: boolean }[]>([])
  const [llm, setLlm] = useState<{ enabled: boolean; base_url: string; model: string; api_key_masked: string } | null>(null)
  const [llmForm, setLlmForm] = useState({ base_url: '', model: '', api_key: '' })
  const [hooks, setHooks] = useState<{ id: number; url: string; model_id: number | null; events: string[] }[]>([])
  const [hookUrl, setHookUrl] = useState('')
  const [keys, setKeys] = useState<{ id: number; name: string; prefix: string; revoked_at: string | null }[]>([])
  const [connections, setConnections] = useState<{ id: number; name: string; db_type: string }[]>([])
  const [newUser, setNewUser] = useState({ email: '', password: '', role: 'viewer' })
  const [mcp, setMcp] = useState<{ enabled: boolean; claude_desktop?: string; cursor?: string; http_command?: string } | null>(null)
  const [llmEnabled, setLlmEnabled] = useState(false)
  const [msg, setMsg] = useState('')

  const refresh = async () => {
    setStats(await adminStats())
    setUsers(await adminUsers())
    const l = await adminLlm()
    setLlm(l)
    setLlmForm((f) => ({ ...f, base_url: l.base_url, model: l.model }))
    setHooks(await adminWebhooks())
    setKeys(await listKeys())
    setConnections(await listConnections())
    setMcp(await mcpConfig())
    const st = await llmStatus()
    setLlmEnabled(st.enabled)
  }

  useEffect(() => { refresh() }, [])

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'users', label: 'Пользователи', icon: <Users size={16} /> },
    { id: 'llm', label: 'LLM', icon: <Brain size={16} /> },
    { id: 'keys', label: 'API-ключи', icon: <Key size={16} /> },
    { id: 'connections', label: 'Подключения', icon: <Database size={16} /> },
    { id: 'webhooks', label: 'Вебхуки', icon: <Webhook size={16} /> },
  ]

  const inputStyle: React.CSSProperties = {
    padding: '10px 14px', fontSize: 14, width: '100%',
    background: 'var(--bg)', border: '1px solid var(--line)',
    borderRadius: 'var(--radius)', color: 'var(--ink)',
    fontFamily: 'var(--font)',
  }

  const labelStyle: React.CSSProperties = {
    display: 'block', fontSize: 12, letterSpacing: '0.06em',
    textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 6,
  }

  const btnStyle: React.CSSProperties = {
    padding: '12px 20px', fontSize: 13, fontWeight: 600,
    background: 'var(--ink)', color: '#101015', border: 'none',
    borderRadius: 'var(--radius)', cursor: 'pointer', fontFamily: 'var(--font)',
  }

  return (
    <Layout>
      {/* Stats strip */}
      {stats && (
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
          gap: 12, marginBottom: 28,
        }}>
          {[
            { label: 'Пользователи', value: stats.users || 0 },
            { label: 'Модели', value: `${stats.ready_models || 0}/${stats.models || 0}` },
            { label: 'Прогнозы / 24ч', value: fmtShort(stats.predictions_24h || 0, 0) },
            { label: 'Ср. задержка', value: `${stats.avg_latency_ms || 0} мс` },
          ].map((s) => (
            <div key={s.label} style={{
              background: 'var(--surface)', borderRadius: 'var(--radius)',
              padding: '20px', border: '1px solid var(--line)',
            }}>
              <div style={{ fontSize: 12, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{s.label}</div>
              <div style={{ fontSize: 32, fontWeight: 600, marginTop: 8, color: 'var(--ink)' }}>{s.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Tab bar */}
      <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--line)', marginBottom: 24, overflowX: 'auto' }}>
        {tabs.map(({ id, label, icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '14px 20px', background: 'none', border: 'none',
              color: tab === id ? 'var(--ink)' : 'var(--muted)',
              borderBottom: tab === id ? '2px solid var(--accent)' : '2px solid transparent',
              fontSize: 14, cursor: 'pointer', fontFamily: 'var(--font)',
              whiteSpace: 'nowrap',
            }}
          >
            {icon} {label}
          </button>
        ))}
      </div>

      {/* === ПОЛЬЗОВАТЕЛИ === */}
      {tab === 'users' && (
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 }}>
          <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 24, border: '1px solid var(--line)' }}>
            <h3 style={{ fontSize: 14, textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 16 }}>Список</h3>
            <DataTable
              columns={[
                { key: 'email', label: 'Email' },
                { key: 'role', label: 'Роль', format: (v, row) => (
                  <select
                    value={String(v)}
                    onChange={async (e) => { await adminPatchUser((row as { id: number }).id, { role: e.target.value }); refresh() }}
                    style={{ background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: 'var(--radius)', padding: '6px 10px', color: 'var(--ink)', fontSize: 13 }}
                  >
                    <option value="admin">admin</option>
                    <option value="builder">builder</option>
                    <option value="viewer">viewer</option>
                  </select>
                )},
                { key: 'must_change_password', label: 'Пароль', format: (v) => v ? 'сменить' : 'ок' },
              ]}
              rows={users as unknown as Record<string, unknown>[]}
            />
          </div>
          <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 24, border: '1px solid var(--line)' }}>
            <h3 style={{ fontSize: 14, textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 16 }}>Новый пользователь</h3>
            <div style={{ marginBottom: 12 }}>
              <label style={labelStyle}>Email</label>
              <input value={newUser.email} onChange={(e) => setNewUser({ ...newUser, email: e.target.value })} style={inputStyle} />
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={labelStyle}>Пароль (≥8)</label>
              <input value={newUser.password} onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} style={inputStyle} type="password" />
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={labelStyle}>Роль</label>
              <select value={newUser.role} onChange={(e) => setNewUser({ ...newUser, role: e.target.value })} style={inputStyle}>
                <option value="viewer">viewer — только просмотр</option>
                <option value="builder">builder — создание моделей</option>
                <option value="admin">admin — полный доступ</option>
              </select>
            </div>
            <button onClick={async () => {
              await adminCreateUser(newUser)
              setNewUser({ email: '', password: '', role: 'viewer' })
              refresh()
            }} style={{ ...btnStyle, width: '100%' }}>
              Создать
            </button>
          </div>
        </div>
      )}

      {/* === LLM === */}
      {tab === 'llm' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 24, border: '1px solid var(--line)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h3 style={{ fontSize: 14, textTransform: 'uppercase', color: 'var(--muted)' }}>Подключение</h3>
              <VerdictBadge verdict={llmEnabled ? 'OK' : 'WARN'} />
            </div>
            <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.6, marginBottom: 20 }}>
              Любой OpenAI-совместимый API. Без LLM всё работает офлайн —
              LLM только для текстов, предложений по фичам и семантической проверки колонок.
              Сырые строки данных не уходят.
            </p>
            <div style={{ marginBottom: 16 }}>
              <label style={labelStyle}>Base URL</label>
              <input value={llmForm.base_url} onChange={(e) => setLlmForm({ ...llmForm, base_url: e.target.value })} style={inputStyle} placeholder="https://api.deepseek.com/v1" />
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={labelStyle}>Модель</label>
              <input value={llmForm.model} onChange={(e) => setLlmForm({ ...llmForm, model: e.target.value })} style={inputStyle} placeholder="deepseek-chat" />
            </div>
            <div style={{ marginBottom: 20 }}>
              <label style={labelStyle}>API Key {llm?.api_key_masked && <span style={{ color: 'var(--ok)' }}>({llm.api_key_masked})</span>}</label>
              <input type="password" value={llmForm.api_key} onChange={(e) => setLlmForm({ ...llmForm, api_key: e.target.value })} style={inputStyle} placeholder="sk-..." />
            </div>
            <button onClick={async () => { await adminPutLlm(llmForm); refresh(); setMsg('LLM настроена') }} style={{ ...btnStyle, width: '100%' }}>
              Сохранить
            </button>
            {msg && <p style={{ color: 'var(--ok)', fontSize: 13, marginTop: 12 }}>{msg}</p>}
          </div>
          <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 24, border: '1px solid var(--line)' }}>
            <h3 style={{ fontSize: 14, textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 16 }}>MCP-сервер</h3>
            {mcp?.enabled ? (
              <>
                <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 16 }}>Конфиги для Claude Desktop и Cursor:</p>
                <div style={{ marginBottom: 16 }}>
                  <label style={labelStyle}>Claude Desktop</label>
                  <pre style={{ ...inputStyle, padding: 14, fontSize: 12, whiteSpace: 'pre-wrap', overflow: 'auto', maxHeight: 150 }}>{mcp.claude_desktop}</pre>
                </div>
                <div style={{ marginBottom: 16 }}>
                  <label style={labelStyle}>Cursor</label>
                  <pre style={{ ...inputStyle, padding: 14, fontSize: 12, whiteSpace: 'pre-wrap', overflow: 'auto', maxHeight: 150 }}>{mcp.cursor}</pre>
                </div>
                <div>
                  <label style={labelStyle}>HTTP-запуск</label>
                  <pre style={{ ...inputStyle, padding: 14, fontSize: 12, whiteSpace: 'pre-wrap' }}>{mcp.http_command}</pre>
                </div>
              </>
            ) : (
              <p style={{ fontSize: 13, color: 'var(--muted)' }}>
                Задайте MCP_AUTH_TOKEN в .env, чтобы включить MCP-сервер.
              </p>
            )}
          </div>
        </div>
      )}

      {/* === API-КЛЮЧИ === */}
      {tab === 'keys' && (
        <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 24, border: '1px solid var(--line)' }}>
          <h3 style={{ fontSize: 14, textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 16 }}>
            Все ключи ({keys.length})
          </h3>
          <DataTable
            columns={[
              { key: 'prefix', label: 'Ключ' },
              { key: 'name', label: 'Имя' },
              { key: 'revoked_at', label: 'Статус', format: (v) => v ? 'отозван' : 'активен' },
            ]}
            rows={keys as unknown as Record<string, unknown>[]}
          />
        </div>
      )}

      {/* === ПОДКЛЮЧЕНИЯ === */}
      {tab === 'connections' && (
        <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 24, border: '1px solid var(--line)' }}>
          <h3 style={{ fontSize: 14, textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 16 }}>
            Подключения к БД ({connections.length})
          </h3>
          <DataTable
            columns={[
              { key: 'name', label: 'Имя' },
              { key: 'db_type', label: 'Тип' },
            ]}
            rows={connections as unknown as Record<string, unknown>[]}
          />
          <p style={{ fontSize: 13, color: 'var(--muted)', marginTop: 16 }}>
            Подключения создаются в мастере новой модели → «Собрать из БД».
          </p>
        </div>
      )}

      {/* === ВЕБХУКИ === */}
      {tab === 'webhooks' && (
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 }}>
          <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 24, border: '1px solid var(--line)' }}>
            <h3 style={{ fontSize: 14, textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 16 }}>Активные</h3>
            <DataTable
              columns={[
                { key: 'url', label: 'URL' },
                { key: 'events', label: 'События', format: (v) => (v as string[]).join(', ') },
              ]}
              rows={hooks as unknown as Record<string, unknown>[]}
            />
          </div>
          <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 24, border: '1px solid var(--line)' }}>
            <h3 style={{ fontSize: 14, textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 16 }}>Добавить</h3>
            <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 16 }}>
              Уведомления при DRIFT или падении live-метрики.
            </p>
            <div style={{ marginBottom: 16 }}>
              <label style={labelStyle}>URL</label>
              <input value={hookUrl} onChange={(e) => setHookUrl(e.target.value)} style={inputStyle} placeholder="https://hooks.example.com/..." />
            </div>
            <button onClick={async () => {
              await adminCreateWebhook({ url: hookUrl, events: ['drift', 'live_metric_drop'] })
              setHookUrl('')
              refresh()
            }} style={{ ...btnStyle, width: '100%' }}>
              Добавить
            </button>
          </div>
        </div>
      )}
    </Layout>
  )
}
