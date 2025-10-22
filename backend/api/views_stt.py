# api/views_stt.py
import base64
from typing import Optional
from django.http import JsonResponse
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework import status

from .services.azure_stt import recognize_short_audio
from .models import VoiceMetricEvent  # usa tu modelo de métricas

def _pick_content_type(upload_ct: Optional[str], fmt_hint: Optional[str]) -> str:
    """
    Intenta deducir Content-Type correcto para Azure a partir del archivo subido
    o de un hint 'wav'/'ogg'.
    """
    if upload_ct:
        # Normaliza tipos comunes
        if upload_ct.startswith("audio/wav") or upload_ct == "audio/x-wav":
            return "audio/wav; codecs=audio/pcm; samplerate=16000"
        if upload_ct.startswith("audio/ogg"):
            return "audio/ogg; codecs=opus"
        if upload_ct.startswith("audio/mpeg"):
            # Azure no acepta mp3 para STT en REST short-form; mejor convertir en el cliente
            # Si llega mp3, lo intentamos como 'audio/mpeg' (puede fallar)
            return "audio/mpeg"
        return upload_ct

    if fmt_hint == "ogg":
        return "audio/ogg; codecs=opus"
    # por defecto WAV PCM 16kHz
    return "audio/wav; codecs=audio/pcm; samplerate=16000"

@api_view(["POST"])
@parser_classes([MultiPartParser, JSONParser])
def stt_recognize(request):
    """
    POST /api/voice/stt/
    Enviar:
      - multipart/form-data con campo 'audio' (archivo .wav/.ogg)
        y opcional 'language' (ej: es-ES, es-MX, es-CO), 'format' (simple|detailed), 'session_id'
      - ó JSON: { "audio_base64": "...", "content_type": "...", "language": "es-ES", "session_id": "..." }

    Respuesta: { text, confidence?, raw, latency_ms }
    """
    try:
        language = request.data.get("language") or "es-ES"
        result_format = request.data.get("format") or "detailed"
        session_id = request.data.get("session_id")

        audio_bytes: Optional[bytes] = None
        content_type: Optional[str] = None

        # 1) multipart con archivo
        if hasattr(request, "FILES") and "audio" in request.FILES:
            f = request.FILES["audio"]
            audio_bytes = f.read()
            content_type = _pick_content_type(f.content_type, request.data.get("fmt"))
        # 2) JSON base64
        elif "audio_base64" in request.data:
            b64 = request.data["audio_base64"]
            audio_bytes = base64.b64decode(b64.split(",")[-1].encode("utf-8"))
            content_type = _pick_content_type(request.data.get("content_type"), request.data.get("fmt"))

        if not audio_bytes:
            return JsonResponse({"error": "audio is required (file or base64)"}, status=status.HTTP_400_BAD_REQUEST)

        text, raw, latency_ms, confidence = recognize_short_audio(
            audio_bytes=audio_bytes,
            content_type=content_type,
            language=language,
            result_format=result_format,
        )

        # Registra métrica
        VoiceMetricEvent.objects.create(
            event_type="stt_complete",
            session_id=session_id,
            latency_ms=latency_ms,
            text_length=len(text or ""),
            backend_used="azure",
            metadata={"language": language, "confidence": confidence, "format": result_format},
        )

        return JsonResponse(
            {
                "text": text,
                "confidence": confidence,
                "raw": raw,            # útil para depurar (puedes retirarlo en prod)
                "latency_ms": latency_ms,
            },
            status=200,
        )

    except Exception as e:
        VoiceMetricEvent.objects.create(
            event_type="stt_error",
            backend_used="azure",
            metadata={"error": str(e)},
        )
        return JsonResponse({"error": str(e)}, status=500)
