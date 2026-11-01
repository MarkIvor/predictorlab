import { useEffect, useState } from 'react'
import { getModelCard, regenerateCard, type ModelOut } from '../../api/endpoints'

function mdToHtml(md: string): string {
  const escape = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const lines = escape(md).split('\n')
  const out: string[] = []
  let inList = false
  for (const line of lines) {
    const l = line.trim()
    if (l.startsWith('### ')) { if (inList) { out.push('</ul>'); inList = false } out.push(`<h3>${l.slice(4)}</h3>`) }
    else if (l.startsWith('## ')) { if (inList) { out.push('</ul>'); inList = false } out.push(`<h2>${l.slice(3)}</h2>`) }
    else if (l.startsWith('# ')) { if (inList) { out.push('</ul>'); inList = false } out.push(`<h1>${l.slice(2)}</h1>`) }
    else if (l.startsWith('- ')) { if (!inList) { out.push('<ul>'); inList = true } out.push(`<li>${l.slice(2)}</li>`) }
    else if (l === '') { if (inList) { out.push('</ul>'); inList = false } }
    else { if (inList) { out.push('</ul>'); inList = false } out.push(`<p>${l}</p>`) }
  }
  if (inList) out.push('</ul>')
  return out.join('\n')
}

export default function CardTab({ model }: { model: ModelOut }) {
  const [card, setCard] = useState<{ card_md: string; llm_narrative?: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => { getModelCard(model.id).then(setCard) }, [model.id])

  const regen = async () => {
    setBusy(true)
    setMsg('')
    try {
      await regenerateCard(model.id)
      setCard(await getModelCard(model.id))
      setMsg('Бизнес-текст обновлён (числа проверены валидатором)')
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'LLM недоступна — карточка по шаблону')
    } finally { setBusy(false) }
  }

  if (!card) return <p className="muted">Загрузка…</p>

  return (
    <div className="bento-grid">
      <div className="tile" style={{ gridColumn: 'span 12', display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <span className="tile-label" style={{ marginRight: 'auto' }}>MODEL CARD · АВТОГЕНЕРАЦИЯ</span>
        <a className="btn" href={`/api/models/${model.id}/card/export?format=md`}>ЭКСПОРТ .MD</a>
        <a className="btn" href={`/api/models/${model.id}/card/export?format=pdf`}>ЭКСПОРТ .PDF</a>
        <button className="btn" onClick={regen} disabled={busy}>{busy ? '…' : 'БИЗНЕС-ЯЗЫК (LLM)'}</button>
      </div>
      {msg && <div className="tile" style={{ gridColumn: 'span 12' }}><p style={{ margin: 0, fontSize: 12 }}>{msg}</p></div>}
      {card.llm_narrative && (
        <div className="tile" style={{ gridColumn: 'span 12', background: 'var(--accent)' }}>
          <span className="tile-label">EXECUTIVE SUMMARY (LLM, ЧИСЛА ПРОВЕРЕНЫ)</span>
          <p style={{ marginTop: 10, fontSize: 13, lineHeight: 1.6 }}>{card.llm_narrative}</p>
        </div>
      )}
      <div className="tile card-md" style={{ gridColumn: 'span 12' }}>
        <div
          style={{ fontSize: 13, lineHeight: 1.65 }}
          dangerouslySetInnerHTML={{ __html: mdToHtml(card.card_md || 'Карточка пока не сгенерирована') }}
        />
      </div>
    </div>
  )
}
