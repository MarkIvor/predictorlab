import { useEffect, useState } from 'react'
import {
  adminCreateUser, adminCreateWebhook, adminLlm, adminPatchUser, adminPutLlm, adminStats,
  adminUsers, adminWebhooks, listKeys, mcpConfig,
} from '../api/endpoints'
import { DataTable, StatTile } from '../design/components'
import Layout from './Layout'

export default function Admin() {
  const [stats, setStats] = useState<Record<string, number> | null>(null)
  const [users, setUsers] = useState<{ id: number; email: string; display_name: string; role: string; must_change_password: boolean }[]>([])
  const [llm, setLlm] = useState<{ enabled: boolean; base_url: string; model: string; api_key_masked: string } | null>(null)
  const [llmForm, setLlmForm] = useState({ base_url: '', model: '', api_key: '' })
  const [hooks, setHooks] = useState<{ id: number; url: string; model_id: number | null; events: string[] }[]>([])
  const [hookUrl, setHookUrl] = useState('')
  const [newUser, setNewUser] = useState({ email: '', password: '', role: 'viewer' })
  const [mcp, setMcp] = useState<{ enabled: boolean; claude_desktop?: string; cursor?: string; http_command?: string } | null>(null)
  const [keys, setKeys] = useState<{ id: number; name: string; prefix: string; revoked_at: string | null }[]>([])

  const refresh = async () => {
    setStats(await adminStats())
    setUsers(await adminUsers())
    const l = await adminLlm()
    setLlm(l)
    setLlmForm((f) => ({ ...f, base_url: l.base_url, model: l.model }))
    setHooks(await adminWebhooks())
    setMcp(await mcpConfig())
    setKeys(await listKeys())
  }
  useEffect(() => { void refresh() }, [])

  return (
    <Layout title="АДМИНКА">
      <div className="bento-grid">
        {stats && (
          <>
            <StatTile label="USERS" value={stats.users} />
            <StatTile label="MODELS" value={stats.models} denominator={`${stats.ready_models} READY`} />
            <StatTile label="PREDICTIONS / 24H" value={stats.predictions_24h} />
            <StatTile label="AVG LATENCY" value={`${stats.avg_latency_ms} мс`} note="Средняя задержка прогноза за 24 часа" />
          </>
        )}

        <div className="tile" style={{ gridColumn: 'span 7' }}>
          <span className="tile-label">ПОЛЬЗОВАТЕЛИ И РОЛИ</span>
          <div style={{ marginTop: 10 }}>
            <DataTable
              columns={[
                { key: 'email', label: 'EMAIL' },
                { key: 'role', label: 'РОЛЬ', format: (v, row) => (
                  <select value={String(v)} onChange={async (e) => { await adminPatchUser((row as { id: number }).id, { role: e.target.value }); void refresh() }}>
                    <option value="admin">admin</option><option value="builder">builder</option><option value="viewer">viewer</option>
                  </select>
                ) },
                { key: 'must_change_password', label: 'ПАРОЛЬ', format: (v) => (v ? 'сменить при входе' : 'ок') },
                { key: 'id', label: '', format: (v) => (
                  <button className="btn btn-danger" onClick={async () => { await adminPatchUser(Number(v), { is_active: false }); void refresh() }}>ОТКЛЮЧИТЬ</button>
                ) },
              ]}
              rows={users as unknown as Record<string, unknown>[]}
            />
          </div>
          <div className="form-row" style={{ marginTop: 14 }}>
            <div className="field"><label>Email</label><input value={newUser.email} onChange={(e) => setNewUser({ ...newUser, email: e.target.value })} /></div>
            <div className="field"><label>Пароль (≥8)</label><input value={newUser.password} onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} /></div>
            <div className="field"><label>Роль</label>
              <select value={newUser.role} onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}>
                <option value="viewer">viewer</option><option value="builder">builder</option><option value="admin">admin</option>
              </select>
            </div>
          </div>
          <button className="btn btn-ink" onClick={async () => { await adminCreateUser(newUser); setNewUser({ email: '', password: '', role: 'viewer' }); void refresh() }}>СОЗДАТЬ</button>
        </div>

        <div className="tile" style={{ gridColumn: 'span 5' }}>
          <span className="tile-label">LLM {llm?.enabled ? '· ВКЛЮЧЕНА' : '· ОФЛАЙН'}</span>
          <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>
            Любой OpenAI-совместимый API. Пустой base_url = офлайн-режим: LLM-функции скрыты, всё остальное работает.
            Сырые строки данных не уходят (LLM_ALLOW_SAMPLES=false).
          </p>
          <div className="field" style={{ marginTop: 10 }}><label>BASE URL</label><input value={llmForm.base_url} onChange={(e) => setLlmForm({ ...llmForm, base_url: e.target.value })} placeholder="https://api.deepseek.com/v1" /></div>
          <div className="field"><label>МОДЕЛЬ</label><input value={llmForm.model} onChange={(e) => setLlmForm({ ...llmForm, model: e.target.value })} /></div>
          <div className="field"><label>API KEY {llm?.api_key_masked}</label><input type="password" value={llmForm.api_key} onChange={(e) => setLlmForm({ ...llmForm, api_key: e.target.value })} /></div>
          <button className="btn btn-ink" onClick={async () => { await adminPutLlm(llmForm); void refresh() }}>СОХРАНИТЬ</button>
        </div>

        <div className="tile" style={{ gridColumn: 'span 7' }}>
          <span className="tile-label">ВЕБХУКИ (ДРЕЙФ / ПАДЕНИЕ LIVE-МЕТРИКИ)</span>
          <div style={{ marginTop: 10 }}>
            <DataTable
              columns={[{ key: 'url', label: 'URL' }, { key: 'events', label: 'СОБЫТИЯ', format: (v) => (v as string[]).join(', ') }]}
              rows={hooks as unknown as Record<string, unknown>[]}
            />
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            <input style={{ flex: 1 }} value={hookUrl} onChange={(e) => setHookUrl(e.target.value)} placeholder="https://…" />
            <button className="btn btn-ink" onClick={async () => { await adminCreateWebhook({ url: hookUrl, events: ['drift', 'live_metric_drop'] }); setHookUrl(''); void refresh() }}>ДОБАВИТЬ</button>
          </div>
        </div>

        <div className="tile" style={{ gridColumn: 'span 5' }}>
          <span className="tile-label">MCP-СЕРВЕР</span>
          {mcp?.enabled ? (
            <>
              <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>Конфиги для Claude Desktop и Cursor. Кнопки копирования в README.</p>
              <div className="field" style={{ marginTop: 10 }}><label>CLAUDE DESKTOP (claude_desktop_config.json)</label><pre className="snippet">{mcp.claude_desktop}</pre></div>
              <div className="field"><label>CURSOR (mcp.json)</label><pre className="snippet">{mcp.cursor}</pre></div>
              <div className="field"><label>HTTP-ЗАПУСК</label><pre className="snippet">{mcp.http_command}</pre></div>
            </>
          ) : <p className="muted" style={{ marginTop: 8 }}>Задайте MCP_AUTH_TOKEN в .env, чтобы включить.</p>}
        </div>

        <div className="tile" style={{ gridColumn: 'span 12' }}>
          <span className="tile-label">API-КЛЮЧИ ВСЕХ ПОЛЬЗОВАТЕЛЕЙ</span>
          <div style={{ marginTop: 10 }}>
            <DataTable
              columns={[
                { key: 'prefix', label: 'КЛЮЧ' },
                { key: 'name', label: 'ИМЯ' },
                { key: 'revoked_at', label: 'СТАТУС', format: (v) => (v ? 'отозван' : 'активен') },
              ]}
              rows={keys as unknown as Record<string, unknown>[]}
            />
          </div>
        </div>
      </div>
    </Layout>
  )
}
