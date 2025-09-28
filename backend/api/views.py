# api/views.py
import os
import json
import re
import uuid
from dotenv import load_dotenv
from django.http import JsonResponse
from rest_framework.decorators import api_view
from rest_framework import status

import google.generativeai as genai
from .models import GenerationSession, RegenerationLog

load_dotenv()

# -------------------- Utilidades --------------------

def _extract_json(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Respuesta vacía de Gemini")
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
    if not raw.lstrip().startswith("{"):
        m = re.search(r"\{.*\}", raw, flags=re.S)
        if not m:
            raise ValueError("No se encontró JSON en la respuesta")
        raw = m.group(0)
    return json.loads(raw)


def _configure_gemini():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    genai.configure(api_key=api_key)


def _normalize_difficulty(diff: str) -> str:
    d = (diff or "").strip().lower()
    if d.startswith("f"):
        return "Fácil"
    if d.startswith("m"):
        return "Media"
    return "Difícil"


# -------------------- Gemini prompts --------------------

def generate_questions_with_gemini(topic, difficulty, types, counts):
    _configure_gemini()

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
            response_schema=schema,
        )
    )
    resp = model.generate_content(prompt)
    raw = (resp.text or "").strip()
    data = json.loads(raw)

    if "questions" not in data or not isinstance(data["questions"], list):
        raise ValueError("Respuesta sin 'questions' válido")

    expected = total
    got = len(data["questions"])
    if got < expected:
        raise ValueError(f"Se esperaban {expected} preguntas y llegaron {got}")
    if got > expected:
        data["questions"] = data["questions"][:expected]

    return data["questions"]

def regenerate_question_with_gemini(topic, difficulty, qtype, base_question=None):
    _configure_gemini()

    schema = {
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

    if qtype not in ("mcq", "vf", "short"):
        qtype = "mcq"

    seed_clause = ""
    if base_question:
        seed_txt = json.dumps({
            "type": base_question.get("type"),
            "question": base_question.get("question"),
            "options": base_question.get("options"),
            "answer": base_question.get("answer"),
        }, ensure_ascii=False)
        seed_clause = (
            "Toma como referencia conceptual la pregunta base, pero **prohíbe** reutilizar el mismo enunciado, "
            "ejemplos, números o nombres concretos. Cambia el foco o los datos para crear una variante clara. "
            "No repitas frases ni listas tal cual.\n"
            f"Pregunta base:\n{seed_txt}\n"
        )

    rules = """
Reglas:
- Mantén el mismo tema y dificultad.
- Si type=mcq: 4 opciones nuevas (no reutilizar el mismo texto de la base), "answer" ∈ {A,B,C,D}.
- Si type=vf: genera un enunciado nuevo (no negación trivial del anterior), "answer" ∈ {"Verdadero","Falso"}.
- Si type=short: responde con solución esperada breve (texto), y máx. 40 palabras en "explanation" si la incluyes.
- Devuelve SOLO JSON válido al schema. No incluyas texto extra.
"""

    prompt = f"""
Genera 1 pregunta de tipo "{qtype}" sobre "{topic}" en nivel {difficulty}.
{seed_clause}
{rules}
"""

    model = genai.GenerativeModel(
        "gemini-2.0-flash",
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=schema,
        )
    )
    resp = model.generate_content(prompt)
    raw = (resp.text or "").strip()
    data = json.loads(raw)

    # Normalizaciones mínimas…
    if data.get("type") != qtype:
        data["type"] = qtype
    if qtype == "mcq":
        opts = data.get("options", [])
        if not isinstance(opts, list) or len(opts) != 4:
            data["options"] = ["A) Opción 1", "B) Opción 2", "C) Opción 3", "D) Opción 4"]
            data["answer"] = "A"
        else:
            ans = str(data.get("answer","A")).strip().upper()[:1]
            if ans not in ("A","B","C","D"):
                data["answer"] = "A"
    if qtype == "vf":
        ans = str(data.get("answer","")).strip().capitalize()
        if ans not in ("Verdadero","Falso"):
            data["answer"] = "Verdadero"

    return data

