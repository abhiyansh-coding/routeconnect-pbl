# How RouteConnect works

## 1. The problem

Parents of children who take the school bus don't know where the bus is. They wait at the
stop, sometimes for 20+ minutes, or call the school, which doesn't know either. The school
has no record of which children actually got on the bus.

**RouteConnect** fixes this with three things:

1. **Live location.** The conductor's phone sends the bus's GPS position every few seconds.
2. **ETA.** Parents see how many minutes until the bus reaches their child's stop.
3. **Attendance.** The conductor taps *Board* / *Drop* for each child, and the parent sees
   it at once.

Three kinds of users, each seeing something different:

| Role | Sees | Can do |
|---|---|---|
| School admin | Every route in their school, every student | Manage data in the admin panel |
| Conductor | Only their own bus | Start/end trip, share GPS, mark attendance |
| Parent | Only the bus their child rides, and only *their own* children | Watch |

## 2. Architecture

```
 Conductor's phone                    Server                          Parent's phone
 ─────────────────                    ──────                          ──────────────
 React app                                                            React app
   │  GPS from browser                Django + Channels (Daphne)        ▲
   │  {lat, lng}                      ┌──────────────────────────┐      │ {kind:"location",
   └──── WebSocket ────────────────►  │ RouteConsumer            │      │  lat, lng, etas}
                                      │  1. check: conductor?    │      │
                                      │  2. save to DB           │──────┘ WebSocket
                                      │  3. compute ETAs         │
                                      │  4. send to group        │
                                      │     "route_1"            │
   POST /api/routes/1/attendance/ ──► │ REST views (DRF)         │──────► {kind:"attendance"}
                                      └────────────┬─────────────┘
                                                   │ Django ORM
                                                   ▼
                                               SQLite DB
```

**Two ways of talking to the server**, and why both:

- **REST (HTTP)** for normal request → response actions: log in, load the route, start a
  trip, mark attendance. The client asks, the server answers, the connection closes.
- **WebSocket** for live location. The connection **stays open**, so the server can push
  a new position to parents the moment it arrives. With plain HTTP the parent's app would
  have to ask "where's the bus?" every few seconds (*polling*). That wastes battery and
  data, and the map would always lag behind.

## 3. The life of one GPS point

This is the core of the project. Follow one location update from the bus to the parent:

1. **Browser gets GPS.** `ConductorPanel.jsx` calls `navigator.geolocation.watchPosition(...)`,
   which fires every time the phone's location changes. (Or *Simulate drive* generates fake
   points along the route every second, for indoor demos.)
2. **Sent over the WebSocket.** `RouteView.jsx` → `sendLocation()` sends
   `{"lat": 18.52, "lng": 73.84}` on the already-open socket to `/ws/routes/1/`.
3. **ASGI routes it.** `routeconnect/asgi.py` sees it's a WebSocket, not HTTP, and passes it to
   `transport/routing.py`, which maps `ws/routes/<id>/` → `RouteConsumer`.
4. **Consumer checks permission.** `consumers.py` → `receive_json()`: is this user the
   conductor of *this* route, and is the trip in progress? Are lat/lng valid numbers in
   range? If not, the message is ignored.
5. **Saved.** The route row's `current_latitude/longitude` and `location_updated_at` are
   updated, so someone who opens the app later still sees the last known position.
6. **ETAs calculated.** `eta.py` → `stop_etas()` works out minutes to every stop, using the
   Google leg times fetched when the trip started. No API call here, so it's free.
7. **Broadcast.** `channel_layer.group_send("route_1", ...)` delivers the message to *every*
   socket in the group: all parents and admins watching that bus.
8. **Parent's screen updates.** Each parent's `RouteView.jsx` gets the message in
   `ws.onmessage`, calls `setRoute(...)` and `setEtas(...)`, and React re-draws the bus
   marker and the "4 min" labels.

Total time: well under a second.

## 4. Database design

```
School 1───* Route 1───* Stop 1───* Student *───1 User (parent)
               │                                   │
               │ 1                                 │ 1
               *                                   1
         AttendanceEvent *───1 Student         Profile (role, school, assigned_route)
```

| Table | Key fields | Notes |
|---|---|---|
| `School` | name | Top of the tree. Everything belongs to a school. |
| `Route` | school, name, bus_number, status, current_latitude/longitude | One bus trip. The **live position lives on the route row.** |
| `Stop` | route, name, latitude, longitude, order | `order` = the sequence the bus visits stops in. |
| `Student` | school, name, stop, parent, status | Linking a student to a **stop** (not just a route) is what lets us show "ETA to *your child's* stop". |
| `Profile` | user, role, school, assigned_route | Django has a built-in `User` table (username, password hash). Profile adds our fields with a one-to-one link instead of rewriting User. |
| `AttendanceEvent` | route, student, kind, marked_by, created_at | **Append-only log.** `Student.status` is the current state; the events are the history (who marked it, when). |

Design choices worth knowing:

- **Why store status on Student *and* keep AttendanceEvent?** Status gives a fast answer to
  "is Aarav on the bus *now*?". The event log answers "what happened on Tuesday?" and
  "which conductor marked it?". If someone disputes a record, the log is the evidence.
