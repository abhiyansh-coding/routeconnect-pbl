import { useEffect, useState } from 'react'
import { api } from './api.js'

const SIM_STEPS_BETWEEN_STOPS = 15
const SIM_TICK_MS = 1000

// Start/end the trip and send the bus's position. Two ways to send it:
//  - "Share my GPS": the phone's real location (browser Geolocation API)
//  - "Simulate drive": fake points moving along the stops, for demos indoors
export default function ConductorPanel({ route, sendLocation }) {
  const [mode, setMode] = useState(null) // null | 'gps' | 'sim'
  const [error, setError] = useState('')
  const live = route.status === 'in_progress'

  useEffect(() => {
    if (!live || !mode) return

    if (mode === 'gps') {
      const id = navigator.geolocation.watchPosition(
        (pos) => sendLocation(pos.coords.latitude, pos.coords.longitude),
        (err) => setError(err.message),
        { enableHighAccuracy: true },
      )
      return () => navigator.geolocation.clearWatch(id)
    }

    const points = interpolate(route.stops)
    let i = 0
    const timer = setInterval(() => {
      sendLocation(...points[i])
      i = Math.min(i + 1, points.length - 1)
    }, SIM_TICK_MS)
    return () => clearInterval(timer)
    // Only restart when the trip or mode changes. sendLocation is a new function every render
    // but always uses the same socket, so it doesn't need to be listed.
  }, [live, mode])

  async function setTrip(action) {
    setError('')
    try {
      await api(`/routes/${route.id}/${action}/`, { method: 'POST' })
      if (action === 'end') setMode(null)
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="panel">
      {!live ? (
        <button onClick={() => setTrip('start')}>Start trip</button>
      ) : (
        <>
          <button className={mode === 'gps' ? 'active' : ''} onClick={() => setMode(mode === 'gps' ? null : 'gps')}>
            {mode === 'gps' ? 'Stop GPS' : 'Share my GPS'}
          </button>
          <button className={mode === 'sim' ? 'active' : ''} onClick={() => setMode(mode === 'sim' ? null : 'sim')}>
            {mode === 'sim' ? 'Stop simulation' : 'Simulate drive'}
          </button>
          <button className="danger" onClick={() => setTrip('end')}>End trip</button>
        </>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  )
}

// Straight-line points between each pair of consecutive stops.
function interpolate(stops) {
  const points = []
  for (let i = 0; i < stops.length - 1; i++) {
    const a = stops[i], b = stops[i + 1]
    for (let t = 0; t < SIM_STEPS_BETWEEN_STOPS; t++) {
      const f = t / SIM_STEPS_BETWEEN_STOPS
      points.push([a.latitude + (b.latitude - a.latitude) * f, a.longitude + (b.longitude - a.longitude) * f])
    }
  }
  const last = stops.at(-1)
  points.push([last.latitude, last.longitude])
  return points
}
