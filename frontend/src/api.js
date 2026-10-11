// Every call to the Django API goes through here, so the login token is attached in one place.

export function getSession() {
  return JSON.parse(localStorage.getItem('session') || 'null')
}

export function saveSession(session) {
  if (session) localStorage.setItem('session', JSON.stringify(session))
  else localStorage.removeItem('session')
}

export async function api(path, { method = 'GET', body } = {}) {
  const session = getSession()
  const res = await fetch(`/api${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(session && { Authorization: `Token ${session.token}` }),
    },
    body: body && JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || data.non_field_errors?.[0] || `Request failed (${res.status})`)
  return data
}

export function openRouteSocket(routeId) {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
  return new WebSocket(`${scheme}://${location.host}/ws/routes/${routeId}/?token=${getSession().token}`)
}
