from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .eta import fetch_google_leg_seconds
from .models import AttendanceEvent
from .permissions import is_conductor_of, routes_for
from .serializers import AttendanceSerializer, RouteSerializer


class LoginView(ObtainAuthToken):
    """POST username + password -> token. The app sends this token on every later request."""

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key, 'username': user.username, 'role': user.profile.role})


def broadcast(route_id, message):
    """Push a message to everyone watching this route over WebSocket."""
    async_to_sync(get_channel_layer().group_send)(f'route_{route_id}', {'type': 'route.event', 'data': message})


def own_route(request, pk):
    """Fetch a route the user may see (404 otherwise), and insist they're its conductor."""
    route = get_object_or_404(routes_for(request.user), pk=pk)
    if not is_conductor_of(request.user, route):
        raise PermissionDenied('Only the assigned conductor can do this.')
    return route


@api_view(['GET'])
def route_list(request):
    routes = routes_for(request.user).prefetch_related('stops__students')
    return Response(RouteSerializer(routes, many=True, context={'request': request}).data)


@api_view(['GET'])
def route_detail(request, pk):
    route = get_object_or_404(routes_for(request.user), pk=pk)
    return Response(RouteSerializer(route, context={'request': request}).data)


@api_view(['POST'])
def start_trip(request, pk):
    route = own_route(request, pk)
    route.status = 'in_progress'
    route.leg_seconds = fetch_google_leg_seconds(list(route.stops.all()))  # the one paid call per trip
    route.save()
    for stop in route.stops.all():
        stop.students.update(status='not_boarded')  # fresh trip, everyone starts unboarded
    broadcast(route.id, {'kind': 'status', 'status': route.status})
    return Response({'status': route.status})


@api_view(['POST'])
def end_trip(request, pk):
    route = own_route(request, pk)
    route.status = 'completed'
    route.save()
    broadcast(route.id, {'kind': 'status', 'status': route.status})
    return Response({'status': route.status})


@api_view(['POST'])
def mark_attendance(request, pk):
    route = own_route(request, pk)
    serializer = AttendanceSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    student, kind = serializer.validated_data['student'], serializer.validated_data['kind']
    if student.stop is None or student.stop.route_id != route.id:
        return Response({'detail': 'Student is not on this route.'}, status=status.HTTP_400_BAD_REQUEST)

    student.status = kind
    student.save()
    AttendanceEvent.objects.create(route=route, student=student, kind=kind, marked_by=request.user)
    broadcast(route.id, {'kind': 'attendance', 'student': student.id, 'status': kind})
    return Response({'student': student.id, 'status': kind})