# -------------------- Taxonomía y validación --------------------

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
    return (t or "").strip().lower()

def find_category_for_topic(topic):
    t = normalize_topic(topic)
    for cat in ALLOWED_TAXONOMY:
        if cat in t or t in cat:
            return cat
    return None


# -------------------- Endpoints --------------------

@api_view(['POST'])
def sessions(request):
    data = request.data
    topic = data.get('topic', '')
    difficulty = _normalize_difficulty(data.get('difficulty', ''))
    types = data.get('types', [])  # ["mcq","vf"]
    counts = data.get('counts', {})

    if not topic:
        return JsonResponse({'error':'topic required'}, status=400)
    cat = find_category_for_topic(topic)
    if not cat:
        return JsonResponse({
            'error':'topic fuera de dominio. Temas permitidos: ' + ', '.join(ALLOWED_TAXONOMY)
        }, status=400)

    valid_types = {'mcq','vf','short'}
    if not types:
        types = ['mcq','vf']
    for t in types:
        if t not in valid_types:
            return JsonResponse({'error':f'type {t} not allowed'}, status=400)

    total = 0
    for t in types:
        try:
            c = int(counts.get(t, 0))
        except:
            return JsonResponse({'error':f'count for {t} must be integer'}, status=400)
        if c < 0 or c > MAX_PER_TYPE:
            return JsonResponse({'error':f'count for {t} must be 0..{MAX_PER_TYPE}'}, status=400)
        total += c

    if total == 0:
        return JsonResponse({'error': 'total questions must be > 0'}, status=400)
    if total > MAX_TOTAL_QUESTIONS:
        return JsonResponse({'error': f'total questions ({total}) exceed max {MAX_TOTAL_QUESTIONS}'}, status=400)

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
    POST /api/preview/?debug=1
    body: { session_id? , topic?, difficulty?, types?, counts? }
    - Si session_id existe, usa la configuración guardada y PERSISTE latest_preview en DB.
    """
    data = request.data
    session = None
    session_id = data.get('session_id')
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
        topic = data.get('topic','Tema de ejemplo')
        difficulty = _normalize_difficulty(data.get('difficulty','Fácil'))
        types = data.get('types',['mcq','vf'])
        counts = data.get('counts', {t:1 for t in types})

    types = list(dict.fromkeys(types))
    debug = request.GET.get('debug') == '1'

    gemini_error = None
    try:
        if os.getenv('GEMINI_API_KEY'):
            generated = generate_questions_with_gemini(topic, difficulty, types, counts)
            # Si hay sesión, persistimos latest_preview
            if session:
                session.latest_preview = generated
                session.save(update_fields=["latest_preview"])
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

    if session:
        session.latest_preview = preview
        session.save(update_fields=["latest_preview"])

    resp = {'preview': preview, 'source': 'placeholder'}
    if debug:
        resp['debug'] = {
            'env_key_present': bool(os.getenv('GEMINI_API_KEY')),
            'gemini_error': gemini_error,
            'topic': topic, 'difficulty': difficulty,
            'types': types, 'counts': counts
        }
    return JsonResponse(resp, status=200)


@api_view(['POST'])
def regenerate_question(request):
    """
    POST /api/regenerate/?debug=1
    body: { session_id: str, index: int, type?: "mcq"|"vf"|"short" }

    Usa session.latest_preview[index] como base (si existe) y genera una variante.
    Guarda un registro en RegenerationLog con la vieja y la nueva versión.
    Devuelve SOLO la nueva pregunta (para colocarla como borrador en el frontend).
    """
    data = request.data
    debug = request.GET.get('debug') == '1'

    # Validaciones básicas
    session_id = data.get("session_id")
    if not session_id:
        return JsonResponse({"error": "session_id requerido"}, status=400)
    try:
        session = GenerationSession.objects.get(id=session_id)
    except GenerationSession.DoesNotExist:
        return JsonResponse({"error": "session not found"}, status=404)

    try:
        index = int(data.get("index", -1))
    except Exception:
        return JsonResponse({"error": "index inválido"}, status=400)
    if index < 0:
        return JsonResponse({"error": "index debe ser >= 0"}, status=400)

    qtype = data.get("type")
    # Si no envían type, intentamos inferirlo del preview guardado
    base_q = None
    if isinstance(session.latest_preview, list) and 0 <= index < len(session.latest_preview):
        base_q = session.latest_preview[index]
        qtype = qtype or base_q.get("type")

    qtype = qtype or "mcq"
    topic = session.topic
    difficulty = session.difficulty

    gemini_error = None
    try:
        if os.getenv("GEMINI_API_KEY"):
            new_q = regenerate_question_with_gemini(topic, difficulty, qtype, base_q)
        else:
            gemini_error = "GEMINI_API_KEY not set"
            raise RuntimeError(gemini_error)
    except Exception as e:
        gemini_error = gemini_error or str(e)
        import random, uuid as _uuid
        uid = str(_uuid.uuid4())[:8]

        if qtype == "mcq":
            new_q = {
                "type": "mcq",
                "question": f"[{topic}] Variante ({difficulty}) — caso {uid}: Selecciona la opción correcta sobre {topic}.",
                "options": [
                    "A) Definición correcta (caso nuevo).",
                    "B) Distractor plausible 1.",
                    "C) Distractor plausible 2.",
                    "D) Distractor plausible 3."
                ],
                "answer": random.choice(["A","B","C","D"]),
                "explanation": "Variante generada localmente para desarrollo."
            }
        elif qtype == "vf":
            stmt = f"En {topic}, todo algoritmo recursivo es siempre más eficiente que su versión iterativa. ({uid})"
            new_q = {
                "type": "vf",
                "question": stmt,
                "answer": random.choice(["Verdadero","Falso"]),
                "explanation": "Variante local; reemplaza con Gemini en producción."
            }
        else:
            new_q = {
                "type": "short",
                "question": f"[{topic}] Explica brevemente el concepto clave (variante {uid}).",
                "answer": "Respuesta esperada breve.",
                "explanation": "Variante local."
            }


    # Registra historial
    try:
        RegenerationLog.objects.create(
            session=session,
            index=index,
            old_question=base_q or {},
            new_question=new_q
        )
    except Exception:
        # no bloquea la respuesta si fallara guardar log
        pass

    # NO reemplazamos en DB automáticamente: el reemplazo final lo decide el cliente.
    # Pero opcionalmente puedes mantener una "draft buffer" por índice si quieres.
    resp = {"question": new_q, "source": "gemini" if not gemini_error else "placeholder"}
    if debug:
        resp["debug"] = {
            "env_key_present": bool(os.getenv("GEMINI_API_KEY")),
            "gemini_error": gemini_error,
            "topic": topic, "difficulty": difficulty, "type": qtype,
            "base_available": base_q is not None
        }
    return JsonResponse(resp, status=200)


@api_view(['POST'])
def confirm_replace(request):
    """
    POST /api/confirm-replace/
    body: { session_id: str, index: int, question: {...} }
    Actualiza session.latest_preview[index] = question
    """
    data = request.data
    session_id = data.get("session_id")
    try:
        session = GenerationSession.objects.get(id=session_id)
    except Exception:
        return JsonResponse({"error":"session not found"}, status=404)

    try:
        index = int(data.get("index", -1))
    except Exception:
        return JsonResponse({"error":"index inválido"}, status=400)
    if index < 0:
        return JsonResponse({"error":"index debe ser >= 0"}, status=400)

    new_q = data.get("question")
    if not isinstance(new_q, dict) or "type" not in new_q or "question" not in new_q or "answer" not in new_q:
        return JsonResponse({"error":"question inválida o incompleta"}, status=400)

    lp = list(session.latest_preview or [])
    # Si el index se sale, expandimos con vacíos:
    while len(lp) <= index:
        lp.append({})
    lp[index] = new_q
    session.latest_preview = lp
    session.save(update_fields=["latest_preview"])

    return JsonResponse({"ok": True})



# -------------------- Prueba libre (opcional) --------------------

@api_view(['POST'])
def gemini_generate(request):
    prompt = request.data.get('prompt', '')
    try:
        _configure_gemini()
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
        return JsonResponse({'result': response.text})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
