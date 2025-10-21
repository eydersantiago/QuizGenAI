# api/voice_metrics_views.py
import logging
from django.http import JsonResponse, HttpResponse
from rest_framework.decorators import api_view
from rest_framework import status

from .services.voice_metrics import compute_voice_metrics, build_voice_metrics_csv
from .models import VoiceMetricEvent

logger = logging.getLogger(__name__)


@api_view(['POST'])
def log_voice_event(request):
    """
    POST /api/voice-metrics/log/
    Registra un evento individual de métricas de voz (STT/TTS).

    Body esperado (JSON):
    {
        "event_type": "stt_final",          // requerido
        "session_id": "uuid-string",        // opcional
        "latency_ms": 150,                  // opcional
        "confidence": 0.95,                 // opcional (0-1)
        "intent": "generate_quiz",          // opcional
        "backend_used": "grammar",          // opcional
        "text_length": 45,                  // opcional
        "metadata": {...}                   // opcional
    }

    Returns:
        JsonResponse con status 201 y {'status': 'logged', 'event_id': <id>}
        o error 400 si falta event_type o hay errores de validación
    """
    try:
        data = request.data

        # Validar que event_type esté presente
        event_type = data.get('event_type')
        if not event_type:
            return JsonResponse(
                {'error': 'event_type is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Extraer campos opcionales
        session_id = data.get('session_id')
        latency_ms = data.get('latency_ms')
        confidence = data.get('confidence')
        intent = data.get('intent')
        backend_used = data.get('backend_used')
        text_length = data.get('text_length')
        metadata = data.get('metadata', {})

        # Validar que metadata sea un dict
        if not isinstance(metadata, dict):
            metadata = {}

        # Crear el evento
        event = VoiceMetricEvent.objects.create(
            event_type=event_type,
            session_id=session_id,
            user=request.user if request.user.is_authenticated else None,
            latency_ms=latency_ms,
            confidence=confidence,
            intent=intent,
            backend_used=backend_used,
            text_length=text_length,
            metadata=metadata
        )

        logger.info(
            f"Voice metric event logged: {event_type} (id={event.id}, "
            f"session={session_id}, user={request.user.id if request.user.is_authenticated else 'anonymous'})"
        )

        return JsonResponse(
            {
                'status': 'logged',
                'event_id': event.id
            },
            status=status.HTTP_201_CREATED
        )

    except ValueError as e:
        logger.warning(f"Validation error in log_voice_event: {str(e)}")
        return JsonResponse(
            {'error': f'Validation error: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    except Exception as e:
        logger.error(f"Error logging voice event: {str(e)}", exc_info=True)
        return JsonResponse(
            {'error': 'Failed to log voice event'},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['GET'])
def voice_metrics_summary(request):
    """
    GET /api/voice-metrics/summary/?start=YYYY-MM-DD&end=YYYY-MM-DD
    Devuelve métricas agregadas de eventos de voz.

    Query params:
        - start: Fecha de inicio (opcional, formato YYYY-MM-DD)
        - end: Fecha de fin (opcional, formato YYYY-MM-DD)

    Returns:
        JsonResponse con métricas calculadas:
        {
            "stt_latency_p50_ms": 145.5,
            "stt_latency_p95_ms": 320.8,
            "tts_latency_p50_ms": 89.2,
            "tts_latency_p95_ms": 210.5,
            "total_intents": 1250,
            "intent_avg_confidence": 0.87,
            "intent_accuracy_rate": 0.82,
            "fallback_count": 45,
            "fallback_rate": 0.036,
            "barge_in_count": 23,
            "suggestions_shown": 340,
            "suggestions_accepted": 210,
            "suggestion_accept_rate": 0.618,
            "backend_distribution": {...},
            "filters": {...}
        }
    """
    try:
        start = request.GET.get('start')
        end = request.GET.get('end')

        metrics = compute_voice_metrics(start=start, end=end)

        logger.info(f"Voice metrics summary requested (start={start}, end={end})")

        return JsonResponse(metrics, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error computing voice metrics: {str(e)}", exc_info=True)
        return JsonResponse(
            {'error': 'Failed to compute voice metrics'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def voice_metrics_export(request):
    """
    GET /api/voice-metrics/export/?start=YYYY-MM-DD&end=YYYY-MM-DD
    Exporta métricas de voz en formato CSV.

    Query params:
        - start: Fecha de inicio (opcional, formato YYYY-MM-DD)
        - end: Fecha de fin (opcional, formato YYYY-MM-DD)

    Returns:
        HttpResponse con archivo CSV descargable
        Content-Type: text/csv; charset=utf-8
        Filename: voice_metrics.csv
    """
    try:
        start = request.GET.get('start')
        end = request.GET.get('end')

        # Calcular métricas
        metrics = compute_voice_metrics(start=start, end=end)

        # Convertir a CSV
        csv_text = build_voice_metrics_csv(metrics)

        logger.info(f"Voice metrics CSV export requested (start={start}, end={end})")

        # Crear respuesta HTTP con CSV
        resp = HttpResponse(csv_text, content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = 'attachment; filename="voice_metrics.csv"'

        return resp

    except Exception as e:
        logger.error(f"Error exporting voice metrics: {str(e)}", exc_info=True)
        return JsonResponse(
            {'error': 'Failed to export voice metrics'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
