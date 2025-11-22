# api/views.py
import os
import json
import re
import uuid
from dotenv import load_dotenv
from django.http import JsonResponse, HttpResponse, FileResponse
from rest_framework.decorators import api_view
from rest_framework import status
from django.utils import timezone
import requests  # <— NUEVO
import base64
import time
from typing import List
import concurrent.futures
import mimetypes
from django.http import Http404


#import google.generativeai as genai
from .models import GenerationSession, RegenerationLog

load_dotenv()

# =========================================================
# Endpoint de salud para diagnóstico
import io
from django.conf import settings

# PIL is optional; try to import for convenience
# =========================================================
try:
    from PIL import Image as PILImage
except Exception:
    PILImage = None
# =========================================================

@api_view(['GET'])
def health_check(request):
    """Endpoint simple para verificar que el backend está funcionando"""
    return JsonResponse({
        'status': 'ok',
        'message': 'Backend funcionando correctamente',
        'timestamp': timezone.now().isoformat()
    })


@api_view(['GET'])
def serve_generated_media(request, filepath: str):
    """
    Servir archivos desde MEDIA_ROOT de forma controlada.
    URL propuesta: /api/media/proxy/<path:filepath>/
    - Evita traversal y sólo entrega archivos dentro de MEDIA_ROOT.
    - Útil en desarrollo o cuando quieras que la API devuelva la imagen
      como recurso del mismo origen (evita problemas de mixed-content).
    """
    # Normalizar y prevenir path traversal
    if not filepath or '..' in filepath or filepath.startswith('/') or filepath.startswith('\\'):
        raise Http404("Invalid path")

    # Solo servir archivos dentro de la subcarpeta 'generated' para mitigar exposición accidental
    fp_norm = filepath.replace('\\', '/').lstrip('/')
    if not fp_norm.startswith('generated/'):
        raise Http404("Not allowed")

    # Construir ruta absoluta y validar que esté dentro de MEDIA_ROOT
    fullpath = os.path.normpath(os.path.join(str(settings.MEDIA_ROOT), fp_norm))
    media_root_norm = os.path.normpath(str(settings.MEDIA_ROOT))
    if not fullpath.startswith(media_root_norm):
        raise Http404("Not allowed")

    if not os.path.exists(fullpath) or not os.path.isfile(fullpath):
        raise Http404("File not found")

    ct = mimetypes.guess_type(fullpath)[0] or 'application/octet-stream'
    fh = open(fullpath, 'rb')
    resp = FileResponse(fh, content_type=ct)
    resp['Content-Length'] = str(os.path.getsize(fullpath))
    resp['Content-Disposition'] = f'inline; filename="{os.path.basename(fullpath)}"'
    return resp

# =========================================================
# Utilidades generales
# =========================================================

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


PPLX_API = "https://api.perplexity.ai/chat/completions"
PPLX_DEFAULT_MODEL = os.getenv("PPLX_MODEL", "llama-3.1-sonar-small-128k-chat")  # ajustable por .env

def _pplx_call_json(prompt: str, max_tokens: int = 1200, temperature: float = 0.9) -> str:
    api_key = os.getenv("PPLX_API_KEY")
    if not api_key:
        raise RuntimeError("PPLX_API_KEY not set")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": PPLX_DEFAULT_MODEL,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Eres un generador de preguntas de programación/CS. "
                    "Debes responder **ÚNICAMENTE** con JSON válido, nada de texto extra ni explicaciones fuera del JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    r = requests.post(PPLX_API, headers=headers, json=body, timeout=60)
    if r.status_code != 200:
        # propagar texto de error, útil para detectar 'no credits'
        raise RuntimeError(f"pplx_http_{r.status_code}: {r.text}")

    data = r.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        raise RuntimeError("pplx_invalid_response")

    return content  # cadena con JSON (según prompt)



# =========================================================
# Moderación / Calidad (HU-08 simple)
# =========================================================

BAD_WORDS = {
    "idiota","estúpido","imbécil","tarado","mierda","maldito","pendejo","marica","negro de ****",
}
STEREOTYPE_PATTERNS = [
    r"\blas\s+mujeres\s+son\b",
    r"\blos\s+hombres\s+son\b",
    r"\blos\s+\w+\s+son\b",
]
AMBIG_MARKERS = [
    "etc.", "etc", "...", "depende", "generalmente", "a veces", "comúnmente",
    "de manera subjetiva", "podría ser cualquiera", "no hay respuesta correcta",
]
SUBJECTIVE_MARKERS = ["mejor", "peor", "más bonito", "más feo"]

def _norm_txt(s: str) -> str:
    return (s or "").strip().lower()

def _has_offense_or_stereotype(text: str) -> bool:
    t = _norm_txt(text)
    if any(bw in t for bw in BAD_WORDS):
        return True
    return any(re.search(pat, t) for pat in STEREOTYPE_PATTERNS)

