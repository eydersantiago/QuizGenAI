"""
Vistas para manejar la edición y confirmación de preguntas.

Este módulo contiene las vistas mejoradas que soportan:
- Creación de sesiones con preguntas editadas
- Validación robusta y sanitización
- Tracking completo de ediciones
- Regeneración en modo preview
- Seguridad contra ataques
"""

import logging
from django.http import JsonResponse
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework import status

from .models import GenerationSession, RegenerationLog
from .models_question_tracking import QuestionEditLog, QuestionOriginMetadata
from .serializers import (
    SessionWithEditedQuestionsSerializer,
    EditableQuestionSerializer,
    sanitize_question_data,
    validate_edited_questions_batch
)
from .views import (
    find_category_for_topic,
    _header_provider,
    _generate_with_fallback,
    _regenerate_with_fallback,
    build_seen_set,
    review_question,
    moderation_severity,
    _norm_for_cmp
)

logger = logging.getLogger(__name__)


@api_view(['POST'])
def create_session_with_edits(request):
    """
    POST /api/sessions/create-with-edits/

    Crea una sesión de quiz con soporte para preguntas editadas.

    Flujos soportados:
    1. Modo generación: Solo configuración → genera con IA
    2. Modo edición: Configuración + preguntas editadas → usa preguntas del usuario

    Body (modo generación):
    {
        "topic": "algoritmos",
        "difficulty": "Media",
        "types": ["mcq", "vf"],
        "counts": {"mcq": 5, "vf": 3}
    }

    Body (modo edición con preguntas):
    {
        "topic": "algoritmos",
        "difficulty": "Media",
        "types": ["mcq", "vf"],
        "counts": {"mcq": 5, "vf": 3},
        "questions": [
            {
                "type": "mcq",
                "question": "¿Cuál es la complejidad...?",
                "options": ["A) O(1)", "B) O(n)", "C) O(log n)", "D) O(n^2)"],
                "answer": "C",
                "explanation": "...",
                "isModified": true,
                "originalIndex": 0
            },
            ...
        ]
    }

    Seguridad implementada:
    - Validación exhaustiva con serializers
    - Sanitización de datos
    - Prevención de injection attacks
    - Rate limiting (configurar en settings)
    - Logging de operaciones sospechosas

    Returns:
        200: Sesión creada con éxito
        400: Datos inválidos
        500: Error del servidor
    """

    try:
        # Validar datos con serializer
        serializer = SessionWithEditedQuestionsSerializer(data=request.data)

        if not serializer.is_valid():
            logger.warning(
                f"Validación fallida en create_session_with_edits: {serializer.errors}",
                extra={'user_ip': request.META.get('REMOTE_ADDR')}
            )
            return JsonResponse({
                'error': 'Datos inválidos',
                'details': serializer.errors
            }, status=400)

        validated_data = serializer.validated_data

        # Extraer datos validados
        topic = validated_data['topic']
        difficulty = validated_data['difficulty']
        types = validated_data['types']
        counts = validated_data['counts']
        questions = validated_data.get('questions')  # Puede ser None

        # Validar categoría del tema
        category = find_category_for_topic(topic)
        if not category:
            return JsonResponse({
                'error': 'Tema fuera de dominio permitido'
            }, status=400)

        # Crear la sesión
        session = GenerationSession.objects.create(
            topic=topic,
            category=category,
            difficulty=difficulty,
            types=types,
            counts=counts,
            latest_preview=[]  # Se llenará después
        )

        logger.info(
            f"Sesión creada: {session.id} - Topic: {topic} - Difficulty: {difficulty}",
            extra={'session_id': str(session.id)}
        )

        # CASO 1: Preguntas editadas provistas (usuario confirmó después de editar)
        if questions:
            # Sanitizar y validar cada pregunta adicional
            sanitized_questions = []

            for i, q in enumerate(questions):
                # Sanitizar
                sanitized_q = sanitize_question_data(q)

                # Validar nuevamente (doble capa de seguridad)
                q_serializer = EditableQuestionSerializer(data=sanitized_q)
                if not q_serializer.is_valid():
                    logger.error(
                        f"Pregunta {i} no pasó validación secundaria",
                        extra={'session_id': str(session.id), 'errors': q_serializer.errors}
                    )
                    # Eliminar sesión creada (rollback manual)
                    session.delete()
                    return JsonResponse({
                        'error': f'Pregunta {i+1} tiene datos inválidos',
                        'details': q_serializer.errors
                    }, status=400)

                sanitized_questions.append(q_serializer.validated_data)

            # Guardar preguntas sanitizadas
            session.latest_preview = sanitized_questions
            session.save(update_fields=['latest_preview'])

            # TRACKING: Crear logs para cada pregunta
            _create_edit_tracking_logs(session, questions, sanitized_questions)

            logger.info(
                f"Sesión {session.id} creada con {len(sanitized_questions)} preguntas editadas",
                extra={'session_id': str(session.id)}
            )

            return JsonResponse({
                'session_id': str(session.id),
                'topic': topic,
                'difficulty': difficulty,
                'questions_count': len(sanitized_questions),
                'mode': 'edited'
            }, status=201)

        # CASO 2: Sin preguntas editadas → generar con IA
        else:
            preferred_provider = _header_provider(request)

            try:
                generated, provider_used, did_fallback, errors = _generate_with_fallback(
                    topic, difficulty, types, counts, preferred_provider
                )

                # Guardar preguntas generadas
                session.latest_preview = generated
                session.save(update_fields=['latest_preview'])

                # TRACKING: Marcar como generadas por IA pura
                for i, q in enumerate(generated):
                    QuestionOriginMetadata.objects.create(
                        session=session,
                        question_index=i,
                        origin_type='pure_ai',
                        initial_ai_provider=provider_used
                    )

                logger.info(
                    f"Sesión {session.id} creada con {len(generated)} preguntas de IA",
                    extra={
                        'session_id': str(session.id),
                        'provider': provider_used,
                        'fallback': did_fallback
                    }
                )

                return JsonResponse({
                    'session_id': str(session.id),
                    'topic': topic,
                    'difficulty': difficulty,
                    'questions_count': len(generated),
                    'mode': 'ai_generated',
                    'provider': provider_used
                }, status=201)

            except RuntimeError as e:
                error_msg = str(e)
                logger.error(
                    f"Error generando preguntas para sesión {session.id}: {error_msg}",
                    extra={'session_id': str(session.id)}
                )

                # Eliminar sesión (rollback)
                session.delete()

                if error_msg == "no_providers_available":
                    return JsonResponse({
                        'error': 'no_providers_available',
                        'message': 'No hay créditos disponibles en los proveedores configurados (Gemini/OpenAI)'
                    }, status=503)

                return JsonResponse({
                    'error': 'Error generando preguntas',
                    'message': error_msg
                }, status=500)

    except Exception as e:
        logger.exception(
            f"Error inesperado en create_session_with_edits: {str(e)}",
            extra={'user_ip': request.META.get('REMOTE_ADDR')}
        )
        return JsonResponse({
            'error': 'Error interno del servidor',
            'message': 'Ocurrió un error inesperado'
        }, status=500)