- **`on_delete` rules.** Deleting a route deletes its stops (`CASCADE`). Deleting a stop
  does *not* delete the students on it (`SET_NULL`), because the child still exists.

## 5. Backend, file by file (`backend/`)

| File | What it does |
|---|---|
| `routeconnect/settings.py` | Config. Installed apps (`daphne`, `rest_framework`, `channels`, `transport`), token auth as default, `CHANNEL_LAYERS`. |
| `routeconnect/urls.py` | `/admin/` → Django admin, `/api/` → our app. |
| `routeconnect/asgi.py` | Server entry point. `ProtocolTypeRouter` sends HTTP to Django and WebSockets to Channels. |
| `transport/models.py` | The six tables above. Django turns these classes into SQL tables via **migrations**. |
| `transport/migrations/` | Auto-generated by `makemigrations`. A versioned history of schema changes. |
| `transport/serializers.py` | Converts models ↔ JSON. `StopSerializer.get_students` filters to the parent's own kids. |
| `transport/permissions.py` | `routes_for(user)`: **one function** decides which routes each role can see. The REST API and the WebSocket both use it, so the rules can't drift apart. |
| `transport/views.py` | REST endpoints: login, list/detail routes, start/end trip, mark attendance. |
| `transport/consumers.py` | WebSocket handler: authenticate, join group, receive location, broadcast. |
| `transport/routing.py` | WebSocket URL → consumer (the WebSocket version of `urls.py`). |
| `transport/eta.py` | Google Routes API call (once per trip) + Haversine + ETA maths. |
| `transport/admin.py` | Registers models in Django's admin panel, which is the school admin's data-entry UI. |
| `transport/tests.py` | 12 automated tests. |
| `transport/management/commands/seed.py` | `python manage.py seed` creates demo data. |

### API endpoints

| Method | URL | Who | Does |
|---|---|---|---|
| POST | `/api/login/` | anyone | username + password → token + role |
| GET | `/api/routes/` | logged in | routes this user may see |
| GET | `/api/routes/<id>/` | logged in | one route with stops + students |
| POST | `/api/routes/<id>/start/` | that route's conductor | status → in progress, students reset |
| POST | `/api/routes/<id>/end/` | that route's conductor | status → completed |
| POST | `/api/routes/<id>/attendance/` | that route's conductor | `{student, kind}` → mark boarded/dropped |
| WS | `/ws/routes/<id>/?token=…` | anyone who can see the route | receive live events; conductor also sends `{lat, lng}` |

## 6. Frontend, file by file (`frontend/src/`)

| File | What it does |
|---|---|
| `main.jsx` | Mounts React into `index.html`, loads CSS. |
| `api.js` | `api()` wraps `fetch` and adds `Authorization: Token …` to every request. `openRouteSocket()` opens the WebSocket. Session is kept in `localStorage`. |
| `App.jsx` | Logged out → `<Login>`. Logged in → loads `/api/routes/` and shows a `<RouteView>` per route. |
| `Login.jsx` | Form → `POST /api/login/` → saves token. |
| `RouteView.jsx` | The main screen. Leaflet map (stops, path line, bus 🚌), stop list with ETAs, students with status badges. Opens the WebSocket and updates state on each message. **Auto-reconnects** if the connection drops and reloads the route to catch up. |
| `ConductorPanel.jsx` | Start/End trip. *Share my GPS* (real GPS) or *Simulate drive* (fake points along the route). |
| `vite.config.js` | Dev server **proxy**: `/api` and `/ws` are forwarded to Django on port 8000, so the browser sees one origin and no CORS setup is needed. |

React ideas used: **components**, **state** (`useState`: data that, when changed, re-draws
the screen), **effects** (`useEffect`: side work like opening a socket, with a cleanup
function that closes it), and **refs** (`useRef`: keeps the socket object without causing
re-renders).

## 7. Security

