# api/suggestion_views.py
"""
Endpoints para el sistema de sugerencias proactivas de QuizGenAI.

Proporciona endpoints para obtener sugerencias basadas en el contexto del usuario
y registrar feedback sobre las sugerencias mostradas.
"""

import logging
from typing import Optional, Dict, Any
from django.http import JsonResponse
from django.core.cache import cache
from rest_framework.decorators import api_view
from rest_framework import status

from .services.suggestion_engine import SuggestionEngine
from .models import VoiceMetricEvent

# Configurar logger
logger = logging.getLogger(__name__)

# Instancia global del motor de sugerencias
# Se inicializa una sola vez para reutilizar las conexiones de LLM
suggestion_engine = SuggestionEngine(
    idle_threshold=15,
    error_threshold=2,
    use_llm_fallback=True
)

logger.info("SuggestionEngine inicializado correctamente")


def _safe_log_metric(event_type: str, session_id: Optional[str] = None,
                     user=None, metadata: Optional[Dict[str, Any]] = None) -> bool:
    """
    Registra una métrica de forma segura sin romper el flujo principal.

    Args:
        event_type: Tipo de evento a registrar
        session_id: ID de sesión (opcional)
        user: Usuario Django (opcional)
        metadata: Metadatos adicionales (opcional)

    Returns:
        True si se registró exitosamente, False si falló
    """
    try:
        VoiceMetricEvent.objects.create(
            event_type=event_type,
            session_id=session_id,
            user=user if (user and user.is_authenticated) else None,
            metadata=metadata or {},
            backend_used=metadata.get('source') if metadata else None,
            text_length=len(metadata.get('suggestion_text', '')) if metadata and 'suggestion_text' in metadata else None
        )
        return True
    except Exception as e:
        logger.error(f"Error registrando métrica {event_type}: {e}")
        return False