@api_view(['POST'])
def regenerate_in_preview_mode(request):
    """
    POST /api/regenerate-preview/

    Regenera una pregunta en modo preview (sin session_id requerido).

    Este endpoint permite regenerar preguntas antes de confirmar la sesión,
    útil para el flujo de edición en QuizPreviewEditor.

    Body:
    {
        "topic": "algoritmos",
        "difficulty": "Media",
        "type": "mcq",
        "base_question": {...},
        "avoid_phrases": ["pregunta 1", "pregunta 2"],
        "session_id": "uuid"  // Opcional, si existe
    }

    Returns:
        200: Pregunta regenerada
        400: Datos inválidos
        503: No hay proveedores disponibles
    """

    try:
        data = request.data

        # Validar campos requeridos
        required_fields = ['topic', 'difficulty', 'type']
        missing_fields = [f for f in required_fields if f not in data]

        if missing_fields:
            return JsonResponse({
                'error': 'Campos faltantes',
                'missing': missing_fields
            }, status=400)

        topic = data['topic']
        difficulty = data['difficulty']
        qtype = data['type']
        base_question = data.get('base_question')
        avoid_phrases = data.get('avoid_phrases', [])
        session_id = data.get('session_id')

        # Validar tipo
        if qtype not in ('mcq', 'vf', 'short'):
            return JsonResponse({
                'error': 'Tipo inválido',
                'message': 'El tipo debe ser mcq, vf o short'
            }, status=400)

        # Si hay session_id, usar para tracking
        session = None
        if session_id:
            try:
                session = GenerationSession.objects.get(id=session_id)
            except GenerationSession.DoesNotExist:
                logger.warning(f"Session {session_id} no encontrada para regeneración")

        # Construir seen set para evitar duplicados
        seen = set()
        if session:
            seen = build_seen_set(session)
        elif avoid_phrases:
            seen = {_norm_for_cmp(p) for p in avoid_phrases}

        # Obtener proveedor preferido
        preferred = _header_provider(request)

        # Regenerar con IA
        try:
            new_q, provider_used, did_fallback, errors = _regenerate_with_fallback(
                topic, difficulty, qtype, base_question, seen, preferred
            )

            # Validar pregunta generada
            issues = review_question(new_q)
            sev = moderation_severity(issues)

            # Si es severo, intentar una vez más
            if sev == "severe":
                logger.warning(
                    f"Pregunta regenerada tiene issues severos: {issues}",
                    extra={'topic': topic, 'type': qtype}
                )

                # Reintentar una vez
                seen.add(_norm_for_cmp(new_q.get("question", "")))
                new_q, provider_used, did_fallback, errors = _regenerate_with_fallback(
                    topic, difficulty, qtype, base_question, seen, preferred
                )

            # Si hay session_id, crear log de regeneración
            if session and base_question:
                index = data.get('index', -1)
                if index >= 0:
                    # Log de regeneración
                    RegenerationLog.objects.create(
                        session=session,
                        index=index,
                        old_question=base_question,
                        new_question=new_q
                    )

                    # Tracking de metadata
                    QuestionOriginMetadata.create_or_update_metadata(
                        session=session,
                        index=index,
                        operation_type='ai_regeneration',
                        ai_provider=provider_used
                    )

            logger.info(
                f"Pregunta regenerada en preview - Topic: {topic} - Provider: {provider_used}",
                extra={'session_id': session_id if session_id else 'preview'}
            )

            return JsonResponse({
                'question': new_q,
                'provider': provider_used,
                'fallback_used': did_fallback
            }, status=200)

        except RuntimeError as e:
            error_msg = str(e)

            if error_msg == "no_providers_available":
                return JsonResponse({
                    'error': 'no_providers_available',
                    'message': 'No hay créditos disponibles en los proveedores configurados (Gemini/OpenAI)'
                }, status=503)

            logger.error(f"Error regenerando en preview: {error_msg}")
            return JsonResponse({
                'error': 'Error regenerando pregunta',
                'message': error_msg
            }, status=500)

    except Exception as e:
        logger.exception(f"Error inesperado en regenerate_in_preview_mode: {str(e)}")
        return JsonResponse({
            'error': 'Error interno',
            'message': 'Ocurrió un error inesperado'
        }, status=500)


