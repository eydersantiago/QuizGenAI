# api/views_saved_quizzes.py
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework import status
from django.utils import timezone
from django.db.models import Q, Count, Avg
from django.db import transaction

from .models import SavedQuiz, GenerationSession
from .serializers import (
    SavedQuizSerializer,
    SavedQuizListSerializer,
    SaveQuizRequestSerializer,
    UpdateQuizProgressSerializer
)
from .views import (
    regenerate_question_with_gemini,
    regenerate_question_with_pplx,
    _regenerate_with_fallback,
    _header_provider,
    _norm_for_cmp
)
from .views import generate_cover_image


@api_view(['GET', 'POST'])
def saved_quizzes(request):
    """
    GET: Lista todos los cuestionarios guardados
    POST: Crea un nuevo cuestionario guardado
    """
    if request.method == 'GET':
        # Filtros opcionales
        topic = request.GET.get('topic')
        difficulty = request.GET.get('difficulty')
        completed = request.GET.get('completed')
        
        queryset = SavedQuiz.objects.all()
        
        if topic:
            queryset = queryset.filter(topic__icontains=topic)
        if difficulty:
            queryset = queryset.filter(difficulty=difficulty)
        if completed is not None:
            is_completed = completed.lower() in ['true', '1', 'yes']
            queryset = queryset.filter(is_completed=is_completed)
        
        # Ordenar por último acceso
        queryset = queryset.order_by('-last_accessed', '-updated_at')
        
        serializer = SavedQuizListSerializer(queryset, many=True, context={'request': request})
        return JsonResponse({
            'saved_quizzes': serializer.data,
            'count': queryset.count()
        }, status=200)
    
    elif request.method == 'POST':
        serializer = SaveQuizRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return JsonResponse({
                'error': 'Datos inválidos',
                'details': serializer.errors
            }, status=400)
        
        data = serializer.validated_data
        
        # Si se proporciona session_id, obtener datos de la sesión
        questions = data.get('questions', [])
        if 'session_id' in data and data['session_id']:
            try:
                session = GenerationSession.objects.get(id=data['session_id'])
                # Usar datos de la sesión si no se proporcionaron en el request
                topic = data.get('topic', session.topic)
                difficulty = data.get('difficulty', session.difficulty)
                types = data.get('types', session.types)
                counts = data.get('counts', session.counts)
                questions = data.get('questions', session.latest_preview or [])
                
                # Usar categoría de la sesión si existe
                category = getattr(session, 'category', '')
                
            except GenerationSession.DoesNotExist:
                return JsonResponse({
                    'error': 'Sesión no encontrada'
                }, status=404)
        else:
            # Usar datos directamente del request
            topic = data.get('topic', 'Tema no especificado')
            difficulty = data.get('difficulty', 'Fácil')
            types = data.get('types', ['mcq'])
            counts = data.get('counts', {'mcq': len(questions)})
            category = ''
        
        # Detectar si es un quiz de repaso (tiene original_quiz_id)
        original_quiz_id = data.get('original_quiz_id')
        original_quiz = None

        if original_quiz_id:
            try:
                original_quiz = SavedQuiz.objects.get(id=original_quiz_id)
                # Verificación de seguridad: no permitir cadenas profundas
                # Si el "original" ya es un repaso, usar su quiz raíz
                original_quiz = original_quiz.get_root_quiz()
            except SavedQuiz.DoesNotExist:
                # Si no existe el original, continuar sin relación
                # (no bloqueamos el guardado por esto)
                pass

        # Crear el cuestionario guardado
        # Si existe session y no tiene cover_image, intentar generarla (no bloquear)
        cover_image_rel = ''
        if 'session' in locals() and session is not None:
            cover_image_rel = getattr(session, 'cover_image', '') or ''
            if not cover_image_rel:
                try:
                    prompt_for_image = f"{topic} - {difficulty} quiz cover"
                    img_rel = generate_cover_image(prompt_for_image, size=1024, timeout_secs=10)
                    if img_rel:
                        # Persistir en la session para reutilizar en futuras operaciones
                        try:
                            session.cover_image = img_rel
                            session.save(update_fields=['cover_image'])
                        except Exception:
                            pass
                        cover_image_rel = img_rel
                except Exception:
                    cover_image_rel = ''

        saved_quiz = SavedQuiz.objects.create(
            title=data['title'],
            topic=topic,
            category=category,
            difficulty=difficulty,
            types=types,
            counts=counts,
            questions=questions,
            user_answers=data.get('user_answers', {}),
            current_question=data.get('current_question', 0),
            original_quiz=original_quiz,  # Establecer relación jerárquica
            cover_image=cover_image_rel
        )
        
        serializer = SavedQuizSerializer(saved_quiz, context={'request': request})
        return JsonResponse({
            'message': 'Cuestionario guardado exitosamente',
            'saved_quiz': serializer.data
        }, status=201)


