"""Who is allowed to see which routes. Used by both the REST API and the WebSocket."""
from .models import Route


def routes_for(user):
    """Admin: every route in their school. Conductor: only their assigned bus.
    Parent: only the routes their children ride."""
    profile = user.profile
    if profile.role == 'admin':
        return Route.objects.filter(school=profile.school)
    if profile.role == 'conductor':
        return Route.objects.filter(pk=profile.assigned_route_id)
    return Route.objects.filter(stops__students__parent=user).distinct()


def is_conductor_of(user, route):
    return user.profile.role == 'conductor' and user.profile.assigned_route_id == route.id