@api_view(['POST'])
def track_question_edit(request):
    """
    POST /api/track-edit/

    Registra una edición manual de pregunta para tracking.

    Este endpoint puede ser llamado por el frontend cuando el usuario
    edita una pregunta, para mantener un historial completo.

    Body:
    {
        "session_id": "uuid",
        "question_index": 0,
        "question_before": {...},
        "question_after": {...}
    }

    Returns:
        200: Edit logged exitosamente
        400: Datos inválidos
        404: Sesión no encontrada
    """

    try:
        data = request.data

        # Validar campos
        required = ['session_id', 'question_index', 'question_after']
        missing = [f for f in required if f not in data]

        if missing:
            return JsonResponse({
                'error': 'Campos faltantes',
                'missing': missing
            }, status=400)

        session_id = data['session_id']
        index = int(data['question_index'])
        before = data.get('question_before')
        after = data['question_after']

        # Obtener sesión
        try:
            session = GenerationSession.objects.get(id=session_id)
        except GenerationSession.DoesNotExist:
            return JsonResponse({
                'error': 'Sesión no encontrada'
            }, status=404)

        # Validar y sanitizar pregunta después
        sanitized_after = sanitize_question_data(after)
        serializer = EditableQuestionSerializer(data=sanitized_after)

        if not serializer.is_valid():
            return JsonResponse({
                'error': 'Pregunta inválida',
                'details': serializer.errors
            }, status=400)

        # Crear log
        QuestionEditLog.log_manual_edit(
            session=session,
            index=index,
            before=before,
            after=sanitized_after
        )

        # Actualizar metadata
        QuestionOriginMetadata.create_or_update_metadata(
            session=session,
            index=index,
            operation_type='manual_edit'
        )

        logger.info(
            f"Edit logged para sesión {session_id}, pregunta {index}",
            extra={'session_id': str(session_id), 'index': index}
        )

        return JsonResponse({
            'success': True,
            'message': 'Edición registrada correctamente'
        }, status=200)

    except Exception as e:
        logger.exception(f"Error en track_question_edit: {str(e)}")
        return JsonResponse({
            'error': 'Error interno',
            'message': str(e)
        }, status=500)