@api_view(['GET', 'PUT', 'DELETE'])
def saved_quiz_detail(request, quiz_id):
    """
    GET: Obtiene detalles de un cuestionario guardado
    PUT: Actualiza un cuestionario guardado
    DELETE: Elimina un cuestionario guardado
    """
    saved_quiz = get_object_or_404(SavedQuiz, id=quiz_id)
    
    if request.method == 'GET':
        # Actualizar último acceso
        saved_quiz.last_accessed = timezone.now()
        saved_quiz.save(update_fields=['last_accessed'])
        
        serializer = SavedQuizSerializer(saved_quiz, context={'request': request})
        return JsonResponse({
            'saved_quiz': serializer.data
        }, status=200)
    
    elif request.method == 'PUT':
        # Actualizar progreso del cuestionario
        progress_serializer = UpdateQuizProgressSerializer(data=request.data)
        if not progress_serializer.is_valid():
            return JsonResponse({
                'error': 'Datos inválidos',
                'details': progress_serializer.errors
            }, status=400)
        
        progress_data = progress_serializer.validated_data
        
        # Validar que current_question no exceda el número de preguntas
        if progress_data['current_question'] >= len(saved_quiz.questions):
            if not progress_data.get('is_completed', False):
                return JsonResponse({
                    'error': 'Índice de pregunta fuera de rango'
                }, status=400)
        
        # Actualizar campos
        saved_quiz.current_question = progress_data['current_question']
        saved_quiz.user_answers = progress_data['user_answers']
        saved_quiz.last_accessed = timezone.now()
        
        if 'is_completed' in progress_data:
            saved_quiz.is_completed = progress_data['is_completed']
        
        if 'score' in progress_data:
            saved_quiz.score = progress_data['score']
        
        saved_quiz.save()
        
        serializer = SavedQuizSerializer(saved_quiz, context={'request': request})
        return JsonResponse({
            'message': 'Progreso actualizado exitosamente',
            'saved_quiz': serializer.data
        }, status=200)
    
    elif request.method == 'DELETE':
        saved_quiz.delete()
        return JsonResponse({
            'message': 'Cuestionario eliminado exitosamente'
        }, status=200)


@api_view(['POST'])
def load_saved_quiz(request, quiz_id):
    """
    POST: Carga un cuestionario guardado para continuar
    Crea una nueva sesión de generación basada en el cuestionario guardado
    """
    saved_quiz = get_object_or_404(SavedQuiz, id=quiz_id)
    
    # Crear nueva sesión basada en el cuestionario guardado
    try:
        with transaction.atomic():
            session = GenerationSession.objects.create(
                topic=saved_quiz.topic,
                category=saved_quiz.category,
                difficulty=saved_quiz.difficulty,
                types=saved_quiz.types,
                counts=saved_quiz.counts,
                latest_preview=saved_quiz.questions
            )
            
            # Actualizar último acceso del cuestionario guardado
            saved_quiz.last_accessed = timezone.now()
            saved_quiz.save(update_fields=['last_accessed'])
            
            return JsonResponse({
                'message': 'Cuestionario cargado exitosamente',
                'session_id': str(session.id),
                'saved_quiz_id': str(saved_quiz.id),
                'topic': saved_quiz.topic,
                'difficulty': saved_quiz.difficulty,
                'questions': saved_quiz.questions,
                'user_answers': saved_quiz.user_answers,
                'current_question': saved_quiz.current_question,
                'is_completed': saved_quiz.is_completed
            }, status=201)
            
    except Exception as e:
        return JsonResponse({
            'error': 'Error al cargar el cuestionario',
            'details': str(e)
        }, status=500)