def _is_ambiguous(text: str) -> bool:
    t = _norm_txt(text)
    return any(marker in t for marker in AMBIG_MARKERS)

def _is_too_subjective(text: str) -> bool:
    t = _norm_txt(text)
    return any(w in t for w in SUBJECTIVE_MARKERS)

def _mcq_has_issues(options) -> bool:
    if not isinstance(options, list) or len(options) != 4:
        return True
    cleaned = [(_norm_txt(o) or "") for o in options]
    if any(not c for c in cleaned):
        return True
    if len(set(cleaned)) < 4:
        return True
    return False

def review_question(q: dict) -> list:
    """
    Devuelve lista de issues: 
    ["offensive_or_stereotype","ambiguous","subjective","mcq_invalid","vf_invalid","too_long"]
    Si lista vacía => OK.
    """
    issues = []
    qtype = (q.get("type") or "").lower()
    question = q.get("question") or ""

    if _has_offense_or_stereotype(question):
        issues.append("offensive_or_stereotype")
    if _is_ambiguous(question):
        issues.append("ambiguous")
    if _is_too_subjective(question):
        issues.append("subjective")

    if qtype == "mcq":
        if _mcq_has_issues(q.get("options")):
            issues.append("mcq_invalid")
        ans = str(q.get("answer","")).strip().upper()[:1]
        if ans not in ("A","B","C","D"):
            issues.append("mcq_invalid")

    if qtype == "vf":
        ans = str(q.get("answer","")).strip().capitalize()
        if ans not in ("Verdadero","Falso"):
            issues.append("vf_invalid")

    if len(question) > 300:
        issues.append("too_long")

    return issues

def moderation_severity(issues: list) -> str:
    """'severe' si hay ofensa/estereotipo; 'minor' para el resto; '' si vacío."""
    if not issues:
        return ""
    if "offensive_or_stereotype" in issues:
        return "severe"
    return "minor"


# =========================================================
# Anti-repetición (diversidad)
# =========================================================

def _norm_for_cmp(s: str) -> str:
    return re.sub(r"[\W_]+", " ", (s or "").lower()).strip()

def build_seen_set(session: GenerationSession, index: int = None) -> set:
    seen = set()
    if isinstance(session.latest_preview, list):
        for q in session.latest_preview:
            if isinstance(q, dict):
                seen.add(_norm_for_cmp(q.get("question", "")))
    try:
        logs = session.regens.all().order_by("-id")[:50]
        for lg in logs:
            if index is None or lg.index == index:
                seen.add(_norm_for_cmp((lg.old_question or {}).get("question", "")))
                seen.add(_norm_for_cmp((lg.new_question or {}).get("question", "")))
    except Exception:
        pass
    return {s for s in seen if s}


# =========================================================
# Gemini prompts (modelo y helpers)
# =========================================================


def generate_questions_with_pplx(topic, difficulty, types, counts):
    total = sum(int(counts.get(t, 0)) for t in types)

    schema_hint = json.dumps(_json_schema_questions(), ensure_ascii=False)
    prompt = f"""
Genera exactamente {total} preguntas sobre "{topic}" en nivel {difficulty}.
Distribución por tipo (counts): {json.dumps(counts, ensure_ascii=False)}.

Política de calidad (OBLIGATORIA):
- Sin sesgos ni estereotipos.
- Sin lenguaje ofensivo.
- Evita ambigüedades: no uses “etc.”, “…”, “depende”, “generalmente”.
- mcq: 4 opciones distintas, answer ∈ {{A,B,C,D}}.
- vf: answer ∈ {{Verdadero,Falso}}.
- short: answer = texto corto.
- explanation ≤ 40 palabras.

Devuelve SOLO un JSON que cumpla con este schema:
{schema_hint}
"""
    raw = _pplx_call_json(prompt, temperature=0.9, max_tokens=1800)
    data = _extract_json(raw)

    if "questions" not in data or not isinstance(data["questions"], list):
        raise ValueError("Respuesta PPLX sin 'questions' válido")

    expected = total
    got = len(data["questions"])
    if got < expected:
        raise ValueError(f"Se esperaban {expected} preguntas y llegaron {got}")
    if got > expected:
        data["questions"] = data["questions"][:expected]

    return data["questions"]