| Concern | How it's handled |
|---|---|
| Who are you? | Token auth. Login returns a random token; every request sends it in a header. Passwords are stored hashed (Django's default: PBKDF2). |
| WebSocket auth | Browsers can't add headers to a WebSocket, so the token goes in the URL (`?token=`). Bad token → connection closed with code 4403. |
| Can a parent move the bus? | No. The consumer only accepts locations from the route's assigned conductor during an active trip (tested). |
| Can a parent see other children? | No. The serializer filters students to `parent=user` (tested). |
| Can a conductor see other buses? | No. `routes_for()` returns only their assigned route. Another route's ID → 404. |
| Bad input | DRF serializers validate attendance input; the consumer checks lat/lng are numbers in range. |

## 8. ETA algorithm (`eta.py`)

ETA uses the **Google Routes API**, the same way production RouteConnect does: the API is
paid per call, so it's called **once per trip**, not on every GPS update.

**At trip start (`views.start_trip`, one paid call).** `fetch_google_leg_seconds()` sends a
`computeRoutes` request: origin = first stop, intermediates = the stops in between,
destination = last stop, `travelMode: DRIVE`, `routingPreference: TRAFFIC_AWARE`. The
`X-Goog-FieldMask` header asks only for `routes.legs.duration`, the driving time of each
leg (stop 1 → 2, 2 → 3, …). Asking for less keeps the response small and the cost
lower. Those times are saved in `Route.leg_seconds`.

**On every GPS update (free, no API call):**

1. **Distance: Haversine.** GPS points sit on a sphere, so plain Pythagoras doesn't work:
   ```
   a = sin²(Δlat/2) + cos(lat1)·cos(lat2)·sin²(Δlng/2)
   d = 2R · asin(√a)          R = 6371 km
   ```
2. **Which leg is the bus on?** Naive approach: "the nearest stop is next". That's wrong
   just after the bus *leaves* a stop: it's still the nearest, so the app said the bus was
   heading back. Instead, for each leg A → B, compute how much extra distance going
   A → bus → B adds over A → B. A bus on that leg adds almost nothing, so the smallest
   value is the leg it's on. (This bug was found in testing, and a test now covers it.)
3. **ETA.** Share of that leg still to drive = `dist(bus,B) / (dist(A,bus) + dist(bus,B))`.
   ETA to B = that share × Google's time for the leg. Each later stop adds its own
   leg's Google time.

**Fallback.** No API key, no internet, bad key or quota exceeded → the call returns
`None` and leg times are estimated from straight-line distance at 20 km/h instead. The
app never breaks because Google is unavailable. The parent's screen shows which source
is in use.

**Limits:** leg times are fixed at trip start, so traffic that changes mid-trip isn't
picked up. Production RouteConnect also saves the road shape Google returns, tracks the
bus along it, and makes a fresh paid call only when the ETA has drifted too far.

## 9. Key concepts, in one paragraph each

- **Django ORM.** Write Python (`Route.objects.filter(school=s)`) instead of SQL. Django
  generates the SQL, so switching SQLite → PostgreSQL is a settings change.
- **Migrations.** Versioned files describing schema changes. `makemigrations` writes them
  from `models.py`; `migrate` applies them to the database.
- **WSGI vs ASGI.** WSGI (classic Django) handles one request → one response. ASGI also
  supports long-lived connections like WebSockets. **Daphne** is the ASGI server; putting
  `daphne` in `INSTALLED_APPS` makes `runserver` use it.
- **Channel layer and groups.** Each WebSocket connection has a "channel". A **group** is a
  named set of channels (`route_1`). `group_send` = send to everyone in it. The layer is the
  message bus behind this; here it's in-memory (one server process). With several server
  processes you'd use **Redis**, so a message from a conductor connected to server A
  reaches a parent connected to server B.
- **Token authentication.** Stateless: the server looks up the token on each request.
  Simpler than sessions + CSRF for a mobile/SPA client.
- **SPA + proxy.** React runs in the browser and only talks JSON to Django. In development
  Vite proxies `/api` and `/ws` to Django. In production you'd build the React app
  (`npm run build`) and serve both behind one web server (e.g. Nginx).

## 10. Testing

`python manage.py test transport` runs 12 tests:

| Test | Proves |
|---|---|
| `test_haversine_known_distance` | Pune → Mumbai ≈ 120 km |
| `test_at_a_stop` | Exact ETA numbers when the bus is on a stop |
| `test_just_left_a_stop_counts_it_as_passed` | The "heading back" bug stays fixed |
| `test_google_leg_times_are_used` | ETAs follow Google's leg times when present |
| `test_google_response_parsed` | Request has the key + stops; `"312s"` parsed (network mocked) |
| `test_google_failure_falls_back` | No internet → fallback, no crash |
| `test_no_key_means_no_call` | No key → Google never called |
| `test_login_required` | No token → 401 |
| `test_parent_sees_only_own_children` | Privacy filter works |
| `test_only_conductor_can_mark_attendance` | Parent → 403, conductor → 200, event logged |
| `test_conductor_location_reaches_parent` | Full WebSocket path; also that a parent sending a fake location is ignored |
| `test_bad_token_rejected` | WebSocket refuses unknown tokens |

The full flow was also tested by hand: conductor and parent in two browsers, simulated
drive, live updates, and restarting the server mid-trip to check auto-reconnect.

## 11. Limitations and future scope

| Now | Production upgrade | Why |
|---|---|---|
| SQLite | PostgreSQL | Many simultaneous writers (every bus, every few seconds) |
| In-memory channel layer | Redis | Several server processes must share groups |
| Location saved on every point | Buffer points (Redis streams) + background workers (Celery) | Hundreds of buses → too many DB writes |
| Username/password | Google sign-in / phone OTP | Parents shouldn't need another password |
| Web app | Native Android/iOS app (React Native / Expo) | GPS keeps running when the screen is off; push notifications |
| Leg times fixed at trip start | Track the bus along Google's road path; refresh only when ETA drifts (as production RouteConnect does) | Traffic changes mid-trip |
| — | Push notification "bus is 5 min away" | Parents don't have to keep the app open |
| — | Arrival detection at stops, trip history, reports | School operations |
