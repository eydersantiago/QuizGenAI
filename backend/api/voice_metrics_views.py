# api/voice_metrics_views.py
import logging
import uuid
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

        # Validar que session_id sea un UUID válido si está presente
        if session_id is not None:
            try:
                # Intentar convertir a UUID para validar el formato
                uuid.UUID(str(session_id))
            except (ValueError, AttributeError):
                return JsonResponse(
                    {'error': f'session_id must be a valid UUID, got: {session_id}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

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


# api/voice_metrics_views.py (al final del archivo)

@api_view(['GET'])
def voice_metrics_events(request):
    """
    GET /api/voice-metrics/events/
    Lista eventos crudos con filtros y paginación.

    Query params opcionales:
      - start=YYYY-MM-DD
      - end=YYYY-MM-DD
      - event_type=stt_complete|stt_final|tts_complete|intent_recognized|...
      - backend=azure|piper|...
      - session_id=<uuid>
      - limit=50 (por defecto)
      - offset=0 (por defecto)

    Respuesta:
    {
      "count": <total>,
      "next_offset": <offset siguiente o null>,
      "results": [
        {
          "id": 123,
          "timestamp": "2025-10-22T12:34:56.123Z",
          "event_type": "stt_complete",
          "session_id": "...",
          "latency_ms": 123,
          "confidence": 0.92,
          "intent": "generate_quiz",
          "backend_used": "azure",
          "text_length": 45,
          "metadata": {...},
          "user_id": 7
        },
        ...
      ]
    }
    """
    try:
        start = request.GET.get('start')
        end = request.GET.get('end')
        event_type = request.GET.get('event_type')
        backend = request.GET.get('backend')
        session_id = request.GET.get('session_id')

        try:
            limit = int(request.GET.get('limit', 50))
            limit = max(1, min(limit, 500))
        except ValueError:
            limit = 50

        try:
            offset = int(request.GET.get('offset', 0))
            offset = max(0, offset)
        except ValueError:
            offset = 0

        qs = VoiceMetricEvent.objects.all()

        # Filtros de fecha
        start_dt = None
        end_dt = None
        if start:
            start_dt = start[:10]
            qs = qs.filter(timestamp__gte=start_dt)
        if end:
            from datetime import datetime, timedelta
            end_dt = end[:10]
            try:
                _end = datetime.strptime(end_dt, "%Y-%m-%d") + timedelta(days=1)
                qs = qs.filter(timestamp__lt=_end)
            except Exception:
                pass

        # Otros filtros
        if event_type:
            qs = qs.filter(event_type=event_type)
        if backend:
            qs = qs.filter(backend_used=backend)
        if session_id:
            qs = qs.filter(session_id=session_id)

        total = qs.count()
        qs = qs.order_by('-timestamp')[offset:offset + limit]

        def serialize(ev: VoiceMetricEvent):
            return {
                "id": ev.id,
                "timestamp": ev.timestamp.isoformat(),
                "event_type": ev.event_type,
                "session_id": str(ev.session_id) if ev.session_id else None,
                "latency_ms": ev.latency_ms,
                "confidence": ev.confidence,
                "intent": ev.intent,
                "backend_used": ev.backend_used,
                "text_length": ev.text_length,
                "metadata": ev.metadata or {},
                "user_id": ev.user.id if ev.user_id else None,
            }

        results = [serialize(ev) for ev in qs]
        next_offset = offset + limit if (offset + limit) < total else None

        return JsonResponse({
            "count": total,
            "next_offset": next_offset,
            "results": results
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error listing voice events: {str(e)}", exc_info=True)
        return JsonResponse({'error': 'Failed to list events'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