@api_view(['PATCH'])
def toggle_favorite_question(request, quiz_id):
    """
    PATCH: Marca o desmarca una pregunta como favorita (toggle)

    Body params:
        - question_index (int): Índice de la pregunta a marcar/desmarcar

    Returns:
        - favorite_questions: Lista actualizada de preguntas favoritas
        - is_favorite: Estado actual de la pregunta (True si fue marcada, False si fue desmarcada)
    """
    # Validar que el quiz existe
    saved_quiz = get_object_or_404(SavedQuiz, id=quiz_id)

    # Obtener el índice de la pregunta del body
    question_index = request.data.get('question_index')

    # Validar que se proporcionó el índice
    if question_index is None:
        return JsonResponse({
            'error': 'El campo question_index es requerido'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Validar que sea un número entero
    try:
        question_index = int(question_index)
    except (ValueError, TypeError):
        return JsonResponse({
            'error': 'El índice de la pregunta debe ser un número entero'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Validar que el índice esté dentro del rango válido
    if question_index < 0 or question_index >= len(saved_quiz.questions):
        return JsonResponse({
            'error': f'Índice de pregunta inválido. Debe estar entre 0 y {len(saved_quiz.questions) - 1}'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Inicializar favorite_questions si es None o no es una lista
    if saved_quiz.favorite_questions is None or not isinstance(saved_quiz.favorite_questions, list):
        saved_quiz.favorite_questions = []

    # Toggle: agregar o remover el índice
    is_favorite = False
    if question_index in saved_quiz.favorite_questions:
        # Ya está marcada, desmarcamos
        saved_quiz.favorite_questions.remove(question_index)
        is_favorite = False
    else:
        # No está marcada, marcamos
        saved_quiz.favorite_questions.append(question_index)
        is_favorite = True

    # Actualizar solo el campo necesario para optimizar
    saved_quiz.save(update_fields=['favorite_questions', 'updated_at'])

    return JsonResponse({
        'message': f'Pregunta {"marcada" if is_favorite else "desmarcada"} como favorita exitosamente',
        'favorite_questions': saved_quiz.favorite_questions,
        'is_favorite': is_favorite,
        'question_index': question_index
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
def quiz_statistics(request):
    """
    GET: Obtiene estadísticas generales de los cuestionarios guardados
    """
    try:
        # Estadísticas básicas
        total_quizzes = SavedQuiz.objects.count()
        completed_quizzes = SavedQuiz.objects.filter(is_completed=True).count()
        in_progress_quizzes = SavedQuiz.objects.filter(is_completed=False).count()
        
        # Estadísticas por tema
        topic_stats = (SavedQuiz.objects
                      .values('topic')
                      .annotate(count=Count('id'))
                      .order_by('-count')[:10])
        
        # Estadísticas por dificultad
        difficulty_stats = (SavedQuiz.objects
                           .values('difficulty')
                           .annotate(count=Count('id'))
                           .order_by('difficulty'))
        
        # Progreso promedio
        progress_data = SavedQuiz.objects.filter(is_completed=False)
        avg_progress = 0
        if progress_data.exists():
            total_progress = sum([quiz.get_progress_percentage() for quiz in progress_data])
            avg_progress = total_progress / progress_data.count()
        
        # Cuestionarios más recientes
        recent_quizzes = SavedQuiz.objects.order_by('-last_accessed')[:5]
        recent_serializer = SavedQuizListSerializer(recent_quizzes, many=True, context={'request': request})
        
        # Cuestionarios completados recientemente
        recent_completed = (SavedQuiz.objects
                           .filter(is_completed=True)
                           .order_by('-updated_at')[:5])
        completed_serializer = SavedQuizListSerializer(recent_completed, many=True, context={'request': request})
        
        return JsonResponse({
            'statistics': {
                'total_quizzes': total_quizzes,
                'completed_quizzes': completed_quizzes,
                'in_progress_quizzes': in_progress_quizzes,
                'completion_rate': round((completed_quizzes / total_quizzes * 100) if total_quizzes > 0 else 0, 2),
                'average_progress': round(avg_progress, 2)
            },
            'topic_stats': list(topic_stats),
            'difficulty_stats': list(difficulty_stats),
            'recent_quizzes': recent_serializer.data,
            'recent_completed': completed_serializer.data
        }, status=200)
        
    except Exception as e:
        return JsonResponse({
            'error': 'Error al obtener estadísticas',
            'details': str(e)
        }, status=500)


@api_view(['POST'])
def generate_review_quiz(request, quiz_id):
    """
    POST: Genera un nuevo quiz compuesto por variantes de las preguntas favoritas

    Parámetros:
        - quiz_id (UUID): ID del quiz original con preguntas marcadas como favoritas

    Retorna:
        - session_id: ID de la nueva sesión de generación creada
        - questions: Array de variantes generadas
        - original_quiz_id: ID del quiz original para trazabilidad
        - topic: Tema del quiz de repaso
        - count: Cantidad de preguntas generadas

    Errores:
        - 404: Quiz no encontrado
        - 400: No hay preguntas marcadas como favoritas
        - 500: Error en la generación de variantes
        - 503: Sin créditos en proveedores LLM
    """
    # Validar que el quiz existe
    saved_quiz = get_object_or_404(SavedQuiz, id=quiz_id)

    # NUEVA VALIDACIÓN: Verificar si se puede crear repaso desde este quiz
    can_create, reason = saved_quiz.can_create_review()
    if not can_create:
        # Si es un quiz de repaso, sugerir usar el original
        if saved_quiz.is_review_quiz():
            original = saved_quiz.original_quiz
            return JsonResponse({
                'error': 'No se puede crear repaso de un repaso',
                'message': reason,
                'suggestion': 'Usa el quiz original para generar un nuevo repaso',
                'original_quiz_id': str(original.id) if original else None,
                'original_quiz_title': original.title if original else None
            }, status=status.HTTP_400_BAD_REQUEST)
        else:
            # No hay preguntas marcadas
            return JsonResponse({
                'error': 'No hay preguntas marcadas',
                'message': reason
            }, status=status.HTTP_400_BAD_REQUEST)

    # Obtener preguntas marcadas (validadas por can_create_review)
    favorite_questions = saved_quiz.favorite_questions

    # Validar que los índices estén dentro del rango
    questions = saved_quiz.questions
    if not questions or not isinstance(questions, list):
        return JsonResponse({
            'error': 'Quiz sin preguntas válidas',
            'message': 'El quiz no contiene preguntas válidas.'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Filtrar índices válidos
    valid_indices = [idx for idx in favorite_questions if 0 <= idx < len(questions)]
    if not valid_indices:
        return JsonResponse({
            'error': 'Índices de preguntas favoritas inválidos',
            'message': 'Ninguno de los índices de preguntas favoritas es válido para este quiz.'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Obtener configuración del proveedor LLM
    preferred = _header_provider(request)

    try:
        # Recuperar las preguntas favoritas completas
        favorite_base_questions = [questions[idx] for idx in valid_indices]

        # Generar variantes para cada pregunta favorita
        generated_variants = []
        seen_phrases = set()

        for base_question in favorite_base_questions:
            # Obtener datos de la pregunta base
            qtype = base_question.get('type', 'mcq')
            question_text = base_question.get('question', '')

            # Agregar el texto de la pregunta base al conjunto de frases a evitar
            seen_phrases.add(_norm_for_cmp(question_text))

            # Crear conjunto de frases a evitar para esta pregunta
            avoid_phrases = seen_phrases.copy()

            try:
                # Llamar a la función de regeneración con fallback
                variant, provider_used, did_fallback, errors = _regenerate_with_fallback(
                    topic=saved_quiz.topic,
                    difficulty=saved_quiz.difficulty,
                    qtype=qtype,
                    base_q=base_question,
                    avoid_phrases=avoid_phrases,
                    preferred=preferred
                )

                # Agregar la variante generada
                generated_variants.append(variant)

                # Agregar el texto de la variante al conjunto de frases a evitar
                variant_text = variant.get('question', '')
                seen_phrases.add(_norm_for_cmp(variant_text))

            except RuntimeError as e:
                if str(e) == "no_providers_available":
                    return JsonResponse({
                        'error': 'no_providers_available',
                        'message': 'No hay créditos disponibles en los proveedores LLM (Perplexity/Gemini).'
                    }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
                else:
                    # Si falla la generación de una variante, continuar con las demás
                    # pero registrar el error
                    continue

        # Verificar que se generaron al menos algunas variantes
        if not generated_variants:
            return JsonResponse({
                'error': 'No se pudieron generar variantes',
                'message': 'No fue posible generar variantes para ninguna de las preguntas favoritas.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Crear una nueva GenerationSession para el quiz de repaso
        review_topic = f"Repaso: {saved_quiz.topic}"

        # Calcular tipos y conteos basados en las variantes generadas
        types_count = {}
        for variant in generated_variants:
            vtype = variant.get('type', 'mcq')
            types_count[vtype] = types_count.get(vtype, 0) + 1

        types = list(types_count.keys())

        with transaction.atomic():
            review_session = GenerationSession.objects.create(
                topic=review_topic,
                category=saved_quiz.category,
                difficulty=saved_quiz.difficulty,
                types=types,
                counts=types_count,
                latest_preview=generated_variants
            )

        # Retornar respuesta exitosa
        return JsonResponse({
            'message': 'Quiz de repaso generado exitosamente',
            'session_id': str(review_session.id),
            'original_quiz_id': str(saved_quiz.id),
            'topic': review_topic,
            'difficulty': saved_quiz.difficulty,
            'questions': generated_variants,
            'count': len(generated_variants),
            'types': types,
            'counts': types_count
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        return JsonResponse({
            'error': 'Error al generar quiz de repaso',
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)