def regenerate_question_with_pplx(topic, difficulty, qtype, base_question=None, avoid_phrases=None):
    schema_hint = json.dumps(_json_schema_one(), ensure_ascii=False)
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
            "Toma como referencia conceptual la pregunta base, pero PROHÍBE reutilizar el mismo enunciado, "
            "ejemplos, números o nombres. Cambia foco o valores para una variante clara.\n"
            f"Pregunta base:\n{seed_txt}\n"
        )

    avoid_txt = ""
    if avoid_phrases:
        bullets = "\n".join(f"- {p}" for p in list(avoid_phrases)[:8])
        avoid_txt = f"Evita enunciados similares a:\n{bullets}\n"

    rules = """
Reglas de calidad:
- Mantén tema y dificultad.
- Prohibido reutilizar enunciado/datos de la base.
- Sin sesgos/estereotipos ni lenguaje ofensivo.
- Evita ambigüedades (no “etc.”, “…”, “depende”, “generalmente”).
- mcq: 4 opciones nuevas; answer ∈ {A,B,C,D}.
- vf: enunciado nuevo (no negación trivial); answer ∈ {"Verdadero","Falso"}.
- short: respuesta breve; explanation ≤ 40 palabras.
Responde SOLO con JSON del schema indicado.
"""

    prompt = f"""
Genera 1 pregunta de tipo "{qtype}" sobre "{topic}" en nivel {difficulty}.
{seed_clause}
{avoid_txt}
{rules}

Schema:
{schema_hint}
"""

    raw = _pplx_call_json(prompt, temperature=0.95, max_tokens=800)
    data = _extract_json(raw)

    # Normalizaciones (mismas que Gemini)
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




def _get_genai():
    """
    Import tardío para evitar que Azure cargue primero /agents/python y rompa typing_extensions.
    Si falla la importación, elevamos un RuntimeError 'genai_unavailable' que se maneja como 503.
    """
    try:
        import google.generativeai as genai  # import perezoso
        return genai
    except Exception as e:
        raise RuntimeError(f"genai_unavailable: {e}")

def _configure_gemini():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    genai = _get_genai()
    genai.configure(api_key=api_key)
    return genai




# Modelo con free tier generoso y buen rendimiento.
GEMINI_MODEL = "gemini-2.5-flash"

