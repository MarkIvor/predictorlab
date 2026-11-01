import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { changePasswordApi } from '../api/endpoints'
import { useAuth } from '../hooks/useAuth'
import { ApiError } from '../api/client'

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

  return (
    <div className="page" style={{ maxWidth: 480, margin: '10vh auto' }}>
      <h1 className="brand" style={{ marginBottom: 24 }}>PREDICTOR<span className="accent">LAB</span></h1>
      <div className="tile">
        <span className="tile-label">{needChange ? 'FIRST LOGIN · CHANGE PASSWORD' : 'SIGN IN'}</span>
        {!needChange ? (
          <form onSubmit={doLogin} style={{ marginTop: 16 }}>
            <div className="field">
              <label>Email</label>
              <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required autoFocus />
            </div>
            <div className="field">
              <label>Пароль</label>
              <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" required />
            </div>
            {error && <p style={{ color: 'var(--danger)', fontSize: 12 }}>{error}</p>}
            <button className="btn btn-ink" disabled={busy} style={{ width: '100%' }}>
              {busy ? '…' : 'ВОЙТИ'}
            </button>
          </form>
        ) : (
          <form onSubmit={doChange} style={{ marginTop: 16 }}>
            <p className="muted" style={{ fontSize: 12 }}>При первом входе нужно сменить пароль (минимум 8 символов)</p>
            <div className="field">
              <label>Текущий пароль</label>
              <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" required />
            </div>
            <div className="field">
              <label>Новый пароль</label>
              <input value={newPassword} onChange={(e) => setNewPassword(e.target.value)} type="password" minLength={8} required />
            </div>
            {error && <p style={{ color: 'var(--danger)', fontSize: 12 }}>{error}</p>}
            <button className="btn btn-ink" disabled={busy} style={{ width: '100%' }}>
              {busy ? '…' : 'СМЕНИТЬ ПАРОЛЬ'}
            </button>
          </form>
        )}
      </div>
      <p className="muted" style={{ fontSize: 11, marginTop: 16 }}>Self-hosted табличный ML: утечки ловятся, интервалы честные, порог по деньгам.</p>
    </div>
  )
}
