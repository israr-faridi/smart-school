from django.contrib.auth import views as auth
from django.urls import path

from core import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', auth.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth.LogoutView.as_view(), name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('actions/<slug:action>/', views.action, name='action'),
    path('check-in/<int:pk>/photo/', views.photo, name='photo'),
    path('transcript/<int:pk>/', views.transcript, name='transcript'),
    path('verify/<str:token>/', views.verify, name='verify'),
]