def _json_schema_questions():
    return {
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

def _json_schema_one():
    return {
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

def generate_questions_with_gemini(topic, difficulty, types, counts):
    # Configurar e importar aquí (perezoso)
    genai = _configure_gemini()

    total = sum(int(counts.get(t, 0)) for t in types)
    schema = _json_schema_questions()

    prompt = f"""
Genera exactamente {total} preguntas sobre "{topic}" en nivel {difficulty}.
Distribución por tipo (counts): {json.dumps(counts, ensure_ascii=False)}.

Política de calidad (OBLIGATORIA):
- Sin sesgos ni estereotipos (no generalizaciones sobre grupos).
- Sin lenguaje ofensivo.
- Evita ambigüedades: no uses “etc.”, “…”, “depende”, “generalmente”.
- Enunciados claros, objetivos y específicos para informática/sistemas.
- mcq: 4 opciones distintas, answer ∈ {{A,B,C,D}}.
- vf: answer ∈ {{Verdadero,Falso}}.
- short: answer = texto corto.
- explanation ≤ 40 palabras.
Devuelve ÚNICAMENTE un JSON que cumpla con el schema dado.
"""

    model = genai.GenerativeModel(
        GEMINI_MODEL,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.9,
            top_p=0.95,
            top_k=64,
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


def regenerate_question_with_gemini(topic, difficulty, qtype, base_question=None, avoid_phrases=None):
    """
    Genera UNA variante, manteniendo tema/dificultad/tipo.
    - avoid_phrases: set/list de enunciados normalizados a evitar (anti-repetición).
    """
    # Configurar e importar aquí (perezoso)
    genai = _configure_gemini()

    schema = _json_schema_one()
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

    avoid_txt = ""
    if avoid_phrases:
        bullets = "\n".join(f"- {p}" for p in list(avoid_phrases)[:8])
        avoid_txt = f"Evita formular enunciados similares a los siguientes:\n{bullets}\n"

    rules = """
Reglas de calidad:
- Mantén el mismo tema y dificultad.
- Prohibido reutilizar el mismo enunciado/datos de la base (cambia foco o valores).
- Sin sesgos/estereotipos, sin lenguaje ofensivo.
- Evita ambigüedades: no uses “etc.”, “…”, “depende”, “generalmente”.
- type=mcq: 4 opciones nuevas y distintas; "answer" ∈ {A,B,C,D}.
- type=vf: enunciado nuevo (no negación trivial); "answer" ∈ {"Verdadero","Falso"}.
- type=short: solución breve; "explanation" ≤ 40 palabras.
- Responde SOLO con JSON válido al schema.
"""

    prompt = f"""
Genera 1 pregunta de tipo "{qtype}" sobre "{topic}" en nivel {difficulty}.
{seed_clause}
{avoid_txt}
{rules}
"""

    model = genai.GenerativeModel(
        GEMINI_MODEL,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.95,
            top_p=0.95,
            top_k=64,
        )
    )
    resp = model.generate_content(prompt)
    raw = (resp.text or "").strip()
    data = json.loads(raw)

    # Normalizaciones mínimas
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



def _generate_with_fallback(topic, difficulty, types, counts, preferred: str):
    """
    Devuelve (questions, provider_used, fallback_used, errors_map)
    Si ambos fallan por créditos -> levanta RuntimeError('no_providers_available')
    """
    order = [preferred, "gemini" if preferred == "perplexity" else "perplexity"]
    errors = {}
    fallback_used = False

    for i, prov in enumerate(order):
        try:
            if prov == "gemini":
                qs = generate_questions_with_gemini(topic, difficulty, types, counts)
            else:
                qs = generate_questions_with_pplx(topic, difficulty, types, counts)
            return qs, prov, fallback_used, errors
        except Exception as e:
            msg = str(e)
            errors[prov] = {"message": msg, "no_credits": _is_no_credits_msg(msg)}
            if i == 0:
                fallback_used = True
            continue

    # Ambos fallaron:
    if errors.get(order[0], {}).get("no_credits") and errors.get(order[1], {}).get("no_credits"):
        raise RuntimeError("no_providers_available")
    # Otro error (red, esquema, etc.)
    raise RuntimeError(f"providers_failed: {errors}")


def _regenerate_with_fallback(topic, difficulty, qtype, base_q, avoid_phrases, preferred: str):
    """
    Devuelve (question, provider_used, fallback_used, errors_map)
    """
    order = [preferred, "gemini" if preferred == "perplexity" else "perplexity"]
    errors = {}
    fallback_used = False

    for i, prov in enumerate(order):
        try:
            if prov == "gemini":
                q = regenerate_question_with_gemini(topic, difficulty, qtype, base_q, avoid_phrases)
            else:
                q = regenerate_question_with_pplx(topic, difficulty, qtype, base_q, avoid_phrases)
            return q, prov, fallback_used, errors
        except Exception as e:
            msg = str(e)
            errors[prov] = {"message": msg, "no_credits": _is_no_credits_msg(msg)}
            if i == 0:
                fallback_used = True
            continue

    if errors.get(order[0], {}).get("no_credits") and errors.get(order[1], {}).get("no_credits"):
        raise RuntimeError("no_providers_available")
    raise RuntimeError(f"providers_failed: {errors}")


# =========================================================
# Taxonomía / Dominio (HU-06)
# =========================================================

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


# ---------------------------
# Proveedor y fallback
# ---------------------------

def _header_provider(request) -> str:
    """Lee X-LLM-Provider y normaliza -> 'perplexity' | 'gemini'."""
    raw = (request.headers.get("X-LLM-Provider") or "").strip().lower()
    if raw.startswith("gemini"):
        return "gemini"
    if raw in ("perplexity", "pplx"):
        return "perplexity"
    # por defecto, lo que tengas como preferido
    return "perplexity"

def _is_no_credits_msg(msg: str) -> bool:
    m = (msg or "").lower()
    # heurística suficiente para 402/429/quotas/creditos
    return any(kw in m for kw in [
        "quota", "over quota", "insufficient", "billing", "payment required",
        "credit", "out of credits", "429", "402"
    ])



# =========================================================
# Endpoints
# =========================================================

@api_view(['POST'])
def sessions(request):
    data = request.data
    topic = data.get('topic', '')
    difficulty = _normalize_difficulty(data.get('difficulty', ''))
    types = data.get('types', [])  # ["mcq","vf"]
    counts = data.get('counts', {})
    image_counts = data.get('image_counts', {})

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

    # Intentar crear la sesión incluyendo image_counts. Si la migración no se aplicó
    # y la columna no existe en la base de datos, caerá aquí y haremos un fallback
    # creando la sesión sin ese campo para evitar un 500 en producción.
    try:
        session = GenerationSession.objects.create(
            topic=topic,
            category=cat,
            difficulty=difficulty,
            types=types,
            counts=counts,
            image_counts=image_counts
        )
    except Exception:
        # Loguear opcionalmente
        try:
            session = GenerationSession.objects.create(
                topic=topic,
                category=cat,
                difficulty=difficulty,
                types=types,
                counts=counts
            )
        except Exception as e:
            # Si falla incluso sin image_counts, propagar para que el manejador superior lo vea
            raise
    # Intentar generar portada asociada a la sesión (timeout corto)
    try:
        prompt_for_image = f"{topic} - {difficulty} quiz cover"
        img_rel = generate_cover_image(prompt_for_image, size=1024, timeout_secs=10)
        if img_rel:
            session.cover_image = img_rel
            session.save(update_fields=['cover_image'])
    except Exception:
        # No bloquear la creación de la sesión por fallo en generación de imagen
        pass
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

    preferred = _header_provider(request)
    try:
        generated, provider_used, did_fallback, errors = _generate_with_fallback(
            topic, difficulty, types, counts, preferred
        )

        # === Moderación + anti-dup como ya lo tenías ===
        clean = []
        moderation = {"flagged": 0, "details": []}
        seen = set()

        for i, q in enumerate(generated):
            issues = review_question(q)
            sev = moderation_severity(issues)
            is_dup = _norm_for_cmp(q.get("question","")) in seen

            if not issues and not is_dup:
                clean.append(q)
                seen.add(_norm_for_cmp(q.get("question","")))
                continue

            moderation["flagged"] += 1
            moderation["details"].append({"index": i, "issues": issues, "severity": sev, "dup": is_dup})

            if sev == "severe":
                try:
                    fixed = _regenerate_with_fallback(topic, difficulty, q.get("type","mcq"), q, seen, provider_used)[0]
                    if moderation_severity(review_question(fixed)) != "severe":
                        clean.append(fixed)
                        seen.add(_norm_for_cmp(fixed.get("question","")))
                    else:
                        clean.append({
                            "type": q.get("type","mcq"),
                            "question": f"[{topic}] Pregunta ajustada por moderación — describe el concepto con claridad.",
                            "options": ["A) Definición correcta","B) Distractor 1","C) Distractor 2","D) Distractor 3"] if q.get("type")=="mcq" else None,
                            "answer": "A" if q.get("type")=="mcq" else ("Verdadero" if q.get("type")=="vf" else "Respuesta breve"),
                            "explanation": "Ajuste automático por reglas de calidad (HU-08)."
                        })
                except Exception:
                    clean.append({
                        "type": q.get("type","mcq"),
                        "question": f"[{topic}] Pregunta ajustada por moderación — redacta con claridad.",
                        "options": ["A) Opción 1","B) Opción 2","C) Opción 3","D) Opción 4"] if q.get("type")=="mcq" else None,
                        "answer": "A" if q.get("type")=="mcq" else ("Verdadero" if q.get("type")=="vf" else "Respuesta breve"),
                        "explanation": "Ajuste automático por reglas de calidad (HU-08)."
                    })
            else:
                try:
                    fixed = _regenerate_with_fallback(topic, difficulty, q.get("type","mcq"), q, seen, provider_used)[0]
                    candidate = fixed if moderation_severity(review_question(fixed)) != "severe" else q
                except Exception:
                    candidate = q
                clean.append(candidate)
                seen.add(_norm_for_cmp(candidate.get("question","")))

        generated = clean

        if session:
            # Si el cliente indicó image_counts al crear la sesión, adjuntar imágenes a algunas preguntas
            try:
                img_counts = getattr(session, 'image_counts', None) or (data.get('image_counts') if isinstance(data, dict) else {})
                if img_counts:
                    attach_images_to_questions(topic, img_counts, generated, session=session, request=request, size=512, timeout_secs=10)
            except Exception:
                # No bloquear el preview por fallos en la generación de imágenes de preguntas
                pass

            # Persistir preview (incluye posibles campos image_rel/image_url añadidos)
            session.latest_preview = generated
            session.save(update_fields=["latest_preview"])

            # Si la sesión no tiene imagen de portada persistida, intentar generarla
            try:
                if not getattr(session, 'cover_image', ''):
                    prompt_for_image = f"{topic} - {difficulty} quiz cover"
                    img_rel = generate_cover_image(prompt_for_image, size=1024, timeout_secs=10)
                    if img_rel:
                        session.cover_image = img_rel
                        session.save(update_fields=['cover_image'])
            except Exception:
                # No bloquear el preview si falla la generación de la imagen
                pass

        resp = {
            'preview': generated,
            'source': provider_used,
            'fallback_used': did_fallback
        }
        if session and getattr(session, 'cover_image', ''):
            # Devolver URL absoluta vía endpoint proxy para evitar problemas de serving/static
            try:
                resp['cover_image'] = request.build_absolute_uri(f"/api/media/proxy/{session.cover_image}")
            except Exception:
                resp['cover_image'] = f"{settings.MEDIA_URL}{session.cover_image}"
        if debug:
            resp['debug'] = {
                'preferred': preferred,
                'errors': errors,
                'topic': topic, 'difficulty': difficulty, 'types': types, 'counts': counts,
                'moderation': moderation
            }
        response = JsonResponse(resp, status=200)
        response["X-LLM-Effective-Provider"] = provider_used
        response["X-LLM-Fallback"] = "1" if did_fallback else "0"
        return response


    except RuntimeError as e:
        if str(e) == "no_providers_available":
            return JsonResponse(
                {
                    "error": "no_providers_available",
                    "message": "No hay créditos disponibles en Perplexity ni en Gemini.",
                },
                status=503
            )
        # otros errores
        return JsonResponse(
            {"error": "providers_failed", "message": str(e)},
            status=500
        )



@api_view(['POST'])
def regenerate_question(request):
    """
    POST /api/regenerate/?debug=1
    body: { session_id: str, index: int, type?: "mcq"|"vf"|"short" }
    Usa session.latest_preview[index] como base (si existe) y genera una variante.
    Guarda log en RegenerationLog. Devuelve SOLO la nueva pregunta.
    """
    data = request.data
    debug = request.GET.get('debug') == '1'
    issues = []
    retry_used = False

    # Validaciones
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
    base_q = None
    if isinstance(session.latest_preview, list) and 0 <= index < len(session.latest_preview):
        base_q = session.latest_preview[index]
        qtype = qtype or base_q.get("type")

    qtype = qtype or "mcq"
    topic = session.topic
    difficulty = session.difficulty
    preferred = _header_provider(request)

    gemini_error = None
    try:
        # Anti-repetición con historial del índice
        seen = build_seen_set(session, index=index)

        def _is_dup(qobj):
            return _norm_for_cmp(qobj.get("question","")) in seen

        attempts = 0
        retry_used = False
        while True:
            attempts += 1
            new_q, provider_used, did_fallback, errors = _regenerate_with_fallback(
                topic, difficulty, qtype, base_q, seen, preferred
            )
            issues = review_question(new_q)
            sev = moderation_severity(issues)
            dup = _is_dup(new_q)

            if sev != "severe" and not dup:
                break

            seen.add(_norm_for_cmp(new_q.get("question","")))
            retry_used = True
            if attempts >= 3:
                if qtype == "mcq":
                    new_q = {
                        "type": "mcq",
                        "question": f"[{topic}] Variante ({difficulty}) — escenario alterno: elige la opción correcta.",
                        "options": ["A) Opción válida","B) Distractor","C) Distractor","D) Distractor"],
                        "answer": "A",
                        "explanation": "Variante segura tras múltiples intentos."
                    }
                elif qtype == "vf":
                    new_q = {
                        "type": "vf",
                        "question": f"En {topic}, el tiempo de ejecución asintótico se expresa con O grande.",
                        "answer": "Verdadero",
                        "explanation": "Enunciado claro y objetivo."
                    }
                else:
                    new_q = {
                        "type": "short",
                        "question": f"[{topic}] Define brevemente el concepto central.",
                        "answer": "Definición concisa.",
                        "explanation": "Variante segura."
                    }
                provider_used = "local_safe"
                did_fallback = True
                break

    except RuntimeError as e:
        if str(e) == "no_providers_available":
            return JsonResponse(
                {"error": "no_providers_available", "message": "Sin créditos en ambos proveedores."},
                status=503
            )
        gemini_error = str(e)
        # fallback local de emergencia:
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
                "explanation": "Variante local; reemplaza con LLM en producción."
            }
        else:
            new_q = {
                "type": "short",
                "question": f"[{topic}] Explica brevemente el concepto clave (variante {uid}).",
                "answer": "Respuesta esperada breve.",
                "explanation": "Variante local."
            }
        provider_used = "local_fallback"
        retry_used = True

    # Log de regeneración (igual)
    try:
        RegenerationLog.objects.create(
            session=session, index=index,
            old_question=base_q or {}, new_question=new_q
        )
    except Exception:
        pass

    resp = {
        "question": new_q,
        "source": provider_used
    }
    if debug:
        resp["debug"] = {
            "env_key_present": bool(os.getenv("GEMINI_API_KEY")) or bool(os.getenv("PPLX_API_KEY")),
            "gemini_error": gemini_error,
            "topic": topic, "difficulty": difficulty, "type": qtype,
            "base_available": base_q is not None,
            "moderation_issues": issues,
            "moderation_retry": retry_used,
        }
    response = JsonResponse(resp, status=200)
    response["X-LLM-Effective-Provider"] = provider_used
    response["X-LLM-Fallback"] = "1" if did_fallback else "0"
    return response




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
    while len(lp) <= index:
        lp.append({})
    lp[index] = new_q
    session.latest_preview = lp
    session.save(update_fields=["latest_preview"])

    return JsonResponse({"ok": True})


@api_view(['POST'])
def gemini_generate(request):
    prompt = request.data.get('prompt', '')
    try:
        genai = _configure_gemini()   # importa y configura aquí
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)
        return JsonResponse({'result': response.text})
    except RuntimeError as e:
        # genai_unavailable o falta de API key -> 503 para que Front distinga “servicio externo caído”
        return JsonResponse(
            {'error': 'genai_unavailable', 'message': str(e)},
            status=503
        )
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def generate_cover_image(prompt: str, size: int = 1024, timeout_secs: int = 10) -> str:
    """Genera una imagen con Gemini y devuelve la ruta relativa dentro de MEDIA_ROOT (ej: 'generated/image_x.png').
    Si falla o excede timeout, retorna None.
    """
    prompt = (prompt or '').strip()
    if not prompt:
        return None

    def _do_generate():
        genai = _configure_gemini()
        model_obj = genai.GenerativeModel('gemini-2.5-flash-image')
        # Ajustar prompt para tamaño y estilo educativo
        p = f"Genera una imagen ilustrativa de portada {size}x{size} para un cuestionario sobre: {prompt}. Estilo claro, educativo, colores brillantes, poco texto."
        resp = model_obj.generate_content(p)

        # Extraer inline data (robusto)
        candidates = getattr(resp, 'candidates', None) or []
        image_data = None
        if candidates:
            content = getattr(candidates[0], 'content', None)
            parts = getattr(content, 'parts', []) if content is not None else []
            for part in parts:
                inline = getattr(part, 'inline_data', None)
                if inline is None:
                    continue
                d = getattr(inline, 'data', None)
                if d:
                    image_data = d
                    break

        if not image_data:
            raise RuntimeError('no_inline_image_data_found')

        # Decodificar
        if isinstance(image_data, (bytes, bytearray)):
            image_bytes = bytes(image_data)
        else:
            s = str(image_data).strip()
            if s.startswith('data:') and ',' in s:
                s = s.split(',', 1)[1]
            image_bytes = base64.b64decode(s)

        # Detectar extensión
        ext = 'png'
        try:
            if image_bytes.startswith(b'\x89PNG'):
                ext = 'png'
            elif image_bytes.startswith(b'\xff\xd8\xff'):
                ext = 'jpg'
            elif image_bytes[:6] in (b'GIF87a', b'GIF89a'):
                ext = 'gif'
            else:
                if PILImage is not None:
                    try:
                        img = PILImage.open(io.BytesIO(image_bytes))
                        fmt = (getattr(img, 'format', None) or '').lower()
                        if fmt:
                            ext = 'jpg' if fmt == 'jpeg' else fmt
                    except Exception:
                        pass
        except Exception:
            ext = 'png'

        output_dir = os.path.join(settings.MEDIA_ROOT, 'generated')
        os.makedirs(output_dir, exist_ok=True)
        filename = f"image_{int(time.time())}.{ext}"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, 'wb') as fh:
            fh.write(image_bytes)

        # Retornar ruta relativa usando slashes '/' para que sea válida como URL
        return f"generated/{filename}"

    # Ejecutar con timeout usando ThreadPoolExecutor
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_do_generate)
            return fut.result(timeout=timeout_secs)
    except concurrent.futures.TimeoutError:
        return None
    except Exception:
        return None


