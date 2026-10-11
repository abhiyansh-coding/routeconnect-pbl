from django.urls import path

from . import views

urlpatterns = [
    path('login/', views.LoginView.as_view()),
    path('routes/', views.route_list),
    path('routes/<int:pk>/', views.route_detail),
    path('routes/<int:pk>/start/', views.start_trip),
    path('routes/<int:pk>/end/', views.end_trip),
    path('routes/<int:pk>/attendance/', views.mark_attendance),
]