@api_view(['GET'])
def get_question_history(request, session_id, question_index):
    """
    GET /api/sessions/<session_id>/questions/<question_index>/history/

    Obtiene el historial completo de ediciones de una pregunta.

    Útil para mostrar al usuario qué cambios ha hecho, en qué orden,
    y permitir deshacer o ver versiones anteriores.

    Returns:
        200: Historial de ediciones
        404: Sesión o pregunta no encontrada
    """

    try:
        # Obtener sesión
        try:
            session = GenerationSession.objects.get(id=session_id)
        except GenerationSession.DoesNotExist:
            return JsonResponse({
                'error': 'Sesión no encontrada'
            }, status=404)

        # Obtener logs
        logs = QuestionEditLog.objects.filter(
            session=session,
            question_index=question_index
        ).order_by('created_at')

        # Obtener metadata
        try:
            metadata = QuestionOriginMetadata.objects.get(
                session=session,
                question_index=question_index
            )
            metadata_summary = metadata.get_summary()
        except QuestionOriginMetadata.DoesNotExist:
            metadata_summary = None

        # Serializar logs
        history = []
        for log in logs:
            history.append({
                'id': str(log.id),
                'operation_type': log.operation_type,
                'question_before': log.question_before,
                'question_after': log.question_after,
                'changed_fields': log.changed_fields,
                'ai_provider': log.ai_provider,
                'created_at': log.created_at.isoformat(),
                'summary': log.get_edit_summary()
            })

        return JsonResponse({
            'session_id': str(session_id),
            'question_index': question_index,
            'history': history,
            'metadata': metadata_summary
        }, status=200)

    except Exception as e:
        logger.exception(f"Error en get_question_history: {str(e)}")
        return JsonResponse({
            'error': 'Error interno',
            'message': str(e)
        }, status=500)


# ==============================================================================
# FUNCIONES AUXILIARES PRIVADAS
# ==============================================================================

def _create_edit_tracking_logs(session, original_questions, sanitized_questions):
    """
    Crea logs de tracking para preguntas editadas.

    Args:
        session: GenerationSession instance
        original_questions: Lista con preguntas originales (con metadata de frontend)
        sanitized_questions: Lista con preguntas sanitizadas

    Esta función analiza las preguntas y crea los logs apropiados según:
    - isNew: log de 'creation'
    - isModified: log de 'manual_edit'
    - ni isNew ni isModified: log de 'pure_ai' (si aplica)
    """

    for i, (original, sanitized) in enumerate(zip(original_questions, sanitized_questions)):
        is_new = original.get('isNew', False)
        is_modified = original.get('isModified', False)
        original_index = original.get('originalIndex', -1)

        if is_new:
            # Pregunta nueva (creada o duplicada)
            QuestionEditLog.log_creation(
                session=session,
                index=i,
                question_data=sanitized
            )

            QuestionOriginMetadata.objects.create(
                session=session,
                question_index=i,
                origin_type='user_created' if original_index == -1 else 'duplicated',
                edit_count=0,
                regeneration_count=0
            )

        elif is_modified:
            # Pregunta editada
            # Intentar obtener el before (no siempre disponible)
            before = None
            if original_index >= 0 and hasattr(session, 'latest_preview'):
                if session.latest_preview and original_index < len(session.latest_preview):
                    before = session.latest_preview[original_index]

            QuestionEditLog.log_manual_edit(
                session=session,
                index=i,
                before=before,
                after=sanitized
            )

            QuestionOriginMetadata.create_or_update_metadata(
                session=session,
                index=i,
                operation_type='manual_edit'
            )

        else:
            # Pregunta no modificada (IA pura)
            QuestionOriginMetadata.objects.create(
                session=session,
                question_index=i,
                origin_type='pure_ai',
                edit_count=0,
                regeneration_count=0,
                initial_ai_provider='gemini'  # o detectar del header
            )
