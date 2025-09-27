import os
from django.http import JsonResponse
from rest_framework.decorators import api_view
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

@api_view(['POST'])
def gemini_generate(request):
	prompt = request.data.get('prompt', '')
	api_key = os.getenv('GEMINI_API_KEY')
	if not api_key:
		return JsonResponse({'error': 'API key not configured'}, status=500)
	genai.configure(api_key=api_key)
	try:
		model = genai.GenerativeModel('gemini-2.0-flash')
		response = model.generate_content(prompt)
		return JsonResponse({'result': response.text})
	except Exception as e:
		return JsonResponse({'error': str(e)}, status=500)

import os
from django.http import JsonResponse
from rest_framework.decorators import api_view
from rest_framework import status
import uuid
from .models import GenerationSession

# Allowed taxonomy (from backlog)
ALLOWED_TAXONOMY = [
    "algoritmos", "redes", "bd", "bases de datos", "sistemas operativos", "so",
    "poo", "programación orientada a objetos", "ciberseguridad", "ia básica",
    "arquitectura de computadores", "arquitectura"
]

MAX_TOTAL_QUESTIONS = 20
MAX_PER_TYPE = 20

def normalize_topic(t):
    return t.strip().lower()

def find_category_for_topic(topic):
    t = normalize_topic(topic)
    for cat in ALLOWED_TAXONOMY:
        if cat in t or t in cat:
            return cat
    return None

@api_view(['POST'])
def create_session(request):
    data = request.data
    topic = data.get('topic', '')
    difficulty = data.get('difficulty', '')
    types = data.get('types', [])  # expected list e.g. ["mcq","vf"]
    counts = data.get('counts', {}) # expected dict e.g. {"mcq":5,...}

    # Validation
    if not topic:
        return JsonResponse({'error':'topic required'}, status=400)
    cat = find_category_for_topic(topic)
    if not cat:
        return JsonResponse({
            'error':'topic fuera de dominio. Temas permitidos: ' + ', '.join(ALLOWED_TAXONOMY)
        }, status=400)

    if difficulty not in ['Fácil','Media','Difícil', 'Facil', 'Media', 'Dificil']:
        return JsonResponse({'error':'difficulty must be Fácil/Media/Difícil'}, status=400)

    # Normalize difficulty spelling
    if difficulty.lower().startswith('f'):
        difficulty = 'Fácil'
    elif difficulty.lower().startswith('m'):
        difficulty = 'Media'
    else:
        difficulty = 'Difícil'

    # Validate types
    valid_types = {'mcq','vf','short'}
    if not types:
        # default mix: at least two types
        types = ['mcq','vf']

    for t in types:
        if t not in valid_types:
            return JsonResponse({'error':f'type {t} not allowed'}, status=400)

    # Validate counts
    total = 0
    for t in types:
        c = counts.get(t, 0)
        try:
            c = int(c)
        except:
            return JsonResponse({'error':f'count for {t} must be integer'}, status=400)
        if c < 0 or c > MAX_PER_TYPE:
            return JsonResponse({'error':f'count for {t} must be 0..{MAX_PER_TYPE}'}, status=400)
        total += c

    if total == 0:
        return JsonResponse({'error': 'total questions must be > 0'}, status=400)
    if total > MAX_TOTAL_QUESTIONS:
        return JsonResponse({'error': f'total questions ({total}) exceed max {MAX_TOTAL_QUESTIONS}'}, status=400)

    # Create session
    session = GenerationSession.objects.create(
        topic=topic,
        category=cat,
        difficulty=difficulty,
        types=types,
        counts=counts
    )
    return JsonResponse({'session_id': str(session.id), 'topic': topic, 'difficulty': difficulty}, status=201)


@api_view(['POST'])
def preview_questions(request):
    """
    Returns a preview list of questions (dummy if no Generative API configured).
    Expects: session_id OR same payload as create_session (topic,difficulty,types,counts)
    """
    data = request.data
    # Either get session or use payload to create a temporary preview
    session_id = data.get('session_id')
    session = None
    if session_id:
        try:
            session = GenerationSession.objects.get(id=session_id)
        except GenerationSession.DoesNotExist:
            return JsonResponse({'error':'session not found'}, status=404)

    if session:
        topic = session.topic
        difficulty = session.difficulty
        types = session.types
        counts = session.counts
    else:
        # reuse validation from create_session? For brevity we accept payload here
        topic = data.get('topic','Tema de ejemplo')
        difficulty = data.get('difficulty','Fácil')
        types = data.get('types',['mcq','vf'])
        counts = data.get('counts', {t:1 for t in types})

    # If GEMINI_API_KEY present, you may call your gemini_generate function
    # Fallback: create placeholder questions
    api_key = os.getenv('GEMINI_API_KEY')
    preview = []
    for t in types:
        n = int(counts.get(t,0))
        for i in range(1, n+1):
            if t == 'mcq':
                preview.append({
                    'type': 'mcq',
                    'question': f'[{topic}] Pregunta MCQ {i} ({difficulty}) — enunciado ejemplo',
                    'options': ['A) ...','B) ...','C) ...','D) ...'],
                    'answer': 'A',
                    'explanation': 'Explicación breve <=40 palabras.'
                })
            elif t == 'vf':
                preview.append({
                    'type': 'vf',
                    'question': f'[{topic}] Pregunta V/F {i} ({difficulty}) — enunciado ejemplo',
                    'answer': 'Verdadero',
                    'explanation': 'Justificación ≤40 palabras.'
                })
            else:
                preview.append({
                    'type': 'short',
                    'question': f'[{topic}] Pregunta corta {i} ({difficulty}) — enunciado ejemplo',
                    'answer': 'Respuesta esperada (criterio de corrección).'
                })
    return JsonResponse({'preview': preview}, status=200)
