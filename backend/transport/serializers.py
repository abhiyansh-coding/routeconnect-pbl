"""Serializers turn model objects into JSON (and check incoming JSON)."""
from rest_framework import serializers

from .models import Route, Stop, Student


class StudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = ['id', 'name', 'status', 'stop']


class StopSerializer(serializers.ModelSerializer):
    students = serializers.SerializerMethodField()

    class Meta:
        model = Stop
        fields = ['id', 'name', 'latitude', 'longitude', 'order', 'students']

    def get_students(self, stop):
        # Privacy: a parent only ever sees their own children, never other kids on the bus.
        user = self.context['request'].user
        students = stop.students.all()
        if user.profile.role == 'parent':
            students = students.filter(parent=user)
        return StudentSerializer(students, many=True).data


class RouteSerializer(serializers.ModelSerializer):
    stops = StopSerializer(many=True, read_only=True)

    class Meta:
        model = Route
        fields = ['id', 'name', 'bus_number', 'status', 'current_latitude', 'current_longitude',
                  'location_updated_at', 'stops']


class AttendanceSerializer(serializers.Serializer):
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    kind = serializers.ChoiceField(choices=['boarded', 'dropped'])