def attach_images_to_questions(topic, image_counts, questions, session=None, request=None, size=512, timeout_secs=10):
    """Adjunta imágenes generadas a una lista de preguntas según image_counts.
    Añade `image_rel` (ruta relativa) y `image_url` (URL absoluta si se pasa `request`) a cada pregunta afectada.
    """
    if not image_counts or not isinstance(image_counts, dict):
        return
    # Iterar por cada tipo y generar hasta la cantidad requerida
    for qtype, required in image_counts.items():
        try:
            needed = int(required)
        except Exception:
            continue
        if needed <= 0:
            continue
        placed = 0
        for q in questions:
            if placed >= needed:
                break
            if q.get('type') != qtype:
                continue
            if q.get('image_rel'):
                continue
            # Construir prompt específico para que la imagen sea la base de la pregunta
            q_text = (q.get('question') or '').strip()
            prompt = (
                f"Genera una imagen educativa y clara para acompañar la siguiente pregunta de tema '{topic}': \"{q_text}\". "
                "La pregunta debe poder formularse sobre la imagen generada. Evita incluir texto dentro de la imagen. "
                "Estilo: ilustrativo, colores claros, aspecto didáctico, sin logos ni marcas."
            )
            try:
                filepath_rel = generate_cover_image(prompt, size=size, timeout_secs=timeout_secs)
            except Exception:
                filepath_rel = None
            if not filepath_rel:
                continue
            q['image_rel'] = filepath_rel
            if request:
                try:
                    q['image_url'] = request.build_absolute_uri(f"/api/media/proxy/{filepath_rel}")
                except Exception:
                    q['image_url'] = f"{settings.MEDIA_URL}{filepath_rel}"
            placed += 1
    return

