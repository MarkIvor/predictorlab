import type { ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { LogOut, Plus, LayoutGrid, Settings } from 'lucide-react'
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

  const navItem = (to: string, icon: ReactNode, label: string) => {
    const active = loc.pathname === to
    return (
      <Link to={to} style={{
        display: 'flex', alignItems: 'center', gap: '8px',
        padding: '10px 16px',
        color: active ? 'var(--ink)' : 'var(--muted)',
        borderBottom: active ? '2px solid var(--accent)' : '2px solid transparent',
        fontSize: '14px',
        letterSpacing: '0.04em',
        textDecoration: 'none',
        transition: 'color 120ms, border-color 120ms',
      }}>
        {icon}
        {label}
      </Link>
    )
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top nav */}
      <header style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 32px',
        height: 64,
        borderBottom: '1px solid var(--line)',
        background: 'var(--surface)',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 40 }}>
          <Link to="/" style={{
            fontSize: 18,
            fontWeight: 600,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: 'var(--ink)',
            textDecoration: 'none',
          }}>
            PREDICTOR<span style={{ color: 'var(--accent)' }}>LAB</span>
          </Link>
          <nav style={{ display: 'flex', gap: 4 }}>
            {navItem('/', <LayoutGrid size={16} />, 'Модели')}
            {navItem('/new', <Plus size={16} />, 'Новая')}
            {user?.role === 'admin' && navItem('/admin', <Settings size={16} />, 'Админ')}
          </nav>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {actions}
          <span style={{ color: 'var(--muted)', fontSize: 13 }}>{user?.email}</span>
          <button
            onClick={doLogout}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              background: 'none', border: '1px solid var(--line)',
              borderRadius: 'var(--radius)', padding: '8px 14px',
              color: 'var(--muted)', cursor: 'pointer',
              fontFamily: 'var(--font)', fontSize: '13px',
            }}
          >
            <LogOut size={14} /> Выйти
          </button>
        </div>
      </header>

      {/* Content */}
      <main style={{ flex: 1, maxWidth: 1440, width: '100%', margin: '0 auto', padding: '28px 32px' }}>
        {title && (
          <h1 style={{
            fontSize: 22,
            textTransform: 'uppercase',
            letterSpacing: '0.02em',
            margin: '0 0 24px',
            color: 'var(--ink)',
          }}>
            {title}
          </h1>
        )}
        {children}
      </main>
    </div>
  )
}
