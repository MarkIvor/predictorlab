import type { ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { logoutApi } from '../api/endpoints'

export default function Layout({ children, title, actions }: { children: ReactNode; title?: string; actions?: ReactNode }) {
  const { user, setUser } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()

  const doLogout = async () => {
    await logoutApi()
    setUser(null)
    nav('/login')
  }

  return (
    <div className="page">
      <header className="page-header">
        <div style={{ display: 'flex', gap: 20, alignItems: 'baseline' }}>
          <Link to="/" className="brand">PREDICTOR<span className="accent">LAB</span></Link>
          <nav className="tabbar">
            <Link to="/"><button className={loc.pathname === '/' ? 'tab active' : 'tab'}>MODELS</button></Link>
            <Link to="/new"><button className={loc.pathname === '/new' ? 'tab active' : 'tab'}>NEW MODEL</button></Link>
            {user?.role === 'admin' && <Link to="/admin"><button className={loc.pathname === '/admin' ? 'tab active' : 'tab'}>ADMIN</button></Link>}
          </nav>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'baseline' }}>
          {actions}
          <span className="muted" style={{ fontSize: 11 }}>{user?.email} · {user?.role?.toUpperCase()}</span>
          <button className="btn" onClick={doLogout}>ВЫЙТИ</button>
        </div>
      </header>
      {title && <h1 style={{ fontSize: 28, textTransform: 'uppercase', margin: '8px 2px' }}>{title}</h1>}
      {children}
    </div>
  )
}