@api_view(['POST'])
def gemini_generate_image(request):
    prompt = (request.data.get('prompt') or '').strip()
    # Optional session_id to persist generated image to a GenerationSession
    session_id = (request.data.get('session_id') or request.GET.get('session_id'))
    if not prompt:
        return JsonResponse({'error': 'prompt required'}, status=400)

    try:
        # Usar helper que encapsula la generación con timeout
        filepath_rel = generate_cover_image(prompt, size=1024, timeout_secs=10)
        if not filepath_rel:
            # fallback: devolver placeholder (si existe en MEDIA_ROOT/static o similar)
            placeholder = os.path.join(settings.MEDIA_ROOT, 'generated', 'placeholder.png')
            if os.path.exists(placeholder):
                fh = open(placeholder, 'rb')
                response = FileResponse(fh, content_type='image/png')
                response['Content-Length'] = str(os.path.getsize(placeholder))
                response['Content-Disposition'] = f'inline; filename="placeholder.png"'
                return response
            return JsonResponse({'error': 'image_generation_failed'}, status=500)

        # filepath_rel es algo como 'generated/image_123.png'
        fullpath = os.path.join(settings.MEDIA_ROOT, filepath_rel)
        ext = os.path.splitext(fullpath)[1].lstrip('.')
        ct = 'application/octet-stream'
        if ext in ('png', 'gif'):
            ct = f'image/{ext}'
        elif ext in ('jpg', 'jpeg'):
            ct = 'image/jpeg'
        elif ext != 'bin':
            ct = f'image/{ext}'

        # Si se proporcionó session_id, persistir la ruta relativa en la sesión (no sobrescribir)
        if session_id:
            try:
                ss = GenerationSession.objects.get(id=session_id)
                if not getattr(ss, 'cover_image', ''):
                    ss.cover_image = filepath_rel
                    ss.save(update_fields=['cover_image'])
            except Exception:
                # No bloquear la entrega de la imagen por fallo al persistir
                pass

        fh = open(fullpath, 'rb')
        response = FileResponse(fh, content_type=ct)
        response['Content-Length'] = str(os.path.getsize(fullpath))
        response['Content-Disposition'] = f'inline; filename="{os.path.basename(fullpath)}"'
        # Exponer la ruta relativa y la URL proxy en cabeceras para que el frontend sepa la ubicación
        try:
            proxy_url = request.build_absolute_uri(f"/api/media/proxy/{filepath_rel}")
            response['X-Cover-Image-Rel'] = filepath_rel
            response['X-Cover-Image-Url'] = proxy_url
        except Exception:
            pass
        return response
        

    except RuntimeError as e:
        # genai_unavailable or missing API key => 503 so frontend can treat as external service down
        return JsonResponse({'error': 'genai_unavailable', 'message': str(e)}, status=503)
    except Exception as e:
        return JsonResponse({'error': 'generate_failed', 'message': str(e)}, status=500)


