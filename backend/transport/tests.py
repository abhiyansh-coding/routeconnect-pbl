import io
import json
from unittest import mock

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TransactionTestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from routeconnect.asgi import application

from .eta import fetch_google_leg_seconds, haversine_km, stop_etas
from .models import AttendanceEvent, Route, Stop, Student


class EtaTests(TransactionTestCase):
    def test_haversine_known_distance(self):
        # Pune to Mumbai is about 120 km in a straight line.
        self.assertAlmostEqual(haversine_km(18.5204, 73.8567, 19.0760, 72.8777), 120, delta=5)

    # Four stops due north of each other, about 1.1 km apart.
    stops = [Stop(id=i, latitude=18.50 + i * 0.01, longitude=73.80, order=i) for i in range(1, 5)]

    def test_at_a_stop(self):
        etas = stop_etas(18.52, 73.80, self.stops)  # sitting exactly on stop 2
        self.assertEqual(etas, {1: None, 2: 0, 3: 3, 4: 7})

    def test_just_left_a_stop_counts_it_as_passed(self):
        # 200 m past stop 2: stop 2 is still the nearest stop, but the bus is heading to stop 3.
        etas = stop_etas(18.5218, 73.80, self.stops)
        self.assertIsNone(etas[2])
        self.assertLess(etas[3], etas[4])


    def test_google_leg_times_are_used(self):
        # Google says each leg takes 10 minutes (traffic), not ~3 at our average speed.
        etas = stop_etas(18.52, 73.80, self.stops, leg_seconds=[600, 600, 600])
        self.assertEqual(etas, {1: None, 2: 0, 3: 10, 4: 20})

    @override_settings(GOOGLE_MAPS_API_KEY='test-key')
    def test_google_response_parsed(self):
        reply = io.BytesIO(json.dumps(
            {'routes': [{'legs': [{'duration': '312s'}, {'duration': '240s'}, {'duration': '405s'}]}]}
        ).encode())
        with mock.patch('urllib.request.urlopen', return_value=reply) as urlopen:
            self.assertEqual(fetch_google_leg_seconds(self.stops), [312, 240, 405])
        sent = urlopen.call_args.args[0]
        self.assertEqual(sent.get_header('X-goog-api-key'), 'test-key')
        self.assertEqual(len(json.loads(sent.data)['intermediates']), 2)

    @override_settings(GOOGLE_MAPS_API_KEY='test-key')
    def test_google_failure_falls_back(self):
        with mock.patch('urllib.request.urlopen', side_effect=OSError('no internet')):
            self.assertIsNone(fetch_google_leg_seconds(self.stops))

    @override_settings(GOOGLE_MAPS_API_KEY='')
    def test_no_key_means_no_call(self):
        with mock.patch('urllib.request.urlopen') as urlopen:
            self.assertIsNone(fetch_google_leg_seconds(self.stops))
        urlopen.assert_not_called()

class ApiTests(TransactionTestCase):
    def setUp(self):
        call_command('seed', stdout=open('/dev/null', 'w'))
        self.route = Route.objects.get()

    def client_for(self, username):
        client = APIClient()
        token = client.post('/api/login/', {'username': username, 'password': 'pbl12345'}).data['token']
        client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
        return client

    def test_login_required(self):
        self.assertEqual(APIClient().get('/api/routes/').status_code, 401)

    def test_parent_sees_only_own_children(self):
        data = self.client_for('parent').get('/api/routes/').data
        names = {s['name'] for stop in data[0]['stops'] for s in stop['students']}
        self.assertEqual(names, {'Aarav Sharma', 'Diya Patil'})

    def test_only_conductor_can_mark_attendance(self):
        student = Student.objects.get(name='Kabir Joshi')
        url = f'/api/routes/{self.route.id}/attendance/'
        body = {'student': student.id, 'kind': 'boarded'}
        self.assertEqual(self.client_for('parent').post(url, body).status_code, 403)
        self.assertEqual(self.client_for('conductor').post(url, body).status_code, 200)
        self.assertEqual(AttendanceEvent.objects.get().kind, 'boarded')


class WebSocketTests(TransactionTestCase):
    def setUp(self):
        call_command('seed', stdout=open('/dev/null', 'w'))
        self.route = Route.objects.get()
        self.route.status = 'in_progress'
        self.route.save()

    def connect(self, username):
        token, _ = Token.objects.get_or_create(user=User.objects.get(username=username))
        return WebsocketCommunicator(application, f'/ws/routes/{self.route.id}/?token={token.key}')

    def test_conductor_location_reaches_parent(self):
        parent, conductor = self.connect('parent'), self.connect('conductor')

        async def run():
            self.assertTrue((await parent.connect())[0])
            self.assertTrue((await conductor.connect())[0])

            await conductor.send_json_to({'lat': 18.5236, 'lng': 73.8410})
            msg = await parent.receive_json_from()
            self.assertEqual(msg['kind'], 'location')
            self.assertEqual(msg['lat'], 18.5236)

            await parent.send_json_to({'lat': 0, 'lng': 0})  # parents can't move the bus
            self.assertTrue(await parent.receive_nothing())
            await parent.disconnect()
            await conductor.disconnect()

        async_to_sync(run)()

    def test_bad_token_rejected(self):
        async def run():
            ws = WebsocketCommunicator(application, f'/ws/routes/{self.route.id}/?token=wrong')
            connected, _ = await ws.connect()
            self.assertFalse(connected)

        async_to_sync(run)()
