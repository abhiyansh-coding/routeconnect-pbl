"""`python manage.py seed` fills an empty database with one school, one bus route and
three demo logins, so the app can be shown without typing data in by hand."""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from transport.models import Profile, Route, School, Stop, Student

PASSWORD = 'pbl12345'
STOPS = [  # (name, lat, lng) in the order the bus drives them, around Pune
    ('Shivajinagar', 18.5308, 73.8475),
    ('FC Road', 18.5236, 73.8410),
    ('Deccan Gymkhana', 18.5158, 73.8418),
    ('Nal Stop', 18.5095, 73.8320),
    ('Karve Nagar (School)', 18.4893, 73.8193),
]


class Command(BaseCommand):
    help = 'Create demo school, route, stops, students and users'

    def handle(self, *args, **options):
        if School.objects.exists():
            self.stdout.write('Already seeded. Delete db.sqlite3 and migrate again to start over.')
            return

        school = School.objects.create(name='Demo Public School')
        route = Route.objects.create(school=school, name='Route 1 - Morning', bus_number='MH12 AB 1234')
        stops = [Stop.objects.create(route=route, name=n, latitude=la, longitude=lo, order=i)
                 for i, (n, la, lo) in enumerate(STOPS, start=1)]

        def make_user(username, role, **extra):
            user = User.objects.create_user(username, password=PASSWORD,
                                            is_staff=role == 'admin', is_superuser=role == 'admin')
            Profile.objects.create(user=user, role=role, school=school, **extra)
            return user

        make_user('admin', 'admin')
        make_user('conductor', 'conductor', assigned_route=route)
        parent = make_user('parent', 'parent')

        Student.objects.create(school=school, name='Aarav Sharma', stop=stops[1], parent=parent)
        Student.objects.create(school=school, name='Diya Patil', stop=stops[1], parent=parent)
        Student.objects.create(school=school, name='Kabir Joshi', stop=stops[0])
        Student.objects.create(school=school, name='Meera Kulkarni', stop=stops[2])
        Student.objects.create(school=school, name='Rohan Desai', stop=stops[3])

        self.stdout.write(self.style.SUCCESS(
            f'Seeded. Log in as admin / conductor / parent, password: {PASSWORD}'))
