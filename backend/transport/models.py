from django.contrib.auth.models import User
from django.db import models


class School(models.Model):
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name


class Route(models.Model):
    """One bus doing one trip. Its live position is stored right here."""
    STATUS_CHOICES = [('not_started', 'Not started'), ('in_progress', 'In progress'), ('completed', 'Completed')]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='routes')
    name = models.CharField(max_length=200)
    bus_number = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_started')
    current_latitude = models.FloatField(null=True, blank=True)
    current_longitude = models.FloatField(null=True, blank=True)
    location_updated_at = models.DateTimeField(null=True, blank=True)
    # Driving seconds per leg from Google, fetched once when the trip starts. Empty = no Google data.
    leg_seconds = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f'{self.name} ({self.bus_number})'


class Stop(models.Model):
    """A pickup point on a route. `order` is the sequence the bus visits them in."""
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name='stops')
    name = models.CharField(max_length=200)
    latitude = models.FloatField()
    longitude = models.FloatField()
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f'{self.order}. {self.name}'


class Profile(models.Model):
    """Extra info on top of Django's built-in User: which role they play and where."""
    ROLE_CHOICES = [('admin', 'School admin'), ('conductor', 'Conductor'), ('parent', 'Parent')]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    assigned_route = models.ForeignKey(Route, null=True, blank=True, on_delete=models.SET_NULL)  # conductors only

    def __str__(self):
        return f'{self.user.username} ({self.role})'


class Student(models.Model):
    STATUS_CHOICES = [('not_boarded', 'Not boarded'), ('boarded', 'Boarded'), ('dropped', 'Dropped')]

    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    stop = models.ForeignKey(Stop, on_delete=models.SET_NULL, null=True, related_name='students')
    parent = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='children')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_boarded')

    def __str__(self):
        return self.name


class AttendanceEvent(models.Model):
    """A log row every time a conductor marks a student. Never edited, only added."""
    KIND_CHOICES = [('boarded', 'Boarded'), ('dropped', 'Dropped')]

    route = models.ForeignKey(Route, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    marked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
