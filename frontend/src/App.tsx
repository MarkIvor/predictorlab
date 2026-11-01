import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './hooks/useAuth'
import Login from './pages/Login'
import Hangar from './pages/Hangar'
import NewModel from './pages/NewModel'
import ModelPage from './pages/ModelPage'
import Admin from './pages/Admin'
import PublicPage from './pages/PublicPage'
import DocsPage from './pages/DocsPage'

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="page muted">…</div>
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/p/:slug" element={<PublicPage />} />
      <Route path="/docs-page" element={<DocsPage />} />
      <Route path="/" element={<Protected><Hangar /></Protected>} />
      <Route path="/new" element={<Protected><NewModel /></Protected>} />
      <Route path="/m/:id/*" element={<Protected><ModelPage /></Protected>} />
      <Route path="/admin" element={<Protected><Admin /></Protected>} />
    </Routes>
  )
}
