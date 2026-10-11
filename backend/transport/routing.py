"""URL table for WebSockets, the same idea as urls.py is for HTTP."""
from django.urls import path

from .consumers import RouteConsumer

websocket_urlpatterns = [
    path('ws/routes/<int:route_id>/', RouteConsumer.as_asgi()),
]
