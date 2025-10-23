# api/views_stt.py
import base64
from typing import Optional
from django.http import JsonResponse
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework import status
from io import BytesIO
from pydub.utils import which
from pydub import AudioSegment
import platform          # 👈 FALTA
import shutil            # 👈 si usas shutil.which
import soundfile as sf   # opcional para mediciones
import logging
import os

from .services.azure_stt import recognize_short_audio
from .models import VoiceMetricEvent  # usa tu modelo de métricas

logger = logging.getLogger(__name__)

def _configure_ffmpeg():
    """
    Intenta fijar la ruta de ffmpeg/ffprobe de forma portable:
      1) Usa variables de entorno si existen (FFMPEG_PATH, FFPROBE_PATH).
      2) En Azure Linux: /home/site/wwwroot/backend/bin/ffmpeg  (vía App Setting FFMPEG_PATH).
         - Asegúrate de tener también LD_LIBRARY_PATH=/home/site/wwwroot/backend/bin/lib
      3) En Windows dev: usa backend\\bin\\ffmpeg.exe si existe, o el ffmpeg del PATH.
      4) Si no se encuentra, pydub intentará lo que haya en PATH; si no hay, conversiones fallarán.
    """
    # 1) Si el host ya tiene PATH, úsalo
    found_ffmpeg = which("ffmpeg")
    found_ffprobe = which("ffprobe")

    # 2) Overrides por variables de entorno (útil en Azure)
    ffmpeg_env = os.getenv("FFMPEG_PATH")
    ffprobe_env = os.getenv("FFPROBE_PATH")

    # 3) Fallback Windows
    if not ffmpeg_env and platform.system().lower().startswith("win"):
        default = r"C:\ffmpeg\bin\ffmpeg.exe"
        if os.path.isfile(default):
            ffmpeg_env = default
    if not ffprobe_env and platform.system().lower().startswith("win"):
        default = r"C:\ffmpeg\bin\ffprobe.exe"
        if os.path.isfile(default):
            ffprobe_env = default

    # 4) Aplica
    if ffmpeg_env:
        AudioSegment.converter = ffmpeg_env
    elif found_ffmpeg:
        AudioSegment.converter = found_ffmpeg

    # pydub usa ffprobe para leer metadatos
    if ffprobe_env:
        AudioSegment.ffprobe = ffprobe_env
    elif found_ffprobe:
        AudioSegment.ffprobe = found_ffprobe

    logger.info(f"[FFMPEG] ffmpeg={getattr(AudioSegment, 'converter', None)} | ffprobe={getattr(AudioSegment, 'ffprobe', None)}")

_configure_ffmpeg()
# =========================
# FIN CONFIG FFMPEG
# =========================

def _to_wav_mono16k(file_bytes: bytes, src_fmt: str) -> bytes:
    """
    Convierte cualquier (webm/ogg/mp3/wav) a WAV PCM mono 16k.
    Requiere ffmpeg instalado en el host.
    """
    buf = BytesIO(file_bytes)
    # pydub autodetecta con ffmpeg
    audio = AudioSegment.from_file(buf, format=src_fmt)
    audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)  # 16-bit PCM
    out = BytesIO()
    audio.export(out, format="wav")
    return out.getvalue()

def _rough_duration_ms(wav_bytes: bytes) -> int:
    try:
        data, sr = sf.read(BytesIO(wav_bytes))
        return int(len(data) * 1000 / sr)
    except Exception:
        return 0

def _pick_src_fmt(upload_ct: Optional[str], fmt_hint: Optional[str]) -> str:
    """
    Deducción defensiva del formato de ENTRADA para pydub/ffmpeg.
    """
    ct = (upload_ct or "").lower()
    hint = (fmt_hint or "").lower()

    if "webm" in ct or hint == "webm":
        return "webm"
    if "ogg" in ct or "opus" in ct or hint in ("ogg", "opus"):
        return "ogg"
    if "mpeg" in ct or "mp3" in ct or hint == "mp3":
        return "mp3"
    if "wav" in ct or hint == "wav":
        return "wav"
    # por defecto intentamos wav
    return "wav"

def _wav_content_type() -> str:
    # Content-Type que Azure acepta sin drama para audio PCM 16k mono
    return "audio/wav; codecs=audio/pcm; samplerate=16000"

