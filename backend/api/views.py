import os
from django.http import JsonResponse
from rest_framework.decorators import api_view
from dotenv import load_dotenv
import google.generativeai as genai
import json, re


load_dotenv()



def _extract_json(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Respuesta vacía de Gemini")

    # Quita code fences ```json ... ```
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()

    # Si aún trae texto, intenta quedarte con el primer bloque { ... }
    if not raw.lstrip().startswith("{"):
        m = re.search(r"\{.*\}", raw, flags=re.S)
        if not m:
            raise ValueError("No se encontró JSON en la respuesta")
        raw = m.group(0)

    return json.loads(raw)

def generate_questions_with_gemini(topic, difficulty, types, counts):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    genai.configure(api_key=api_key)

    total = sum(int(counts.get(t, 0)) for t in types)

    schema = {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["type", "question", "answer"],
                    "properties": {
                        "type": {"type": "string", "enum": ["mcq","vf","short"]},
                        "question": {"type": "string"},
                        "options": {"type": "array", "items": {"type": "string"}},
                        "answer": {"type": "string"},
                        "explanation": {"type": "string"}
                    }
                }
            }
        },
        "required": ["questions"]
    }

    prompt = f"""
Genera exactamente {total} preguntas sobre "{topic}" en nivel {difficulty}.
Distribución por tipo (counts): {json.dumps(counts, ensure_ascii=False)}.

Reglas:
- mcq: 4 opciones, answer ∈ {{A,B,C,D}}.
- vf: answer ∈ {{Verdadero,Falso}}.
- short: answer = texto corto.
- explanation ≤ 40 palabras.
Devuelve ÚNICAMENTE un JSON que cumpla con el schema dado.
"""

    model = genai.GenerativeModel(
        "gemini-2.0-flash",
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=schema,  # valida el schema en salida
        )
    )

    resp = model.generate_content(prompt)

    raw = (resp.text or "").strip()
    data = json.loads(raw)  # ahora sí debería ser JSON puro

    if "questions" not in data or not isinstance(data["questions"], list):
        raise ValueError("Respuesta sin 'questions' válido")

    # (Opcional) relaja la igualdad exacta para no fallar si el modelo devuelve demás:
    expected = total
    got = len(data["questions"])
    if got < expected:
        raise ValueError(f"Se esperaban {expected} preguntas y llegaron {got}")
    if got > expected:
        data["questions"] = data["questions"][:expected]

    return data["questions"]
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
    "algoritmos", "estructura de datos", "complejidad computacional", "np-completitud",
    "teoría de la computación", "autómatas y gramáticas", "compiladores", "intérpretes",
    "lenguajes de programación", "sistemas de tipos", "verificación formal", "model checking",
    "programación orientada a objetos", "patrones de diseño", "programación funcional",
    "metodologías ágiles", "scrum", "kanban", "devops", "sre", "observabilidad",
    "logging", "monitoring", "tracing", "apm", "optimización de rendimiento", "profiling",
    "cachés", "cdn", "sistemas operativos", "gestión de memoria", "concurrencia",
    "paralelismo", "hilos", "procesos", "bloqueos y semáforos", "sistemas distribuidos",
    "consenso", "microservicios", "arquitectura hexagonal", "ddd", "event sourcing",
    "mensajería asíncrona", "kafka", "rabbitmq", "mqtt", "rest", "graphql", "grpc",
    "redes de computadores", "tcp/ip", "enrutamiento", "dns", "http/2", "http/3", "quic",
    "seguridad informática", "owasp", "criptografía", "pki", "ssl/tls", "iam",
    "seguridad en redes", "seguridad web", "pentesting", "forense digital",
    "bases de datos", "modelado relacional", "normalización", "transacciones",
    "aislamiento y concurrencia", "sql", "pl/sql", "postgresql", "mysql", "sqlite",
    "mariadb", "nosql", "mongodb", "redis", "elasticsearch", "data warehousing",
    "etl", "elt", "data lakes", "big data", "hadoop", "spark", "procesamiento en stream",
    "procesamiento batch", "ingeniería de datos", "mlops", "machine learning",
    "deep learning", "nlp", "computer vision", "reinforcement learning",
    "transformers", "embeddings", "llms", "prompt engineering", "evaluación de llms",
    "edge ai", "federated learning", "differential privacy", "autoML", "explicabilidad (xai)",
    "estadística", "probabilidad", "álgebra lineal", "cálculo", "matemática discreta",
    "optimización", "investigación de operaciones", "series de tiempo",
    "arquitectura de software", "requisitos de software", "uml", "pruebas unitarias",
    "pruebas de integración", "tdd", "ci/cd", "contenedores", "docker", "kubernetes",
    "serverless", "nubes públicas", "aws", "azure", "gcp", "iac (terraform)", "ansible",
    "backend", "frontend", "fullstack", "html", "css", "javascript",
    "typescript", "react", "next.js", "vue", "angular", "svelte", "node.js", "deno",
    "python", "java", "c", "c++", "c#", "go", "rust", "php", "ruby", "swift", "kotlin", "r",
    "matlab", "apis", "sockets", "iot", "sistemas embebidos", "esp32", "arduino", "robótica",
    "gráficos por computador", "opengl", "unity", "unreal", "ar/vr", "hci", "accesibilidad",
    "ux/ui", "bioinformática", "gis", "fintech", "e-commerce", "blockchain",
    "contratos inteligentes", "zk-proofs", "escalado blockchain", "privacidad", "etica en ia"
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
    Si hay GEMINI_API_KEY y todo sale bien: source='gemini'.
    Si falla: source='placeholder'. Con ?debug=1 verás por qué.
    """
    data = request.data
    session_id = data.get('session_id')
    session = None
    if session_id:
        from .models import GenerationSession
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
        topic = data.get('topic','Tema de ejemplo')
        difficulty = data.get('difficulty','Fácil')
        types = data.get('types',['mcq','vf'])
        counts = data.get('counts', {t:1 for t in types})

    # normaliza duplicados
    types = list(dict.fromkeys(types))
    debug = request.GET.get('debug') == '1'

    # intenta Gemini
    gemini_error = None
    try:
        if os.getenv('GEMINI_API_KEY'):
            generated = generate_questions_with_gemini(topic, difficulty, types, counts)
            resp = {'preview': generated, 'source': 'gemini'}
            if debug:
                resp['debug'] = {
                    'env_key_present': True,
                    'topic': topic, 'difficulty': difficulty,
                    'types': types, 'counts': counts
                }
            return JsonResponse(resp, status=200)
        else:
            gemini_error = "GEMINI_API_KEY not set"
    except Exception as e:
        gemini_error = str(e)

    # fallback
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
                    'explanation': 'Explicación breve ≤40 palabras.'
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

    resp = {'preview': preview, 'source': 'placeholder'}
    if debug:
        resp['debug'] = {
            'env_key_present': bool(os.getenv('GEMINI_API_KEY')),
            'gemini_error': gemini_error,
            'topic': topic, 'difficulty': difficulty,
            'types': types, 'counts': counts
        }
    return JsonResponse(resp, status=200)





