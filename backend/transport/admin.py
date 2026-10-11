from django.contrib import admin

from .models import AttendanceEvent, Profile, Route, School, Stop, Student


class StopInline(admin.TabularInline):
    model = Stop
    extra = 0


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ['name', 'bus_number', 'school', 'status', 'location_updated_at']
    inlines = [StopInline]


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['name', 'stop', 'parent', 'status']


@admin.register(AttendanceEvent)
class AttendanceEventAdmin(admin.ModelAdmin):
    list_display = ['student', 'kind', 'route', 'marked_by', 'created_at']


admin.site.register([School, Profile])