@api_view(["POST"])
@parser_classes([MultiPartParser, JSONParser])
def stt_recognize(request):
    """
    POST /api/voice/stt/
    Enviar:
      - multipart/form-data con campo 'audio' (archivo .wav/.ogg/.webm/.mp3)
        y opcional 'language' (ej: es-ES, es-MX, es-CO), 'format' (simple|detailed), 'session_id', 'fmt'
      - ó JSON: { "audio_base64": "...", "content_type": "...", "language": "es-ES", "session_id": "..." }

    Respuesta: { text, confidence?, raw, latency_ms }
    """
    try:
        language = request.data.get("language") or "es-ES"
        result_format = request.data.get("format") or "detailed"
        session_id = request.data.get("session_id")
        fmt_hint = request.data.get("fmt")

        # ===== 1) Obtener bytes + content-type reportado =====
        audio_bytes: Optional[bytes] = None
        upload_ct: Optional[str] = None

        if hasattr(request, "FILES") and "audio" in request.FILES:
            f = request.FILES["audio"]
            audio_bytes = f.read()
            upload_ct = f.content_type
        elif "audio_base64" in request.data:
            b64 = request.data["audio_base64"]
            audio_bytes = base64.b64decode(b64.split(",")[-1].encode("utf-8"))
            upload_ct = request.data.get("content_type")

        if not audio_bytes:
            return JsonResponse({"error": "audio is required (file or base64)"}, status=status.HTTP_400_BAD_REQUEST)

        # ===== 2) Convertir SIEMPRE a WAV PCM mono 16k (robustez) =====
        src_fmt = _pick_src_fmt(upload_ct, fmt_hint)
        wav_bytes: bytes
        converted = False
        try:
            wav_bytes = _to_wav_mono16k(audio_bytes, src_fmt)
            converted = True
        except Exception as conv_err:
            # Si no pudimos convertir (ffmpeg ausente o formato raro), enviamos lo original.
            logger.warning(f"[STT] Conversion to WAV failed ({src_fmt}): {conv_err}. Sending original bytes.")
            wav_bytes = audio_bytes  # fallback
            src_fmt = src_fmt or "unknown"

        duration_ms = _rough_duration_ms(wav_bytes) if converted or src_fmt == "wav" else 0

        # Para Azure forzamos WAV si conversion OK; si no, dejamos el CT original (puede fallar).
        if converted:
            content_type = _wav_content_type()
            send_bytes = wav_bytes
            out_fmt = "wav16k"
        else:
            # Enviar lo recibido; último recurso
            content_type = (upload_ct or "audio/wav")
            send_bytes = audio_bytes
            out_fmt = src_fmt

        logger.info(
            f"[STT] ingest: received={len(audio_bytes)}B ct='{upload_ct}' "
            f"src_fmt={src_fmt} -> out_fmt={out_fmt} send={len(send_bytes)}B dur≈{duration_ms}ms"
        )

        # ===== 3) Llamar a Azure =====
        text, raw, latency_ms, confidence = recognize_short_audio(
            audio_bytes=send_bytes,
            content_type=content_type,
            language=language,
            result_format=result_format,
        )

        # Enriquecer raw con datos de ingest para depurar en el frontend
        raw_extra = {
            "ingest": {
                "received_bytes": len(audio_bytes),
                "upload_content_type": upload_ct,
                "src_fmt": src_fmt,
                "out_fmt": out_fmt,
                "sent_bytes": len(send_bytes),
                "duration_ms": duration_ms,
            }
        }
        if isinstance(raw, dict):
            raw.update(raw_extra)
        else:
            raw = raw_extra  # al menos devolvemos ingest

        # ===== 4) Métrica =====
        try:
            VoiceMetricEvent.objects.create(
                event_type="stt_complete",
                session_id=session_id,
                latency_ms=latency_ms,
                text_length=len(text or ""),
                backend_used="azure",
                metadata={
                    "language": language,
                    "confidence": confidence,
                    "format": result_format,
                    "src_fmt": src_fmt,
                    "out_fmt": out_fmt,
                    "duration_ms": duration_ms,
                },
            )
        except Exception as m_err:
            logger.warning(f"[STT] metric save failed: {m_err}")

        # ===== 5) Respuesta =====
        return JsonResponse(
            {
                "text": text or "",
                "confidence": confidence,
                "raw": raw,            # útil para depurar (puedes retirarlo en prod)
                "latency_ms": latency_ms,
            },
            status=200,
        )

    except Exception as e:
        try:
            VoiceMetricEvent.objects.create(
                event_type="stt_error",
                backend_used="azure",
                metadata={"error": str(e)},
            )
        except Exception:
            pass
        logger.exception(f"[STT] error: {e}")
        return JsonResponse({"error": str(e)}, status=500)
