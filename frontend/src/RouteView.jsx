import { useEffect, useRef, useState } from 'react'
import { CircleMarker, MapContainer, Marker, Polyline, TileLayer, Tooltip } from 'react-leaflet'
import L from 'leaflet'
import { api, openRouteSocket } from './api.js'
import ConductorPanel from './ConductorPanel.jsx'

const busIcon = L.divIcon({ className: 'bus-icon', html: '🚌', iconSize: [32, 32] })

// One bus route: map, stops with live ETAs, and students. Everyone sees this;
// the conductor also gets the controls panel.
export default function RouteView({ initial, role }) {
  const [route, setRoute] = useState(initial)
  const [etas, setEtas] = useState({})
  const [etaSource, setEtaSource] = useState(null) // 'google' | 'straight_line'
  const socket = useRef(null)

  // Keep a WebSocket open and apply every message the server pushes. Phones lose signal,
  // so if the connection drops we reconnect after 2 s and reload the route to catch up on
  // anything we missed while offline.
  useEffect(() => {
    let ws, retryTimer
    let unmounted = false

    function handle(msg) {
      if (msg.kind === 'location') {
        setRoute((r) => ({ ...r, current_latitude: msg.lat, current_longitude: msg.lng, location_updated_at: msg.at }))
        setEtas(msg.etas)
        setEtaSource(msg.eta_source)
      } else if (msg.kind === 'status') {
        // Trip started or ended. The server reset some data (students back to "not boarded"),
        // so everyone watching reloads the route.
        api(`/routes/${initial.id}/`).then(setRoute)
        setEtas({})
      } else if (msg.kind === 'attendance') {
        setRoute((r) => ({
          ...r,
          stops: r.stops.map((s) => ({
            ...s,
            students: s.students.map((st) => (st.id === msg.student ? { ...st, status: msg.status } : st)),
          })),
        }))
      }
    }

    function connect() {
      ws = openRouteSocket(initial.id)
      ws.onmessage = (e) => handle(JSON.parse(e.data))
      ws.onopen = () => api(`/routes/${initial.id}/`).then(setRoute)
      ws.onclose = (e) => {
        // 4403 = server refused us (bad token / not our bus): retrying won't help.
        if (!unmounted && e.code !== 4403) retryTimer = setTimeout(connect, 2000)
      }
      socket.current = ws
    }

    connect()
    return () => {
      unmounted = true
      clearTimeout(retryTimer)
      ws.close()
    }
  }, [initial.id])

  const sendLocation = (lat, lng) => {
    if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify({ lat, lng }))
  }

  const path = route.stops.map((s) => [s.latitude, s.longitude])
  const hasBus = route.current_latitude != null && route.status === 'in_progress'

  return (
    <section className="card">
      <div className="route-head">
        <div>
          <h2>{route.name}</h2>
          <span className="muted">Bus {route.bus_number}</span>
        </div>
        <span className={`badge ${route.status}`}>{route.status.replace('_', ' ')}</span>
      </div>

      <MapContainer bounds={path} boundsOptions={{ padding: [30, 30] }} className="map">
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution="&copy; OpenStreetMap contributors"
        />
        <Polyline positions={path} pathOptions={{ color: '#2563eb', weight: 4, opacity: 0.5 }} />
        {route.stops.map((s) => (
          <CircleMarker key={s.id} center={[s.latitude, s.longitude]} radius={7} pathOptions={{ color: '#1e3a8a' }}>
            <Tooltip>{s.order}. {s.name}</Tooltip>
          </CircleMarker>
        ))}
        {hasBus && <Marker position={[route.current_latitude, route.current_longitude]} icon={busIcon} />}
      </MapContainer>

      {role === 'conductor' && <ConductorPanel route={route} sendLocation={sendLocation} />}

      {etaSource && route.status === 'in_progress' && (
        <p className="muted">
          ETA: {etaSource === 'google' ? 'Google Routes, live traffic' : 'straight-line estimate (no Google data)'}
        </p>
      )}
      <ol className="stops">
        {route.stops.map((s) => (
          <li key={s.id}>
            <div className="stop-row">
              <span>{s.name}</span>
              <span className="muted">
                {etas[s.id] === null ? 'passed' : etas[s.id] !== undefined ? `${etas[s.id]} min` : ''}
              </span>
            </div>
            {s.students.map((st) => (
              <div key={st.id} className="student-row">
                <span>{st.name}</span>
                <span className={`badge ${st.status}`}>{st.status.replace('_', ' ')}</span>
                {role === 'conductor' && route.status === 'in_progress' && (
                  <AttendanceButtons routeId={route.id} student={st} />
                )}
              </div>
            ))}
          </li>
        ))}
      </ol>
    </section>
  )
}

function AttendanceButtons({ routeId, student }) {
  const mark = (kind) => api(`/routes/${routeId}/attendance/`, { method: 'POST', body: { student: student.id, kind } })
  // No local state update here: the server broadcasts the change back over the WebSocket.
  return student.status === 'not_boarded'
    ? <button className="small" onClick={() => mark('boarded')}>Board</button>
    : student.status === 'boarded'
      ? <button className="small" onClick={() => mark('dropped')}>Drop</button>
      : null
}
