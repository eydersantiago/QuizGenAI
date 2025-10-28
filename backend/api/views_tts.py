# api/views_tts.py
import json
import os
import re
from django.http import JsonResponse, HttpResponse
from rest_framework.decorators import api_view
from rest_framework import status
from django.utils import timezone

from .services.azure_speech import issue_token, synthesize
from .models import VoiceMetricEvent  # para registrar métricas (event_type tts_complete)

# ---------- Utilidades de saneo SSML ----------

_TAG_RE = re.compile(r"<[^>]+>")
_THINK_RE = re.compile(r"</?think\b[^>]*>", re.IGNORECASE)

def _strip_disallowed_tags(s: str) -> str:
    """Quita específicamente <think>…</think> y cualquier otra etiqueta HTML/XML."""
    if not s:
        return ""
    s = _THINK_RE.sub("", s)
    s = _TAG_RE.sub("", s)
    return s

def _escape_xml(s: str) -> str:
    """Escapa caracteres para SSML/XML."""
    if not s:
        return ""
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&apos;"))

def _sanitize_tts_text(raw: str, limit: int = 5000) -> str:
    """Limpia etiquetas no permitidas y escapa; limita longitud segura para Azure."""
    clean = _strip_disallowed_tags(raw or "").strip()
    clean = _escape_xml(clean)
    # Azure recomienda <= ~5000 chars por request
    return clean[:limit]

# ---------- Vistas ----------

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
    return os.getenv("SPEECH_REGION", os.getenv("AZURE_SPEECH_REGION", "eastus2"))

def _guess_content_type(fmt: str) -> str:
    f = (fmt or "").lower()
    if "mp3" in f:
        return "audio/mpeg"
    if "wav" in f or "riff" in f or "pcm" in f:
        return "audio/wav"
    if "ogg" in f or "opus" in f:
        return "audio/ogg"
    # fallback razonable
    return "application/octet-stream"

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
        # 🔧 Arreglo clave: sanear texto (quita <think> y otras etiquetas; escapa XML)
        safe_text = _sanitize_tts_text(text)

        # Si después de sanear queda vacío, evita pedir TTS
        if not safe_text:
            return JsonResponse({"error": "text is empty after sanitization"}, status=400)

        # Llama al servicio que habla con Azure (mantienes tu lógica/caché dentro)
        audio, latency_ms = synthesize(text=safe_text, voice=voice, fmt=fmt)

        # Registra métrica TTS
        try:
            VoiceMetricEvent.objects.create(
                event_type="tts_complete",
                session_id=session_id,
                latency_ms=latency_ms,
                text_length=len(safe_text),
                backend_used="azure"
            )
        except Exception:
            # No bloquear la respuesta por fallos de métricas
            pass

        # Respuesta binaria con content-type correcto
        content_type = _guess_content_type(fmt)
        resp = HttpResponse(audio, content_type=content_type)
        # Sugerencia de descarga opcional:
        # ext = "mp3" if "mp3" in fmt.lower() else ("wav" if "wav" in fmt.lower() else "ogg")
        # resp['Content-Disposition'] = f'inline; filename="tts.{ext}"'
        return resp

    except Exception as e:
        # Loguea fallback/errores sin romper
        try:
            VoiceMetricEvent.objects.create(
                event_type="fallback_triggered",
                session_id=session_id,
                backend_used="azure",
                metadata={"stage": "tts", "error": str(e)}
            )
        except Exception:
            pass

        # Propaga mensaje legible al front
        return JsonResponse({"error": str(e)}, status=500)
