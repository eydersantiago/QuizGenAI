# api/views.py
import json
import logging
import os
import re
import time
import uuid
from dotenv import load_dotenv
from django.http import JsonResponse
from rest_framework.decorators import api_view
from rest_framework import status
from django.utils import timezone
import requests  # <— NUEVO

logger = logging.getLogger(__name__)


#import google.generativeai as genai
from .models import GenerationSession, RegenerationLog

load_dotenv()

# =========================================================
# Endpoint de salud para diagnóstico
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
def providers_health(request):
    """Verifica configuración de proveedores IA y fallback local."""

    def _status(name: str, env_keys=None, optional=False):
        env_keys = env_keys or []
        missing = [k for k in env_keys if not os.getenv(k)]
        if missing and not optional:
            return {"name": name, "status": "degraded", "missing_env": missing}
        if missing and optional:
            return {"name": name, "status": "skipped", "missing_env": missing}
        return {"name": name, "status": "ok"}

    providers = [
        _status("gemini", ["GEMINI_API_KEY"]),
        _status("perplexity", ["PPLX_API_KEY"]),
        _status(SECONDARY_PROVIDER, [], optional=True) | {"notes": "placeholder listo"},
    ]

    return JsonResponse({
        "status": "ok",
        "providers": providers,
        "retry_strategy": {"attempts": 2, "mode": "exponential_backoff"},
        "timestamp": timezone.now().isoformat(),
    })

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


def _retry_with_backoff(fn, *args, attempts: int = 2, base_delay: float = 0.75, **kwargs):
    """Ejecuta `fn` con reintentos exponenciales simples.

    Intenta `attempts` veces (por defecto 2). El tiempo de espera usa backoff
    exponencial: base_delay, base_delay*2, etc.
    """
    last_exc = None
    for idx in range(attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 (registramos y propagamos)
            last_exc = exc
            if idx >= attempts - 1:
                break
            delay = base_delay * (2 ** idx)
            logger.warning(
                "Intento %s/%s falló (%s). Reintentando en %.2fs",
                idx + 1,
                attempts,
                exc,
                delay,
            )
            time.sleep(delay)
    if last_exc:
        raise last_exc


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
    def _do_call():
        r = requests.post(PPLX_API, headers=headers, json=body, timeout=60)
        if r.status_code != 200:
            # propagar texto de error, útil para detectar 'no credits'
            raise RuntimeError(f"pplx_http_{r.status_code}: {r.text}")

        data = r.json()
        try:
            return data["choices"][0]["message"]["content"]
        except Exception:
            raise RuntimeError("pplx_invalid_response")

    return _retry_with_backoff(_do_call)



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


def _gemini_generate_with_retry(model, prompt: str) -> str:
    return _retry_with_backoff(
        lambda: (model.generate_content(prompt).text or "").strip()
    )

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
    raw = _gemini_generate_with_retry(model, prompt)
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
    raw = _gemini_generate_with_retry(model, prompt)
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


SECONDARY_PROVIDER = "stability_placeholder"


def _build_placeholder_question(topic: str, difficulty: str, qtype: str, index: int) -> dict:
    base_question = (
        "¿Cuál es el propósito principal de un bloque try/except en Python?"
        if qtype == "mcq"
        else "Explica brevemente qué es la complejidad temporal Big-O."
    )
    if qtype == "vf":
        base_question = "Las listas en Python son inmutables."

    if qtype == "mcq":
        return {
            "type": "mcq",
            "question": f"[{difficulty}] {base_question} ({topic}) #{index}",
            "options": [
                "A) Manejar errores durante la ejecución",
                "B) Declarar variables globales",
                "C) Optimizar el uso de memoria",
                "D) Ejecutar código asíncrono",
            ],
            "answer": "A",
            "explanation": "Los bloques try/except permiten capturar excepciones y evitar fallos abruptos.",
        }
    if qtype == "vf":
        return {
            "type": "vf",
            "question": f"[{difficulty}] {base_question} ({topic}) #{index}",
            "answer": "Falso",
            "explanation": "Las listas son mutables; las tuplas son las estructuras inmutables estándar.",
        }
    return {
        "type": "short",
        "question": f"[{difficulty}] {base_question} ({topic}) #{index}",
        "answer": "Medida del crecimiento del tiempo de ejecución en función del tamaño de entrada.",
        "explanation": "Big-O describe cómo escalan los algoritmos; es un indicador asintótico.",
    }


def generate_questions_with_secondary(topic, difficulty, types, counts):
    logger.info("Usando proveedor secundario %s", SECONDARY_PROVIDER)
    questions = []
    for qtype in types:
        total = int(counts.get(qtype, 0))
        for idx in range(1, total + 1):
            questions.append(_build_placeholder_question(topic, difficulty, qtype, idx))
    return questions


def regenerate_question_with_secondary(topic, difficulty, qtype, base_question=None, avoid_phrases=None):
    logger.info("Regenerando con proveedor secundario %s", SECONDARY_PROVIDER)
    return _build_placeholder_question(topic, difficulty, qtype, 1)



def _generate_with_fallback(topic, difficulty, types, counts, preferred: str):
    """
    Devuelve (questions, provider_used, fallback_used, errors_map)
    Si ambos fallan por créditos -> levanta RuntimeError('no_providers_available')
    """
    order = [preferred, "gemini" if preferred == "perplexity" else "perplexity", SECONDARY_PROVIDER]
    errors = {}
    fallback_used = False

    for i, prov in enumerate(order):
        try:
            if prov == "gemini":
                qs = generate_questions_with_gemini(topic, difficulty, types, counts)
            elif prov == "perplexity":
                qs = generate_questions_with_pplx(topic, difficulty, types, counts)
            else:
                qs = generate_questions_with_secondary(topic, difficulty, types, counts)
            return qs, prov, fallback_used or i > 0, errors
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
    order = [preferred, "gemini" if preferred == "perplexity" else "perplexity", SECONDARY_PROVIDER]
    errors = {}
    fallback_used = False

    for i, prov in enumerate(order):
        try:
            if prov == "gemini":
                q = regenerate_question_with_gemini(topic, difficulty, qtype, base_q, avoid_phrases)
            elif prov == "perplexity":
                q = regenerate_question_with_pplx(topic, difficulty, qtype, base_q, avoid_phrases)
            else:
                q = regenerate_question_with_secondary(topic, difficulty, qtype, base_q, avoid_phrases)
            return q, prov, fallback_used or i > 0, errors
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
            session.latest_preview = generated
            session.save(update_fields=["latest_preview"])

        resp = {
            'preview': generated,
            'source': provider_used,
            'fallback_used': did_fallback
        }
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
