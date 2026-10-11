import { useState } from 'react'
import { api, saveSession } from './api.js'

export default function Login({ onLogin }) {
  const [error, setError] = useState('')

  async function submit(e) {
    e.preventDefault()
    const form = new FormData(e.target)
    try {
      const session = await api('/login/', {
        method: 'POST',
        body: { username: form.get('username'), password: form.get('password') },
      })
      saveSession(session)
      onLogin(session)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <form className="login card" onSubmit={submit}>
      <h1>RouteConnect</h1>
      <p className="muted">Live school bus tracking</p>
      <label>Username <input name="username" required autoComplete="username" /></label>
      <label>Password <input name="password" type="password" required autoComplete="current-password" /></label>
      {error && <p className="error">{error}</p>}
      <button>Log in</button>
    </form>
  )
}
