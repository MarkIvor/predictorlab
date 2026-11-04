import { useEffect, useState } from 'react'
import { Globe, Key, Upload, Copy, Check, ExternalLink, Lock, Link2, FileSpreadsheet, Zap, TrendingUp, Brain, ShieldCheck } from 'lucide-react'
import { createKey, listKeys, getSnippets, managePublic, type ModelOut } from '../../api/endpoints'
import { api } from '../../api/client'

type ShareTab = 'form' | 'api' | 'batch'
type SnippetLang = 'curl' | 'python' | 'javascript' | 'one_c'

export default function ApiTab({ model }: { model: ModelOut }) {
  const [tab, setTab] = useState<ShareTab>('form')

  const tabs: { id: ShareTab; label: string; icon: React.ReactNode; desc: string }[] = [
    { id: 'form', label: 'Веб-форма', icon: <Globe size={16} />, desc: 'Ссылка, по которой любой может получить прогноз без входа' },
    { id: 'api', label: 'API-ключ', icon: <Key size={16} />, desc: 'Для разработчиков: curl, Python, JS, 1С' },
    { id: 'batch', label: 'Пакетный прогноз', icon: <Upload size={16} />, desc: 'Загрузите файл — получите прогнозы для всех строк' },
  ]

  return (
    <div>
      {/* Explanation banner */}
      <div style={{
        background: 'var(--surface)', borderRadius: 'var(--radius)', padding: '20px 24px',
        border: '1px solid var(--line)', marginBottom: 20,
        display: 'flex', alignItems: 'flex-start', gap: 16,
      }}>
        <Zap size={24} color="var(--accent)" style={{ flexShrink: 0, marginTop: 2 }} />
        <div>
          <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--ink)' }}>
            Поделитесь предсказаниями
          </div>
          <p style={{ fontSize: 14, color: 'var(--muted)', margin: '4px 0 0', lineHeight: 1.6 }}>
            Выберите, как передать модель тем, кому она нужна: ссылка для любого человека,
            API-ключ для программиста или загрузка файла с базой объектов.
          </p>
        </div>
      </div>

      {/* Method tabs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 24 }}>
        {tabs.map(({ id, label, icon, desc }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            style={{
              background: tab === id ? 'var(--accent)' : 'var(--surface)',
              borderRadius: 'var(--radius)', padding: '20px 24px',
              border: `1px solid ${tab === id ? 'var(--accent)' : 'var(--line)'}`,
              cursor: 'pointer', textAlign: 'left', fontFamily: 'var(--font)',
              transition: 'all 120ms',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              {icon}
              <span style={{
                fontSize: 16, fontWeight: 600,
                color: tab === id ? 'var(--ink)' : 'var(--muted)',
              }}>{label}</span>
            </div>
            <div style={{ fontSize: 13, color: tab === id ? 'var(--ink)' : 'var(--muted)', opacity: 0.8, lineHeight: 1.5 }}>
              {desc}
            </div>
          </button>
        ))}
      </div>

      {tab === 'form' && <WebFormSection model={model} />}
      {tab === 'api' && <ApiKeySection model={model} />}
      {tab === 'batch' && <BatchSection model={model} />}
    </div>
  )
}

/* === ВЕБ-ФОРМА === */
function WebFormSection({ model }: { model: ModelOut }) {
  const [slug, setSlug] = useState('')
  const [password, setPassword] = useState('')
  const [publicUrl, setPublicUrl] = useState<string | null>(null)
  const [hasPassword, setHasPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    // Check if already has a public page
    api<{ slug?: string }>(`/api/models/${model.id}`).then((m) => {
      if (m.slug) {
        setSlug(m.slug)
        setPublicUrl(`${window.location.origin}/p/${m.slug}`)
      }
    }).catch(() => {})
  }, [model.id])

  const createForm = async () => {
    setBusy(true)
    try {
      const body: Record<string, unknown> = { enabled: true }
      if (slug) body.slug = slug
      if (password) body.password = password
      const r = await managePublic(model.id, body)
      if (r.url) {
        setPublicUrl(r.url)
        setHasPassword(Boolean(password))
      }
    } finally {
      setBusy(false)
    }
  }

  const copyUrl = () => {
    if (publicUrl) {
      navigator.clipboard.writeText(publicUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  if (publicUrl) {
    return (
      <div style={{ display: 'grid', gap: 16 }}>
        {/* Success card */}
        <div style={{
          background: 'var(--ok)', borderRadius: 'var(--radius)', padding: '32px 28px',
          color: '#101015', textAlign: 'center',
        }}>
          <Check size={40} style={{ margin: '0 auto 12px' }} />
          <h3 style={{ fontSize: 20, fontWeight: 600, margin: 0 }}>Форма готова!</h3>
          <p style={{ fontSize: 14, margin: '8px 0 20px', opacity: 0.8 }}>
            Любой человек по этой ссылке может получить прогноз без входа в систему.
          </p>

          {/* URL display */}
          <div style={{
            display: 'flex', gap: 8, justifyContent: 'center', alignItems: 'center',
          }}>
            <div style={{
              background: '#101015', borderRadius: 'var(--radius)',
              padding: '12px 20px', fontSize: 14,
              color: 'var(--ink)', fontFamily: 'var(--font)',
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <Link2 size={16} />
              {publicUrl}
            </div>
            <button onClick={copyUrl} style={{
              background: '#101015', border: 'none', borderRadius: 'var(--radius)',
              padding: '12px 16px', cursor: 'pointer',
              color: copied ? 'var(--ok)' : 'var(--ink)',
            }}>
              {copied ? <Check size={18} /> : <Copy size={18} />}
            </button>
            <a href={publicUrl} target="_blank" rel="noreferrer" style={{
              background: '#101015', border: 'none', borderRadius: 'var(--radius)',
              padding: '12px 16px', cursor: 'pointer',
              color: 'var(--ink)', display: 'inline-flex', alignItems: 'center',
            }}>
              <ExternalLink size={18} />
            </a>
          </div>

          {hasPassword && (
            <div style={{
              marginTop: 16, display: 'inline-flex', alignItems: 'center', gap: 6,
              fontSize: 13, color: '#101015', opacity: 0.7,
            }}>
              <Lock size={14} /> Защищена паролем
            </div>
          )}
        </div>

        {/* What the form looks like */}
        <div style={{
          background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 28,
          border: '1px solid var(--line)',
        }}>
          <h4 style={{ fontSize: 14, textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 16 }}>
            Что увидит человек по ссылке
          </h4>
          <ol style={{ fontSize: 14, color: 'var(--ink)', lineHeight: 2, paddingLeft: 20, margin: 0 }}>
            <li>Форму с полями модели «{model.name}»</li>
            <li>Заполнит признаки объекта и нажмёт «Предсказать»</li>
            <li>Увидит результат: вероятность + доверительный интервал + причины по-русски</li>
            <li>Всё это — без регистрации и без доступа к вашим данным</li>
          </ol>
        </div>

        {/* Disable button */}
        <button
          onClick={async () => {
            await managePublic(model.id, { enabled: false })
            setPublicUrl(null)
          }}
          style={{
            alignSelf: 'center', padding: '12px 24px', fontSize: 13,
            background: 'var(--surface)', color: 'var(--danger)',
            border: '1px solid var(--danger)', borderRadius: 'var(--radius)',
            cursor: 'pointer', fontFamily: 'var(--font)',
          }}
        >
          Закрыть публичный доступ
        </button>
      </div>
    )
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
      {/* Left: settings */}
      <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 28, border: '1px solid var(--line)' }}>
        <h3 style={{ fontSize: 16, fontWeight: 600, color: 'var(--ink)', marginBottom: 8 }}>
          Создать форму предсказания
        </h3>
        <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.6, marginBottom: 24 }}>
          Человек по ссылке увидит форму с полями вашей модели, заполнит их
          и получит прогноз. Ему не нужен доступ к системе.
        </p>

        <div style={{ marginBottom: 20 }}>
          <label style={{ display: 'block', fontSize: 12, textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 8 }}>
            Адрес страницы (опционально)
          </label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ fontSize: 14, color: 'var(--muted)' }}>/p/</span>
            <input
              value={slug}
              onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
              placeholder="churn-form"
              style={{
                flex: 1, padding: '14px', fontSize: 15,
                background: 'var(--bg)', border: '1px solid var(--line)',
                borderRadius: 'var(--radius)', color: 'var(--ink)', fontFamily: 'var(--font)',
              }}
            />
          </div>
          <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 6 }}>
            Если оставить пустым — сгенерируем автоматически
          </p>
        </div>

        <div style={{ marginBottom: 24 }}>
          <label style={{ display: 'block', fontSize: 12, textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 8 }}>
            Пароль (опционально)
          </label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Защитите форму паролем"
            style={{
              width: '100%', padding: '14px', fontSize: 15,
              background: 'var(--bg)', border: '1px solid var(--line)',
              borderRadius: 'var(--radius)', color: 'var(--ink)', fontFamily: 'var(--font)',
            }}
          />
          <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Lock size={12} /> Если не задан — форма открыта для всех
          </p>
        </div>

        <button onClick={createForm} disabled={busy} style={{
          width: '100%', padding: '16px 0', fontSize: 15, fontWeight: 600,
          background: 'var(--ink)', color: '#101015', border: 'none',
          borderRadius: 'var(--radius)', cursor: 'pointer', fontFamily: 'var(--font)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
          opacity: busy ? 0.5 : 1,
        }}>
          <Globe size={18} /> {busy ? 'Создаём…' : 'Создать форму'}
        </button>
      </div>

      {/* Right: what happens */}
      <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 28, border: '1px solid var(--line)' }}>
        <h4 style={{ fontSize: 14, textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 16 }}>
          Как это работает
        </h4>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {[
            { num: 1, text: 'Вы создаёте форму и получаете ссылку' },
            { num: 2, text: 'Отправляете ссылку коллегам, клиентам или встраиваете в свой сайт' },
            { num: 3, text: 'Человек заполняет поля: возраст, тариф, стаж…' },
            { num: 4, text: 'Получает прогноз: вероятность + интервал + причины по-русски' },
          ].map((step) => (
            <div key={step.num} style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
              <div style={{
                width: 32, height: 32, borderRadius: '50%',
                background: 'var(--accent)', color: 'var(--ink)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 14, fontWeight: 600, flexShrink: 0,
              }}>
                {step.num}
              </div>
              <p style={{ fontSize: 14, color: 'var(--ink)', margin: 0, lineHeight: 1.6, paddingTop: 4 }}>
                {step.text}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

/* === API-КЛЮЧ === */
function ApiKeySection({ model }: { model: ModelOut }) {
  const [snippetTab, setSnippetTab] = useState<SnippetLang>('curl')
  const [snippets, setSnippets] = useState<{ curl: string; python: string; javascript: string; one_c: string; url: string } | null>(null)
  const [keys, setKeys] = useState<{ id: number; name: string; prefix: string; revoked_at: string | null }[]>([])
  const [newKeyName, setNewKeyName] = useState('')
  const [createdKey, setCreatedKey] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [busy, setBusy] = useState(false)
  const [sandboxInput, setSandboxInput] = useState('{}')
  const [sandboxOut, setSandboxOut] = useState('')

  const refresh = async () => {
    setSnippets(await getSnippets(model.id))
    setKeys(await listKeys())
  }

  useEffect(() => { refresh() }, [model.id])

  const createNewKey = async () => {
    setBusy(true)
    try {
      const r = await createKey({ name: newKeyName || `Модель ${model.id}`, model_ids: [model.id] })
      setCreatedKey(r.key)
      setNewKeyName('')
      refresh()
    } finally {
      setBusy(false)
    }
  }

  const copyText = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const runSandbox = async () => {
    setSandboxOut('…')
    try {
      const body = JSON.parse(sandboxInput)
      const r = await api<Record<string, unknown>>(`/api/v1/models/${model.id}/predict`, { json: body })
      setSandboxOut(JSON.stringify(r, null, 2))
    } catch (e) {
      setSandboxOut(String(e))
    }
  }

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {/* Key creation or display */}
      {createdKey ? (
        <div style={{
          background: 'var(--ok)', borderRadius: 'var(--radius)', padding: 24,
          color: '#101015',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Check size={20} />
            <span style={{ fontSize: 16, fontWeight: 600 }}>Ключ создан!</span>
          </div>
          <p style={{ fontSize: 13, opacity: 0.8, margin: '0 0 12px' }}>
            Сохраните ключ — он показывается только один раз.
          </p>
          <div style={{ display: 'flex', gap: 8 }}>
            <code style={{
              flex: 1, background: '#101015', color: 'var(--ink)',
              padding: '12px 16px', borderRadius: 'var(--radius)',
              fontSize: 14, fontFamily: 'var(--font)', overflow: 'auto',
            }}>
              {createdKey}
            </code>
            <button onClick={() => copyText(createdKey)} style={{
              background: '#101015', border: 'none', borderRadius: 'var(--radius)',
              padding: '12px 16px', cursor: 'pointer', color: copied ? 'var(--ok)' : 'var(--ink)',
            }}>
              {copied ? <Check size={16} /> : <Copy size={16} />}
            </button>
          </div>
        </div>
      ) : (
        <div style={{
          background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 24,
          border: '1px solid var(--line)',
          display: 'flex', gap: 16, alignItems: 'center',
        }}>
          <Key size={24} color="var(--accent)" style={{ flexShrink: 0 }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--ink)' }}>Нужен API-ключ для этой модели</div>
            <p style={{ fontSize: 13, color: 'var(--muted)', margin: '4px 0 0' }}>
              Ключ даёт доступ только к предсказаниям этой модели. Без доступа к вашим данным.
            </p>
          </div>
          <input
            value={newKeyName}
            onChange={(e) => setNewKeyName(e.target.value)}
            placeholder="Имя ключа"
            style={{
              padding: '12px 16px', fontSize: 14, width: 200,
              background: 'var(--bg)', border: '1px solid var(--line)',
              borderRadius: 'var(--radius)', color: 'var(--ink)', fontFamily: 'var(--font)',
            }}
          />
          <button onClick={createNewKey} disabled={busy} style={{
            padding: '12px 24px', fontSize: 13, fontWeight: 600,
            background: 'var(--ink)', color: '#101015', border: 'none',
            borderRadius: 'var(--radius)', cursor: 'pointer', fontFamily: 'var(--font)',
            whiteSpace: 'nowrap',
          }}>
            {busy ? '…' : 'Создать ключ'}
          </button>
        </div>
      )}

      {/* Existing keys */}
      {keys.filter((k) => !k.revoked_at).length > 0 && (
        <div style={{
          background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 20,
          border: '1px solid var(--line)',
        }}>
          <span style={{ fontSize: 12, textTransform: 'uppercase', color: 'var(--muted)' }}>Активные ключи</span>
          <div style={{ marginTop: 8 }}>
            {keys.filter((k) => !k.revoked_at).map((k) => (
              <div key={k.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14, padding: '6px 0' }}>
                <span style={{ color: 'var(--ink)' }}>{k.prefix}…</span>
                <span style={{ color: 'var(--muted)' }}>{k.name}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Snippets */}
      {snippets && createdKey && (
        <div style={{
          background: 'var(--surface)', borderRadius: 'var(--radius)',
          border: '1px solid var(--line)', overflow: 'hidden',
        }}>
          {/* Language tabs */}
          <div style={{ display: 'flex', borderBottom: '1px solid var(--line)' }}>
            {([
              { id: 'curl', label: 'curl' },
              { id: 'python', label: 'Python' },
              { id: 'javascript', label: 'JavaScript' },
              { id: 'one_c', label: '1С' },
            ] as { id: SnippetLang; label: string }[]).map(({ id, label }) => (
              <button
                key={id}
                onClick={() => setSnippetTab(id)}
                style={{
                  padding: '14px 20px', background: 'none', border: 'none',
                  borderBottom: snippetTab === id ? '2px solid var(--accent)' : '2px solid transparent',
                  color: snippetTab === id ? 'var(--ink)' : 'var(--muted)',
                  fontSize: 14, cursor: 'pointer', fontFamily: 'var(--font)',
                }}
              >
                {label}
              </button>
            ))}
            <button
              onClick={() => copyText(snippets[snippetTab].replace('pl_live_ВАШ_КЛЮЧ', createdKey))}
              style={{
                marginLeft: 'auto', padding: '8px 16px', background: 'none',
                border: 'none', color: 'var(--muted)', cursor: 'pointer',
                fontFamily: 'var(--font)', fontSize: 13, display: 'flex', alignItems: 'center', gap: 6,
              }}
            >
              {copied ? <Check size={14} /> : <Copy size={14} />} Копировать
            </button>
          </div>

          {/* Code */}
          <pre style={{
            margin: 0, padding: 20, fontSize: 13,
            background: 'var(--bg)', color: 'var(--ink)',
            fontFamily: 'var(--font)', lineHeight: 1.7,
            overflow: 'auto', whiteSpace: 'pre-wrap',
          }}>
            {snippets[snippetTab].replace('pl_live_ВАШ_КЛЮЧ', createdKey)}
          </pre>

          <div style={{ padding: '12px 20', borderTop: '1px solid var(--line)', fontSize: 13, color: 'var(--muted)' }}>
            Готово — вставьте в терминал или код. Работает без правок.
          </div>
        </div>
      )}

      {/* Sandbox */}
      <div style={{
        background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 24,
        border: '1px solid var(--line)',
      }}>
        <h4 style={{ fontSize: 14, textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 12 }}>
          Песочница — проверьте запрос прямо здесь
        </h4>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div>
            <textarea
              value={sandboxInput}
              onChange={(e) => setSandboxInput(e.target.value)}
              rows={10}
              style={{
                width: '100%', padding: 14, fontSize: 13,
                background: 'var(--bg)', border: '1px solid var(--line)',
                borderRadius: 'var(--radius)', color: 'var(--ink)',
                fontFamily: 'var(--font)', resize: 'vertical',
              }}
              placeholder='{"data": [{"признак1": 100, "признак2": "значение"}]}'
            />
            <button onClick={runSandbox} style={{
              marginTop: 8, width: '100%', padding: '12px 0', fontSize: 13, fontWeight: 600,
              background: 'var(--ink)', color: '#101015', border: 'none',
              borderRadius: 'var(--radius)', cursor: 'pointer', fontFamily: 'var(--font)',
            }}>
              Отправить запрос
            </button>
          </div>
          <pre style={{
            margin: 0, padding: 14, fontSize: 13, minHeight: 200,
            background: 'var(--bg)', border: '1px solid var(--line)',
            borderRadius: 'var(--radius)', color: 'var(--ink)',
            fontFamily: 'var(--font)', overflow: 'auto', whiteSpace: 'pre-wrap',
          }}>
            {sandboxOut || 'Ответ появится здесь…'}
          </pre>
        </div>
      </div>
    </div>
  )
}

/* === ПАКЕТНЫЙ ПРОГНОЗ === */
function BatchSection({ model }: { model: ModelOut }) {
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [jobId, setJobId] = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState('')
  const [resultUrl, setResultUrl] = useState<string | null>(null)

  const startBatch = async () => {
    if (!file) return
    setBusy(true)
    setJobStatus('Загружаем файл…')
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('include', 'reasons')
      const r = await api<{ job_id: string }>(`/api/v1/models/${model.id}/predict/batch`, { form })
      setJobId(r.job_id)
      setJobStatus('В очереди')
      for (;;) {
        const job = await api<{ status: string; progress: Record<string, unknown>; error: string | null; result_path: string | null }>(`/api/jobs/${r.job_id}`)
        setJobStatus(
          job.status === 'running' ? `Считаем… ${JSON.stringify(job.progress).slice(0, 80)}` :
          job.status === 'done' ? 'Готово!' :
          job.status === 'error' ? `Ошибка: ${(job.error || '').slice(0, 100)}` : job.status
        )
        if (job.status === 'done') {
          setResultUrl(`/api/v1/jobs/${r.job_id}/result/predictions.csv`)
          break
        }
        if (job.status === 'error') break
        await new Promise((res) => setTimeout(res, 2000))
      }
    } catch (e) {
      setJobStatus(`Ошибка: ${e}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
      {/* Left: upload */}
      <div style={{
        background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 32,
        border: '2px dashed var(--line)', textAlign: 'center',
      }}>
        <FileSpreadsheet size={48} color="var(--muted)" style={{ margin: '0 auto 16px' }} />
        <p style={{ fontSize: 16, color: 'var(--ink)', margin: '0 0 8px' }}>
          Загрузите файл с объектами для прогноза
        </p>
        <p style={{ fontSize: 13, color: 'var(--muted)', margin: '0 0 20px' }}>
          CSV, XLSX или Parquet. Колонки должны совпадать со схемой модели.
          Результат: prediction, probability, интервалы, ood + причины для топ-1000 рисковых.
        </p>
        <input type="file" accept=".csv,.xlsx,.parquet" onChange={(e) => setFile(e.target.files?.[0] || null)}
          style={{ fontSize: 14, padding: '12px', background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: 'var(--radius)', color: 'var(--ink)', width: '80%' }}
        />
        <div style={{ marginTop: 20 }}>
          <button onClick={startBatch} disabled={!file || busy} style={{
            padding: '14px 40px', fontSize: 14, fontWeight: 600,
            background: 'var(--ink)', color: '#101015', border: 'none',
            borderRadius: 'var(--radius)', cursor: busy ? 'wait' : 'pointer',
            fontFamily: 'var(--font)', opacity: !file || busy ? 0.4 : 1,
          }}>
            {busy ? 'Обрабатываем…' : 'Запустить прогноз'}
          </button>
        </div>
        {jobId && (
          <div style={{ marginTop: 16 }}>
            <p style={{ fontSize: 13, color: 'var(--muted)' }}>{jobStatus}</p>
            {resultUrl && (
              <a href={resultUrl} download style={{
                display: 'inline-flex', alignItems: 'center', gap: 8,
                marginTop: 12, padding: '12px 24px', fontSize: 14, fontWeight: 600,
                background: 'var(--ok)', color: '#101015', border: 'none',
                borderRadius: 'var(--radius)', textDecoration: 'none', fontFamily: 'var(--font)',
              }}>
                <FileSpreadsheet size={16} /> Скачать результат (CSV)
              </a>
            )}
          </div>
        )}
      </div>

      {/* Right: explanation */}
      <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 28, border: '1px solid var(--line)' }}>
        <h4 style={{ fontSize: 14, textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 16 }}>
          Что вы получите
        </h4>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {[
            { icon: <Zap size={18} />, title: 'Прогноз для каждой строки', desc: 'Класс или число + вероятность' },
            { icon: <TrendingUp size={18} />, title: 'Доверительный интервал 90%', desc: 'В каких пределах ожидать результат' },
            { icon: <Brain size={18} />, title: 'Причины (top-1000 рисковых)', desc: 'Почему модель дала такой прогноз' },
            { icon: <ShieldCheck size={18} />, title: 'Флаг OOD', desc: 'Если объект сильно отличается от обучающих данных' },
          ].map((item, i) => (
            <div key={i} style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
              <div style={{
                width: 36, height: 36, borderRadius: 'var(--radius)',
                background: 'var(--surface-2)', display: 'flex',
                alignItems: 'center', justifyContent: 'center', color: 'var(--accent)', flexShrink: 0,
              }}>
                {item.icon}
              </div>
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>{item.title}</div>
                <div style={{ fontSize: 13, color: 'var(--muted)' }}>{item.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
