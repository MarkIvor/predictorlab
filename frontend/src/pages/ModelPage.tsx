import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getModel, type ModelOut } from '../api/endpoints'
import { VerdictBadge } from '../design/components'
import Layout from './Layout'
import Overview from './model/Overview'
import Drivers from './model/Drivers'
import WhatIf from './model/WhatIf'
import Profit from './model/Profit'
import PredictTab from './model/PredictTab'
import ApiTab from './model/ApiTab'
import CardTab from './model/CardTab'
import ActionsTab from './model/ActionsTab'
import MonitorTab from './model/MonitorTab'

const TABS = ['OVERVIEW', 'DRIVERS', 'WHAT-IF', 'PROFIT', 'PREDICT', 'API', 'CARD', 'ACTIONS', 'MONITOR'] as const

export default function ModelPage() {
  const { id, '*': tab } = useParams()
  const modelId = Number(id)
  const active = (TABS as readonly string[]).includes(tab || '') ? (tab as string) : 'OVERVIEW'
  const [model, setModel] = useState<ModelOut | null>(null)
  const [error, setError] = useState('')

  const reload = () => getModel(modelId).then(setModel).catch((e) => setError(String(e)))

  useEffect(() => { reload() }, [modelId])

  if (error) return <Layout><div className="tile">Модель не найдена</div></Layout>
  if (!model) return <Layout><p className="muted">Загрузка…</p></Layout>
  if (model.status === 'training') {
    return (
      <Layout title={model.name.toUpperCase()}>
        <div className="tile"><span className="tile-label">STATUS</span><p style={{ marginTop: 8 }}>Модель обучается — см. мастер (NEW MODEL) или обновите страницу через минуту.</p></div>
      </Layout>
    )
  }

  return (
    <Layout
      title={model.name.toUpperCase()}
      actions={<span style={{ display: 'flex', gap: 8, alignItems: 'center' }}><VerdictBadge verdict={model.guard_verdict} /><Link to="/" className="btn" style={{ textDecoration: 'none' }}>← АНГАР</Link></span>}
    >
      <div className="tabbar" style={{ margin: '4px 2px 12px' }}>
        {TABS.map((t) => (
          <Link key={t} to={`/m/${modelId}/${t}`}>
            <button className={t === active ? 'tab active' : 'tab'}>{t}</button>
          </Link>
        ))}
      </div>
      {model.status !== 'ready' && active !== 'OVERVIEW' && (
        <div className="tile" style={{ marginBottom: 8 }}>
          <span className="tile-label">МОДЕЛЬ ЕЩЁ НЕ ОБУЧЕНА</span>
          <p className="muted" style={{ marginTop: 8 }}>Этот раздел доступен после обучения (в мастере NEW MODEL).</p>
        </div>
      )}
      {active === 'OVERVIEW' && <Overview model={model} />}
      {active === 'DRIVERS' && <Drivers model={model} />}
      {active === 'WHAT-IF' && <WhatIf model={model} />}
      {active === 'PROFIT' && <Profit model={model} onSaved={reload} />}
      {active === 'PREDICT' && <PredictTab model={model} />}
      {active === 'API' && <ApiTab model={model} />}
      {active === 'CARD' && <CardTab model={model} />}
      {active === 'ACTIONS' && <ActionsTab model={model} onSaved={reload} />}
      {active === 'MONITOR' && <MonitorTab model={model} />}
    </Layout>
  )
}
