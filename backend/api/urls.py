from django.urls import path
from . import views

urlpatterns = [
    path('sessions/', views.create_session, name='create_session'),
    path('preview/', views.preview_questions, name='preview_questions'),
]