@api_view(['POST'])
def get_next_suggestion(request):
    """
    POST /api/suggestions/next/

    Genera la siguiente sugerencia proactiva basada en el contexto del usuario.

    Request body:
        {
            "context": {
                "idleSeconds": int,
                "consecutiveErrors": int,
                "quizTopic": str,
                "progress": {
                    "answered": int,
                    "total": int,
                    "percentage": float
                },
                "lastAction": str | null,
                "lastActionTime": int,
                "isIdle": bool
            },
            "session_id": str (opcional)
        }

    Response (200):
        {
            "suggestion": {
                "suggestion_text": str,
                "action_type": str,
                "action_params": dict,
                "priority": str,
                "reasoning": str,
                "source": str
            }
        }

    Response (200 - no suggestion):
        {
            "suggestion": null,
            "message": "No suggestion needed"
        }

    Response (400):
        {
            "error": "context is required"
        }

    Response (500):
        {
            "error": "Internal server error",
            "detail": str (solo en desarrollo)
        }
    """
    try:
        # Validar que context esté presente
        context = request.data.get('context')
        if not context or not isinstance(context, dict):
            logger.warning("Request sin contexto válido")
            return JsonResponse(
                {'error': 'context is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Obtener session_id del request
        session_id = request.data.get('session_id')

        # Obtener user_id desde request.user o usar session_id como fallback
        user_id = None
        user = None

        if request.user and request.user.is_authenticated:
            user_id = str(request.user.id)
            user = request.user
            logger.debug(f"Usuario autenticado: {user_id}")
        elif session_id:
            user_id = session_id
            logger.debug(f"Usando session_id como user_id: {user_id}")
        else:
            # Si no hay ni usuario ni session_id, generar sugerencia sin rate limiting
            logger.debug("Request sin user_id ni session_id")

        # Log del contexto recibido
        logger.info(
            f"Generando sugerencia - User: {user_id}, "
            f"Idle: {context.get('idleSeconds', 0)}s, "
            f"Errors: {context.get('consecutiveErrors', 0)}, "
            f"Progress: {context.get('progress', {}).get('percentage', 0):.0f}%"
        )

        # Generar sugerencia usando el motor
        suggestion = suggestion_engine.generate_suggestion(
            context=context,
            user_id=user_id
        )

        # Si hay sugerencia, registrar métrica y retornar
        if suggestion:
            logger.info(
                f"Sugerencia generada - Source: {suggestion['source']}, "
                f"Action: {suggestion['action_type']}, "
                f"Priority: {suggestion['priority']}"
            )

            # Registrar métrica de sugerencia mostrada
            _safe_log_metric(
                event_type='suggestion_shown',
                session_id=session_id,
                user=user,
                metadata={
                    'suggestion_text': suggestion['suggestion_text'],
                    'action_type': suggestion['action_type'],
                    'action_params': suggestion['action_params'],
                    'priority': suggestion['priority'],
                    'reasoning': suggestion['reasoning'],
                    'source': suggestion['source'],
                    'context_summary': {
                        'idle_seconds': context.get('idleSeconds', 0),
                        'consecutive_errors': context.get('consecutiveErrors', 0),
                        'progress_percentage': context.get('progress', {}).get('percentage', 0),
                        'quiz_topic': context.get('quizTopic', ''),
                    }
                }
            )

            return JsonResponse(
                {'suggestion': suggestion},
                status=status.HTTP_200_OK
            )

        # No hay sugerencia necesaria
        logger.debug("No se generó sugerencia para el contexto actual")
        return JsonResponse(
            {
                'suggestion': None,
                'message': 'No suggestion needed'
            },
            status=status.HTTP_200_OK
        )

    except Exception as e:
        # Log del error completo
        logger.error(f"Error generando sugerencia: {e}", exc_info=True)

        # Respuesta de error
        error_response = {'error': 'Internal server error'}

        # En desarrollo, incluir detalles del error
        if hasattr(request, 'META') and request.META.get('DEBUG') == 'True':
            error_response['detail'] = str(e)

        return JsonResponse(
            error_response,
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def suggestion_feedback(request):
    """
    POST /api/suggestions/feedback/

    Registra feedback del usuario sobre una sugerencia mostrada.

    Request body:
        {
            "action": "accepted" | "dismissed",
            "suggestion_text": str,
            "session_id": str (opcional),
            "action_type": str (opcional),
            "priority": str (opcional),
            "source": str (opcional),
            "user_action": str (opcional) - acción que tomó el usuario tras aceptar
        }

    Response (200):
        {
            "status": "logged",
            "message": "Feedback registered successfully"
        }

    Response (400):
        {
            "error": "Invalid action. Must be 'accepted' or 'dismissed'"
        }

    Response (500):
        {
            "error": "Internal server error",
            "detail": str (solo en desarrollo)
        }
    """
    try:
        # Obtener y validar action
        action = request.data.get('action', '').strip().lower()

        if action not in ['accepted', 'dismissed']:
            logger.warning(f"Action inválida recibida: {action}")
            return JsonResponse(
                {'error': "Invalid action. Must be 'accepted' or 'dismissed'"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Obtener datos adicionales
        suggestion_text = request.data.get('suggestion_text', '')
        session_id = request.data.get('session_id')
        action_type = request.data.get('action_type', '')
        priority = request.data.get('priority', '')
        source = request.data.get('source', '')
        user_action = request.data.get('user_action', '')

        # Determinar usuario
        user = None
        if request.user and request.user.is_authenticated:
            user = request.user

        # Construir event_type según la acción
        event_type = f"suggestion_{action}"

        logger.info(
            f"Feedback de sugerencia - Action: {action}, "
            f"Source: {source}, User: {user.id if user else 'anon'}"
        )

        # Construir metadata
        metadata = {
            'suggestion_text': suggestion_text,
            'action': action,
            'action_type': action_type,
            'priority': priority,
            'source': source,
        }

        # Si fue aceptada, incluir qué hizo el usuario
        if action == 'accepted' and user_action:
            metadata['user_action'] = user_action

        # Registrar métrica
        metric_logged = _safe_log_metric(
            event_type=event_type,
            session_id=session_id,
            user=user,
            metadata=metadata
        )

        if metric_logged:
            logger.debug(f"Métrica {event_type} registrada correctamente")
        else:
            logger.warning(f"No se pudo registrar métrica {event_type}, pero continuando")

        return JsonResponse(
            {
                'status': 'logged',
                'message': 'Feedback registered successfully'
            },
            status=status.HTTP_200_OK
        )

    except Exception as e:
        # Log del error completo
        logger.error(f"Error registrando feedback: {e}", exc_info=True)

        # Respuesta de error
        error_response = {'error': 'Internal server error'}

        # En desarrollo, incluir detalles del error
        if hasattr(request, 'META') and request.META.get('DEBUG') == 'True':
            error_response['detail'] = str(e)

        return JsonResponse(
            error_response,
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