def guardarLocal(resp):
    # Guardar respuesta completa (debug) en un archivo JSON dentro de MEDIA_ROOT/generated/debug
    try:
        dbg_dir = os.path.join(settings.MEDIA_ROOT, 'generated', 'debug')
        os.makedirs(dbg_dir, exist_ok=True)
        resp_file = os.path.join(dbg_dir, f"resp_{int(time.time())}.json")

        # Intentar obtener una representación serializable
        if hasattr(resp, "to_dict"):
            serial = resp.to_dict()
        else:
            serial = {}
            for attr in ("text", "candidates", "metadata"):
                if hasattr(resp, attr):
                    try:
                        serial[attr] = getattr(resp, attr)
                    except Exception:
                        serial[attr] = str(getattr(resp, attr))
            if not serial:
                serial = {"repr": repr(resp)}

        # Convertir elementos no serializables a strings
        def _make_jsonable(o):
            try:
                json.dumps(o)
                return o
            except Exception:
                return str(o)

        serial_clean = {k: _make_jsonable(v) for k, v in serial.items()}

        with open(resp_file, "w", encoding="utf-8") as fh:
            json.dump(serial_clean, fh, ensure_ascii=False, indent=2)

    except Exception:
        # No interrumpir el flujo por fallo en guardado de debug
        pass


