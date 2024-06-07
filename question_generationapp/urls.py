from django.urls import path
from . import views

urlpatterns = [
    path('', views.generate_questions_view, name='generate_question'),
    path('generate_question/', views.generate_questions, name='generate_question'),
    # path('',views.home, name='home'),
    path('register/',views.userregister, name='register'),
    path('user/dashboard/',views.dashboard, name='dashboard'),
    path('login/',views.login, name='login'),
    path('logout/',views.logout, name='logout'),
]
