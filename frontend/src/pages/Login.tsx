import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { changePasswordApi } from '../api/endpoints'
import { useAuth } from '../hooks/useAuth'
import { ApiError } from '../api/client'
import { ArrowRight } from 'lucide-react'

export default function Login() {
  const { login, user, setUser } = useAuth()
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const needChange = user?.must_change_password === true

  if (user && !needChange) {
    return <Navigate to="/" replace />
  }

  const doLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(email, password)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось войти')
    } finally {
      setBusy(false)
    }
  }

  const doChange = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await changePasswordApi(password, newPassword)
      setUser({ ...user!, must_change_password: false })
      nav('/')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сменить пароль')
    } finally {
      setBusy(false)
    }
  }

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '14px 16px',
    fontSize: '15px',
    background: 'var(--bg)',
    border: '1px solid var(--line)',
    borderRadius: 'var(--radius)',
    color: 'var(--ink)',
    fontFamily: 'var(--font)',
    outline: 'none',
  }

  const labelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: '12px',
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    color: 'var(--muted)',
    marginBottom: '8px',
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--bg)',
      padding: '24px',
    }}>
      <div style={{ width: '100%', maxWidth: 420 }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 48 }}>
          <div style={{
            fontSize: 32,
            fontWeight: 600,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: 'var(--ink)',
          }}>
            PREDICTOR<span style={{ color: 'var(--accent)' }}>LAB</span>
          </div>
          <div style={{
            marginTop: 12,
            fontSize: 14,
            color: 'var(--muted)',
            lineHeight: 1.6,
          }}>
            Загрузи данные. Скажи, что предсказать.<br />
            Получи честную модель и API за 5 минут.
          </div>
        </div>

        {/* Card */}
        <div style={{
          background: 'var(--surface)',
          borderRadius: 'var(--radius)',
          padding: '36px 32px',
          border: '1px solid var(--line)',
        }}>
          <div style={{
            fontSize: 12,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: 'var(--muted)',
            marginBottom: 24,
          }}>
            {needChange ? 'Первый вход — смена пароля' : 'Вход в систему'}
          </div>

          {!needChange ? (
            <form onSubmit={doLogin}>
              <div style={{ marginBottom: 20 }}>
                <label style={labelStyle}>Email</label>
                <input
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  type="email"
                  required
                  autoFocus
                  placeholder="admin@predictorlab.io"
                  style={inputStyle}
                  onFocus={(e) => e.target.style.borderColor = 'var(--accent)'}
                  onBlur={(e) => e.target.style.borderColor = 'var(--line)'}
                />
              </div>
              <div style={{ marginBottom: 24 }}>
                <label style={labelStyle}>Пароль</label>
                <input
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  type="password"
                  required
                  placeholder="••••••••"
                  style={inputStyle}
                  onFocus={(e) => e.target.style.borderColor = 'var(--accent)'}
                  onBlur={(e) => e.target.style.borderColor = 'var(--line)'}
                />
              </div>
              {error && (
                <div style={{
                  color: 'var(--danger)',
                  fontSize: 13,
                  marginBottom: 16,
                  padding: '10px 14px',
                  background: 'rgba(181, 96, 90, 0.1)',
                  borderRadius: 'var(--radius)',
                  border: '1px solid rgba(181, 96, 90, 0.3)',
                }}>
                  {error}
                </div>
              )}
              <button
                type="submit"
                disabled={busy}
                style={{
                  width: '100%',
                  padding: '14px 0',
                  background: 'var(--ink)',
                  color: '#101015',
                  border: 'none',
                  borderRadius: 'var(--radius)',
                  fontFamily: 'var(--font)',
                  fontSize: '14px',
                  fontWeight: 600,
                  letterSpacing: '0.04em',
                  textTransform: 'uppercase',
                  cursor: busy ? 'not-allowed' : 'pointer',
                  opacity: busy ? 0.5 : 1,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                }}
              >
                {busy ? 'Входим…' : <>Войти <ArrowRight size={16} /></>}
              </button>
            </form>
          ) : (
            <form onSubmit={doChange}>
              <p style={{ fontSize: 14, color: 'var(--muted)', margin: '0 0 20px', lineHeight: 1.6 }}>
                При первом входе нужно сменить пароль (минимум 8 символов).
              </p>
              <div style={{ marginBottom: 20 }}>
                <label style={labelStyle}>Текущий пароль</label>
                <input
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  type="password"
                  required
                  style={inputStyle}
                />
              </div>
              <div style={{ marginBottom: 24 }}>
                <label style={labelStyle}>Новый пароль</label>
                <input
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  type="password"
                  minLength={8}
                  required
                  style={inputStyle}
                />
              </div>
              {error && (
                <div style={{ color: 'var(--danger)', fontSize: 13, marginBottom: 16, padding: '10px 14px', background: 'rgba(181,96,90,0.1)', borderRadius: 'var(--radius)' }}>
                  {error}
                </div>
              )}
              <button
                type="submit"
                disabled={busy}
                style={{
                  width: '100%',
                  padding: '14px 0',
                  background: 'var(--ink)',
                  color: '#101015',
                  border: 'none',
                  borderRadius: 'var(--radius)',
                  fontFamily: 'var(--font)',
                  fontSize: '14px',
                  fontWeight: 600,
                  letterSpacing: '0.04em',
                  textTransform: 'uppercase',
                  cursor: busy ? 'not-allowed' : 'pointer',
                  opacity: busy ? 0.5 : 1,
                }}
              >
                {busy ? 'Сохраняем…' : 'Сменить пароль'}
              </button>
            </form>
          )}
        </div>

        {/* Features strip */}
        <div style={{
          marginTop: 32,
          display: 'flex',
          justifyContent: 'center',
          gap: 24,
          fontSize: 11,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          color: 'var(--muted)',
        }}>
          <span>Leakage Guard</span>
          <span>·</span>
          <span>Conformal Intervals</span>
          <span>·</span>
          <span>Profit Threshold</span>
          <span>·</span>
          <span>REST API</span>
        </div>
      </div>
    </div>
  )
}
