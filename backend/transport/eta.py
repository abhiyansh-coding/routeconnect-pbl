"""ETA calculation.

Google's Routes API knows real roads and traffic, but every call costs money. So:
  - ONE call when the trip starts: Google returns the driving time for each leg
    (stop 1 -> stop 2, stop 2 -> stop 3, ...). We save those times on the route.
  - Every GPS update after that is FREE: we work out which leg the bus is on and how far
    along it is, and use Google's leg times for the rest.
If there's no API key, or the call fails, legs are timed from straight-line distance at an
average speed instead, so the app still works.
"""
import json
import logging
import urllib.request
from math import asin, cos, radians, sin, sqrt

from django.conf import settings

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371
AVERAGE_BUS_SPEED_KMPH = 20  # fallback only; city traffic with stops
ROUTES_API_URL = 'https://routes.googleapis.com/directions/v2:computeRoutes'


def haversine_km(lat1, lon1, lat2, lon2):
    """Straight-line distance between two GPS points on the Earth's surface."""
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def _stop_km(a, b):
    return haversine_km(a.latitude, a.longitude, b.latitude, b.longitude)


def fetch_google_leg_seconds(stops):
    """One Routes API call: first stop -> every stop in order -> last stop.
    Returns the driving seconds for each leg, e.g. [312, 240, 405], or None on any failure."""
    if not settings.GOOGLE_MAPS_API_KEY or len(stops) < 2:
        return None

    def waypoint(stop):
        return {'location': {'latLng': {'latitude': stop.latitude, 'longitude': stop.longitude}}}

    body = {
        'origin': waypoint(stops[0]),
        'destination': waypoint(stops[-1]),
        'intermediates': [waypoint(s) for s in stops[1:-1]],
        'travelMode': 'DRIVE',
        'routingPreference': 'TRAFFIC_AWARE',
    }
    request = urllib.request.Request(ROUTES_API_URL, data=json.dumps(body).encode(), headers={
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': settings.GOOGLE_MAPS_API_KEY,
        'X-Goog-FieldMask': 'routes.legs.duration',  # ask only for what we use
    })
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            legs = json.load(response)['routes'][0]['legs']
        seconds = [float(leg['duration'].rstrip('s')) for leg in legs]  # Google sends "312s"
    except Exception as e:  # network down, bad key, quota, odd response: fall back, don't crash
        logger.warning('Google Routes API failed, using straight-line ETA: %s', e)
        return None
    return seconds if len(seconds) == len(stops) - 1 else None


def straight_line_leg_seconds(stops):
    """Fallback leg times: straight-line distance at the average speed."""
    return [_stop_km(a, b) / AVERAGE_BUS_SPEED_KMPH * 3600 for a, b in zip(stops, stops[1:])]


def stop_etas(bus_lat, bus_lng, stops, leg_seconds=None):
    """Minutes until the bus reaches each stop, as {stop_id: minutes}. Passed stops get None.

    `stops` must be in visiting order; `leg_seconds` are Google's times (None = fallback).
    Step 1: find which leg (stop A -> stop B) the bus is on. It's the leg where going
    A -> bus -> B adds the least extra distance over A -> B (a bus on the leg adds zero).
    Step 2: the share of that leg still to drive, times its time, gives the ETA to B.
    Step 3: each later stop adds its leg's time.
    The trip is assumed to begin at the first stop.
    """
    if not stops:
        return {}
    to_bus = [haversine_km(bus_lat, bus_lng, s.latitude, s.longitude) for s in stops]
    if len(stops) == 1:
        return {stops[0].id: round(to_bus[0] / AVERAGE_BUS_SPEED_KMPH * 60)}
    legs = leg_seconds or straight_line_leg_seconds(stops)

    leg = min(range(len(stops) - 1),
              key=lambda i: to_bus[i] + to_bus[i + 1] - _stop_km(stops[i], stops[i + 1]))
    done, left = to_bus[leg], to_bus[leg + 1]
    seconds = legs[leg] * (left / (done + left) if done + left else 0)

    etas = {}
    for i, stop in enumerate(stops):
        if i <= leg:
            etas[stop.id] = None
            continue
        if i > leg + 1:
            seconds += legs[i - 1]
        etas[stop.id] = round(seconds / 60)
    return etas
