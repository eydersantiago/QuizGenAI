from django.urls import path
from rest_framework.routers import DefaultRouter
from . import views
from .views_metrics import metrics_summary, metrics_export
from .voice_metrics_views import log_voice_event, voice_metrics_summary, voice_metrics_export, voice_metrics_events
from .views_tts import voice_token, tts_synthesize
from .views_stt import stt_recognize
from .views_saved_quizzes import (
    saved_quizzes, saved_quiz_detail, load_saved_quiz, quiz_statistics
)

router = DefaultRouter()

urlpatterns = [
    path("health/", views.health_check, name="health_check"),
    
    path("sessions/", views.sessions, name="sessions"),
    path("preview/", views.preview_questions, name="preview_questions"),
    path("regenerate/", views.regenerate_question, name="regenerate_question"),
    path("confirm-replace/", views.confirm_replace, name="confirm_replace"),
     # nuevos (HU-11)
    path("metrics/", metrics_summary, name="metrics_summary"),
    path("metrics/export/", metrics_export, name="metrics_export"),

    # Voice metrics (QGAI-108)
    path("voice-metrics/log/", log_voice_event, name="log_voice_event"),
    path("voice-metrics/summary/", voice_metrics_summary, name="voice_metrics_summary"),
    path("voice-metrics/export/", voice_metrics_export, name="voice_metrics_export"),
    path("voice-metrics/events/", voice_metrics_events, name="voice_metrics_events"),

    # Cuestionarios guardados (nueva funcionalidad)
    path("saved-quizzes/", saved_quizzes, name="saved_quizzes"),
    path("saved-quizzes/<uuid:quiz_id>/", saved_quiz_detail, name="saved_quiz_detail"),
    path("saved-quizzes/<uuid:quiz_id>/load/", load_saved_quiz, name="load_saved_quiz"),
    path("saved-quizzes/statistics/", quiz_statistics, name="quiz_statistics"),

    #Para TTS y STT con Azure
    path("voice/token/", voice_token, name="voice_token"),
    path("voice/tts/", tts_synthesize, name="tts_synthesize"),
    path("voice/stt/", stt_recognize, name="stt_recognize"),

    path("gemini-generate/", views.gemini_generate, name="gemini_generate"),  # opcional: tu prueba libre
]