@api_view(['POST'])
def update_session_preview(request, session_id):
    """Actualizar latest_preview de una GenerationSession existente.
    Body esperado: { latest_preview: [...], cover_image_rel?: 'generated/xxx.png' }
    No sobrescribe cover_image si ya existe en la sesión (comportamiento intencional).
    """
    try:
        session = GenerationSession.objects.get(id=session_id)
    except GenerationSession.DoesNotExist:
        return JsonResponse({'error': 'session not found'}, status=404)

    data = request.data
    latest = data.get('latest_preview')
    if latest is None:
        return JsonResponse({'error': 'latest_preview required'}, status=400)
    # Guardar latest_preview
    try:
        session.latest_preview = latest
        # Si se envió cover_image_rel y la sesión no tiene cover_image, persistirla
        cover_rel = data.get('cover_image_rel')
        if cover_rel and not getattr(session, 'cover_image', ''):
            session.cover_image = cover_rel
            session.save(update_fields=['latest_preview', 'cover_image'])
        else:
            session.save(update_fields=['latest_preview'])
    except Exception as e:
        return JsonResponse({'error': 'save_failed', 'message': str(e)}, status=500)

    resp = {
        'ok': True,
        'session_id': str(session.id),
        'cover_image': (request.build_absolute_uri(f"/api/media/proxy/{session.cover_image}") if getattr(session, 'cover_image', '') else '')
    }
    return JsonResponse(resp, status=200)