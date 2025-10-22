# api/views_tts.py
import json
from django.http import JsonResponse, HttpResponse
from rest_framework.decorators import api_view
from rest_framework import status
from django.utils import timezone

from .services.azure_speech import issue_token, synthesize
from .models import VoiceMetricEvent  # para registrar métricas (event_type tts_complete)

@api_view(["GET"])
def voice_token(_request):
    """
    GET /api/voice/token/  -> { token, region }
    """
    try:
        tok = issue_token()
        return JsonResponse({"token": tok, "region": _get_region()}, status=200)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def _get_region():
    import os
    return os.getenv("SPEECH_REGION", "eastus2")

@api_view(["POST"])
def tts_synthesize(request):
    """
    POST /api/voice/tts/
    body: { text: str, voice?: str, format?: str, session_id?: uuid }
    Devuelve audio (binary). Usa cache para ahorrar créditos.
    """
    data = request.data or {}
    text = (data.get("text") or "").strip()
    voice = data.get("voice") or "es-ES-AlvaroNeural"
    fmt = data.get("format") or "audio-16khz-32kbitrate-mono-mp3"
    session_id = data.get("session_id")  # opcional (uuid)

    if not text:
        return JsonResponse({"error": "text is required"}, status=400)

    try:
        audio, latency_ms = synthesize(text=text, voice=voice, fmt=fmt)

        # Registra métrica TTS (usa tu modelo VoiceMetricEvent)
        VoiceMetricEvent.objects.create(  # :contentReference[oaicite:2]{index=2}
            event_type="tts_complete",
            session_id=session_id,
            latency_ms=latency_ms,
            text_length=len(text),
            backend_used="azure"
        )

        # Respuesta binaria
        content_type = "audio/mpeg" if "mp3" in fmt else "audio/ogg"
        resp = HttpResponse(audio, content_type=content_type)
        # Sugerencia de descarga opcional:
        # resp['Content-Disposition'] = 'inline; filename="tts.mp3"'
        return resp

    except Exception as e:
        # Loguea fallback si lo deseas
        VoiceMetricEvent.objects.create(
            event_type="fallback_triggered",
            session_id=session_id,
            backend_used="azure",
            metadata={"stage": "tts", "error": str(e)}
        )
        return JsonResponse({"error": str(e)}, status=500)
