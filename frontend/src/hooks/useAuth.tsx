import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from '../api/client'

export type User = {
  id: number
  email: string
  display_name: string
  role: 'admin' | 'builder' | 'viewer'
  must_change_password: boolean
}

type AuthState = {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<User>
  logout: () => Promise<void>
  refresh: () => Promise<void>
  setUser: (u: User | null) => void
}

const Ctx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const me = await api<User>('/api/auth/me')
      setUser(me)
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void refresh() }, [refresh])

  const login = useCallback(async (email: string, password: string) => {
    const res = await api<{ user: User }>('/api/auth/login', { json: { email, password } })
    setUser(res.user)
    return res.user
  }, [])

  const logout = useCallback(async () => {
    await api('/api/auth/logout', { method: 'POST' })
    setUser(null)
  }, [])

  return (
    <Ctx.Provider value={{ user, loading, login, logout, refresh, setUser }}>
      {children}
    </Ctx.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAuth вне AuthProvider')
  return ctx
}
