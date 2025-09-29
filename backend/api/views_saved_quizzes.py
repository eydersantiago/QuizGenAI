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
        
        serializer = SavedQuizListSerializer(queryset, many=True)
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
        
        # Crear el cuestionario guardado
        saved_quiz = SavedQuiz.objects.create(
            title=data['title'],
            topic=topic,
            category=category,
            difficulty=difficulty,
            types=types,
            counts=counts,
            questions=questions,
            user_answers=data.get('user_answers', {}),
            current_question=data.get('current_question', 0)
        )
        
        serializer = SavedQuizSerializer(saved_quiz)
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
        
        serializer = SavedQuizSerializer(saved_quiz)
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
        
        serializer = SavedQuizSerializer(saved_quiz)
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
        recent_serializer = SavedQuizListSerializer(recent_quizzes, many=True)
        
        # Cuestionarios completados recientemente
        recent_completed = (SavedQuiz.objects
                           .filter(is_completed=True)
                           .order_by('-updated_at')[:5])
        completed_serializer = SavedQuizListSerializer(recent_completed, many=True)
        
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