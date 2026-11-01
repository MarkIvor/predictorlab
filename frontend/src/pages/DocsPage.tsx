import { useEffect, useState } from 'react'

type Spec = { paths?: Record<string, Record<string, { summary?: string }>>; info?: { title?: string; version?: string } }

export default function DocsPage() {
  const [spec, setSpec] = useState<Spec | null>(null)
  useEffect(() => { fetch('/openapi.json').then((r) => r.json()).then(setSpec) }, [])
  const paths = Object.entries(spec?.paths || {})
  return (
    <div className="page" style={{ maxWidth: 900, margin: '0 auto' }}>
      <h1 className="brand" style={{ margin: '16px 2px' }}>API <span className="accent">DOCS</span></h1>
      <p className="muted" style={{ fontSize: 12 }}>
        Публичный контракт PredictorLab: база <b>/api/v1</b>, авторизация <b>Bearer pl_live_…</b> или JWT-сессия.
        Полная интерактивная схема: <a href="/docs" target="_blank" rel="noreferrer">/docs (Swagger)</a>.
      </p>
      <div className="tile" style={{ marginTop: 12 }}>
        <span className="tile-label">ЭНДПОИНТЫ</span>
        {paths.map(([path, methods]) => (
          <div key={path} style={{ borderTop: '1px solid var(--line)', padding: '8px 0' }}>
            {Object.entries(methods).map(([method, op]) => (
              <div key={method} style={{ display: 'flex', gap: 12, fontSize: 12 }}>
                <span style={{ color: 'var(--stone)', width: 56 }}>{method.toUpperCase()}</span>
                <span style={{ width: 320 }}>{path}</span>
                <span className="muted">{op.summary || ''}</span>
              </div>
            ))}
          </div>
        ))}
        {!spec && <p className="muted">Загрузка OpenAPI…</p>}
      </div>
    </div>
  )
}
