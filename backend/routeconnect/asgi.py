"""Entry point for the server. Sends normal HTTP requests to Django and WebSocket
connections to Channels."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'routeconnect.settings')
django_asgi_app = get_asgi_application()  # must load Django before importing app code

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from transport.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': URLRouter(websocket_urlpatterns),
})
