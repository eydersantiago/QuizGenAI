from django.urls import path
from . import views

urlpatterns = [
    path("sessions/", views.sessions, name="sessions"),
    path("preview/", views.preview_questions, name="preview_questions"),
    path("regenerate/", views.regenerate_question, name="regenerate_question"),
    path("confirm-replace/", views.confirm_replace, name="confirm_replace"),

    path("gemini-generate/", views.gemini_generate, name="gemini_generate"),  # opcional: tu prueba libre
]
