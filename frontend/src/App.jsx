import { useEffect, useState } from 'react'
import { api, getSession, saveSession } from './api.js'
import Login from './Login.jsx'
import RouteView from './RouteView.jsx'

const ROLE_TITLES = { admin: 'School admin', conductor: 'Conductor', parent: 'Parent' }

export default function App() {
  const [session, setSession] = useState(getSession)
  const [routes, setRoutes] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!session) return
    api('/routes/').then(setRoutes).catch((e) => setError(e.message))
  }, [session])

  function logout() {
    saveSession(null)
    setSession(null)
    setRoutes(null)
  }

  if (!session) return <Login onLogin={setSession} />

  return (
    <div className="page">
      <header>
        <strong>RouteConnect</strong>
        <span className="muted">{ROLE_TITLES[session.role]} · {session.username}</span>
        <button className="link" onClick={logout}>Log out</button>
      </header>
      {error && <p className="error">{error}</p>}
      {routes?.length === 0 && <p className="muted">No routes to show.</p>}
      {routes?.map((r) => <RouteView key={r.id} initial={r} role={session.role} />)}
    </div>
  )
}
