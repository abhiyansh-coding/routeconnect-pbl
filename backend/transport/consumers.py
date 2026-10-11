"""The live part. A WebSocket is a connection that stays open so the server can push updates
the moment they happen, instead of the app asking "anything new?" every few seconds.

Everyone watching route 7 joins the group "route_7". When the conductor's phone sends a GPS
point, we save it and send it to the whole group.
"""
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone
from rest_framework.authtoken.models import Token

from .eta import stop_etas
from .permissions import is_conductor_of, routes_for


@database_sync_to_async
def user_from_token(key):
    token = Token.objects.select_related('user__profile').filter(key=key).first()
    return token.user if token else None


@database_sync_to_async
def visible_route(user, route_id):
    return routes_for(user).filter(pk=route_id).first()


@database_sync_to_async
def save_location(route, lat, lng):
    route.current_latitude, route.current_longitude = lat, lng
    route.location_updated_at = timezone.now()
    route.save(update_fields=['current_latitude', 'current_longitude', 'location_updated_at'])
    return stop_etas(lat, lng, list(route.stops.all()), route.leg_seconds), route.location_updated_at.isoformat()


class RouteConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        # Browsers can't set headers on a WebSocket, so the token comes in the URL: ?token=...
        key = parse_qs(self.scope['query_string'].decode()).get('token', [''])[0]
        self.user = await user_from_token(key)
        self.route = self.user and await visible_route(self.user, self.scope['url_route']['kwargs']['route_id'])
        if not self.route:
            await self.close(code=4403)  # not logged in, or not allowed to see this bus
            return
        self.group = f'route_{self.route.id}'
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if getattr(self, 'group', None):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content):
        """Only the bus's own conductor may send locations, and only during a trip."""
        # Re-read: the trip may have started or ended (with new Google leg times) since we connected.
        await database_sync_to_async(self.route.refresh_from_db)(fields=['status', 'leg_seconds'])
        if not is_conductor_of(self.user, self.route) or self.route.status != 'in_progress':
            return
        try:
            lat, lng = float(content['lat']), float(content['lng'])
        except (KeyError, TypeError, ValueError):
            return
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return
        etas, at = await save_location(self.route, lat, lng)
        await self.channel_layer.group_send(self.group, {
            'type': 'route.event',
            'data': {'kind': 'location', 'lat': lat, 'lng': lng, 'at': at, 'etas': etas,
                     'eta_source': 'google' if self.route.leg_seconds else 'straight_line'},
        })

    async def route_event(self, event):
        """Called once per connected client for each group_send of type 'route.event'."""
        await self.send_json(event['data'])
