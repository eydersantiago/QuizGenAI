from django.urls import path
from . import views
from .views_metrics import metrics_summary, metrics_export
from .views_saved_quizzes import (
    saved_quizzes, saved_quiz_detail, load_saved_quiz, quiz_statistics
)

urlpatterns = [
    path("health/", views.health_check, name="health_check"),
    
    path("sessions/", views.sessions, name="sessions"),
    path("preview/", views.preview_questions, name="preview_questions"),
    path("regenerate/", views.regenerate_question, name="regenerate_question"),
    path("confirm-replace/", views.confirm_replace, name="confirm_replace"),

     # nuevos (HU-11)
    path("metrics/", metrics_summary, name="metrics_summary"),
    path("metrics/export/", metrics_export, name="metrics_export"),

    # Cuestionarios guardados (nueva funcionalidad)
    path("saved-quizzes/", saved_quizzes, name="saved_quizzes"),
    path("saved-quizzes/<uuid:quiz_id>/", saved_quiz_detail, name="saved_quiz_detail"),
    path("saved-quizzes/<uuid:quiz_id>/load/", load_saved_quiz, name="load_saved_quiz"),
    path("saved-quizzes/statistics/", quiz_statistics, name="quiz_statistics"),

    path("gemini-generate/", views.gemini_generate, name="gemini_generate"),  # opcional: tu prueba libre
]
