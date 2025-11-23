# api/views.py
import os
import json
import re
import uuid
import logging
import hashlib
from datetime import timedelta
from dotenv import load_dotenv
from django.http import JsonResponse, HttpResponse, FileResponse
from rest_framework.decorators import api_view
from rest_framework import status
from django.utils import timezone
import base64
import time
from typing import Optional, List, Dict, Any, Tuple, Union
import concurrent.futures
import mimetypes
from django.http import Http404
from sentry_sdk import capture_exception


from api.utils.gemini_keys import get_next_gemini_key, has_any_gemini_key

# Configurar logger
logger = logging.getLogger(__name__)


#import google.generativeai as genai
from .models import GenerationSession, RegenerationLog, ImagePromptCache, ImageGenerationLog

load_dotenv()

IMAGE_DAILY_LIMIT = 10


def _user_and_identifier(request):
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        return user, f"user:{user.id}"

    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR", "") or "").split(",")[0].strip()
    ip_addr = forwarded or request.META.get("REMOTE_ADDR", "unknown") or "unknown"
    return None, f"anon:{ip_addr}"


def _normalize_prompt(prompt: str) -> str:
    return " ".join((prompt or "").strip().lower().split())


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(_normalize_prompt(prompt).encode("utf-8")).hexdigest()


def _image_rate_limit_status(user_identifier: str, provider: Optional[str] = None) -> Dict[str, Any]:
    """
    Devuelve el uso diario por proveedor:
    - provider='gemini' -> solo imágenes generadas con Gemini
    - provider='openai' -> solo imágenes generadas con OpenAI
    - provider=None     -> todas (por si quieres ver el total)
    """
    now = timezone.now()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

    qs = ImageGenerationLog.objects.filter(
        user_identifier=user_identifier,
        created_at__gte=start_of_day,
        reused_from_cache=False,  # solo las que realmente consumen crédito
    )
    if provider:
        qs = qs.filter(provider__iexact=provider)

    used = qs.count()
    remaining = max(0, IMAGE_DAILY_LIMIT - used)

    return {
        "provider": (provider or "all").lower(),
        "used": used,
        "remaining": remaining,
    }



def _get_cached_image(user_identifier: str, prompt: str) -> Optional[ImagePromptCache]:
    prompt_hash = _prompt_hash(prompt)
    now = timezone.now()
    cached = (
        ImagePromptCache.objects.filter(
            user_identifier=user_identifier,
            prompt_hash=prompt_hash,
            expires_at__gte=now,
        )
        .order_by("-created_at")
        .first()
    )

    if not cached:
        return None

    fullpath = os.path.join(settings.MEDIA_ROOT, cached.image_path)
    if not os.path.exists(fullpath):
        return None
    return cached


def _save_cache_entry(user, user_identifier: str, prompt: str, image_path: str):
    prompt_hash = _prompt_hash(prompt)
    expires_at = timezone.now() + timedelta(hours=24)
    ImagePromptCache.objects.update_or_create(
        user_identifier=user_identifier,
        prompt_hash=prompt_hash,
        defaults={
            "user": user,
            "prompt": prompt,
            "image_path": image_path,
            "expires_at": expires_at,
        },
    )
    return expires_at


def _log_image_usage(
    *,
    user,
    user_identifier: str,
    prompt: str,
    provider: str,
    image_path: str,
    reused_from_cache: bool,
    estimated_cost_usd: Optional[float] = None,
):
    try:
        ImageGenerationLog.objects.create(
            user=user,
            user_identifier=user_identifier,
            prompt=prompt,
            provider=provider,
            image_path=image_path,
            reused_from_cache=reused_from_cache,
            estimated_cost_usd=estimated_cost_usd,
        )
    except Exception as e:  # noqa: PERF203 - mantener logging de auditoría
        logger.warning("[CoverImage] No se pudo registrar uso de imagen: %s", e)


def _build_image_response(
    filepath_rel: str,
    request,
    *,
    remaining: int,
    reused: bool = False,
    cache_expires=None,
    provider: Optional[str] = None,
):
    fullpath = os.path.join(settings.MEDIA_ROOT, filepath_rel)
    ext = os.path.splitext(fullpath)[1].lstrip('.')
    ct = 'application/octet-stream'
    if ext in ('png', 'gif'):
        ct = f'image/{ext}'
    elif ext in ('jpg', 'jpeg'):
        ct = 'image/jpeg'
    elif ext != 'bin':
        ct = f'image/{ext}'

    fh = open(fullpath, 'rb')
    response = FileResponse(fh, content_type=ct)
    response['Content-Length'] = str(os.path.getsize(fullpath))
    response['Content-Disposition'] = f'inline; filename="{os.path.basename(fullpath)}"'

    try:
        proxy_url = request.build_absolute_uri(f"/api/media/proxy/{filepath_rel}")
        response['X-Cover-Image-Rel'] = filepath_rel
        response['X-Cover-Image-Url'] = proxy_url
    except Exception:
        pass

    response['X-RateLimit-Limit'] = str(IMAGE_DAILY_LIMIT)
    response['X-RateLimit-Remaining'] = str(max(0, remaining))
    response['X-RateLimit-Provider'] = (provider or 'all').lower()
    response['X-Image-Reused'] = 'true' if reused else 'false'
    if cache_expires:
        response['X-Cache-Expires'] = cache_expires.isoformat()
    return response

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
    return JsonResponse({
        'status': 'ok',
        'message': 'Backend funcionando correctamente',
        'timestamp': timezone.now().isoformat(),
        'sentry_enabled': bool(os.getenv("SENTRY_DSN")),
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
        raise ValueError("Respuesta vacía del proveedor LLM")
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
    if not raw.lstrip().startswith("{"):
        m = re.search(r"\{.*\}", raw, flags=re.S)
        if not m:
            raise ValueError("No se encontró JSON en la respuesta")
        raw = m.group(0)
    return json.loads(raw)


def _call_with_retry(fn, attempts: int = 3, base_delay: float = 1.0):
    last_error = None
    delay = base_delay
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: PERF203 -- necesitamos capturar cualquier fallo de proveedor
            last_error = e
            if i == attempts - 1:
                break
            time.sleep(delay)
            delay *= 2
    if last_error:
        raise last_error
    raise RuntimeError("unknown_retry_failure")


def _normalize_difficulty(diff: str) -> str:
    d = (diff or "").strip().lower()
    if d.startswith("f"):
        return "Fácil"
    if d.startswith("m"):
        return "Media"
    return "Difícil"



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

def _get_genai():
    """
    Import tardío para evitar que Azure cargue primero /agents/python y rompa typing_extensions.
    Si falla la importación, elevamos un RuntimeError 'genai_unavailable' que se maneja como 503.
    """
    try:
        import google.generativeai as genai  # import perezoso (SDK antiguo para texto)
        return genai
    except Exception as e:
        raise RuntimeError(f"genai_unavailable: {e}")

def _get_genai_client():
    """
    Obtiene el cliente del nuevo SDK de Google GenAI para generación de imágenes.
    Soporta gemini-2.5-flash-image e Imagen 4 API.
    """
    try:
        from google import genai  # Nuevo SDK para imágenes
        api_key = get_next_gemini_key()
        client = genai.Client(api_key=api_key)
        return client
    except ImportError as e:
        logger.error(f"[CoverImage] Nuevo SDK google.genai no está instalado: {e}")
        logger.error("[CoverImage] Para instalar: pip install google-genai")
        raise RuntimeError(f"google_genai_sdk_not_installed: Necesitas instalar 'google-genai' package. Ejecuta: pip install google-genai")
    except Exception as e:
        logger.error(f"[CoverImage] Error al inicializar cliente GenAI: {e}")
        raise RuntimeError(f"genai_client_unavailable: {e}")


def _configure_openai():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("openai_api_key_missing: Configura OPENAI_API_KEY en el entorno")
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError(f"openai_sdk_not_installed: {e}")
    return OpenAI(api_key=api_key)


def _configure_gemini():
    api_key = get_next_gemini_key()
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


def _generate_cover_image_with_gemini(prompt: str, size: int) -> str:
    """
    Genera una imagen usando el nuevo SDK google.genai y el modelo
    gemini-2.5-flash-image, extrayendo correctamente los bytes de imagen.
    """
    client = _get_genai_client()
    logger.info(f"[CoverImage] Configurando Google GenAI Client para generar imagen con prompt: {prompt}")

    p = (
        f"Genera una imagen ilustrativa de portada {size}x{size} para un cuestionario sobre: {prompt}. "
        "Estilo claro, educativo, colores brillantes, poco texto."
    )

    model_candidates = [
        "gemini-2.5-flash-image",
    ]

    image_bytes: bytes | None = None
    last_error: Exception | None = None

    for model_name in model_candidates:
        try:
            logger.info(f"[CoverImage] Intentando generar imagen con modelo: {model_name}")
            response = client.models.generate_content(
                model=model_name,
                contents=[p],
            )

            # Guardar respuesta para debug en JSON (no rompe si falla)
            guardarLocal(response)

            # Estructura esperada:
            # response.candidates[0].content.parts[*].inline_data.data
            candidates = getattr(response, "candidates", None) or []
            if not candidates:
                raise ValueError("Respuesta de Gemini sin 'candidates'")

            for cand in candidates:
                content = getattr(cand, "content", None)
                if not content:
                    continue

                parts = getattr(content, "parts", None) or []
                for part in parts:
                    inline = getattr(part, "inline_data", None) or getattr(part, "inlineData", None)
                    if inline is not None and getattr(inline, "data", None) is not None:
                        data_field = inline.data
                        if isinstance(data_field, (bytes, bytearray)):
                            image_bytes = bytes(data_field)
                        else:
                            # por si viniera como string/base64
                            s = str(data_field).strip()
                            if s.startswith("data:") and "," in s:
                                s = s.split(",", 1)[1]
                            image_bytes = base64.b64decode(s)
                        break

                if image_bytes:
                    break

            if image_bytes:
                break
            else:
                last_error = RuntimeError(
                    "No se encontró inline_data.data con bytes de imagen en la respuesta de Gemini."
                )
                logger.warning(f"[CoverImage] {last_error}")

        except Exception as e:
            last_error = e
            logger.warning(f"[CoverImage] Modelo {model_name} falló: {str(e)}")
            continue

    if not image_bytes:
        error_msg = f"No se pudo generar imagen con ningún modelo. Último error: {last_error}"
        logger.error(f"[CoverImage] {error_msg}")
        raise RuntimeError(error_msg)

    # Guardar en disco y devolver ruta relativa (generated/xxx.png)
    return _store_image_bytes(image_bytes)

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


OPENAI_MODEL = "gpt-4o-mini"



def generate_questions_with_gemini(topic, difficulty, types, counts):
    genai = _configure_gemini()

    total = sum(int(counts.get(t, 0)) for t in types)
    if total <= 0:
        raise ValueError("total debe ser > 0 para generar preguntas")

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
    data = _extract_json(raw)

    if "questions" not in data or not isinstance(data["questions"], list):
        raise ValueError("Respuesta sin 'questions' válido (Gemini)")

    expected = total
    got = len(data["questions"])
    if got < expected:
        raise ValueError(f"(Gemini) Se esperaban {expected} preguntas y llegaron {got}")
    if got > expected:
        data["questions"] = data["questions"][:expected]

    return data["questions"]






def generate_questions_with_openai(topic, difficulty, types, counts):
    client = _configure_openai()

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

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.9,
    )

    content = (resp.choices[0].message.content or "").strip()
    data = _extract_json(content)

    if "questions" not in data or not isinstance(data["questions"], list):
        raise ValueError("Respuesta sin 'questions' válido")

    expected = total
    got = len(data["questions"])
    if got < expected:
        raise ValueError(f"Se esperaban {expected} preguntas y llegaron {got}")
    if got > expected:
        data["questions"] = data["questions"][:expected]

    return data["questions"]



def regenerate_question_with_openai(topic, difficulty, qtype, base_question=None, avoid_phrases=None):
    client = _configure_openai()

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

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.95,
    )

    content = (resp.choices[0].message.content or "").strip()
    data = _extract_json(content)

    # 🔴 FIX: si viene envuelto como {"questions": [ {...} ]}
    if isinstance(data, dict) and "questions" in data and isinstance(data["questions"], list) and data["questions"]:
        data = data["questions"][0]

    # Normalizar el tipo
    if data.get("type") != qtype:
        data["type"] = qtype

    # Normalización de opciones / respuesta para MCQ
    if qtype == "mcq":
        opts = data.get("options", [])

        # Si viene en formato raro, intentamos rescatar antes de tirar TODO
        if not isinstance(opts, list):
            # Por ejemplo, si vino un string con opciones separadas por comas
            if isinstance(opts, str):
                parts = [p.strip() for p in opts.split(",") if p.strip()]
                opts = parts
            else:
                opts = []

        # Asegurar 4 opciones como máximo
        if len(opts) > 4:
            opts = opts[:4]

        # Si hay menos de 4, rellenar con genéricos pero sin perder las reales
        while len(opts) < 4:
            opts.append(f"Opción {len(opts)+1}")

        data["options"] = opts

        # Normalizar answer
        ans = str(data.get("answer", "A")).strip().upper()[:1]
        if ans not in ("A", "B", "C", "D"):
            data["answer"] = "A"
        else:
            data["answer"] = ans

    elif qtype == "vf":
        ans = str(data.get("answer", "")).strip().capitalize()
        if ans not in ("Verdadero", "Falso"):
            data["answer"] = "Verdadero"

    return data





def _generate_with_fallback(topic, difficulty, types, counts, preferred: str):
    """
    Devuelve (questions, provider_used, fallback_used, errors_map).

    Respeta el proveedor preferido:
    - preferred='gemini' → prueba Gemini y luego OpenAI.
    - preferred='openai' → prueba OpenAI y luego Gemini.
    """
    errors: Dict[str, Dict[str, Any]] = {}
    order = _provider_order(preferred)

    for idx, provider in enumerate(order):
        fallback_used = idx > 0
        try:
            if provider == "gemini":
                qs = _call_with_retry(
                    lambda: generate_questions_with_gemini(topic, difficulty, types, counts),
                    attempts=3,
                )
            else:
                qs = _call_with_retry(
                    lambda: generate_questions_with_openai(topic, difficulty, types, counts),
                    attempts=3,
                )

            return qs, provider, fallback_used, errors

        except Exception as e:
            msg = str(e)
            errors[provider] = {
                "message": msg,
                "no_credits": _is_no_credits_msg(msg),
            }
            logger.error(f"[Questions] Error con {provider}: {msg}")
            continue

    if any(err.get("no_credits") for err in errors.values()):
        raise RuntimeError("no_providers_available")
    raise RuntimeError(f"providers_failed: {errors}")


def _regenerate_with_fallback(topic, difficulty, qtype, base_q, avoid_phrases, preferred: str):
    """
    Devuelve (question, provider_used, fallback_used, errors_map).
    """
    errors: Dict[str, Dict[str, Any]] = {}
    order = _provider_order(preferred)

    for idx, provider in enumerate(order):
        fallback_used = idx > 0
        try:
            if provider == "gemini":
                q = _call_with_retry(
                    lambda: regenerate_question_with_gemini(topic, difficulty, qtype, base_q, avoid_phrases),
                    attempts=3,
                )
            else:
                q = _call_with_retry(
                    lambda: regenerate_question_with_openai(topic, difficulty, qtype, base_q, avoid_phrases),
                    attempts=3,
                )

            return q, provider, fallback_used, errors

        except Exception as e:
            msg = str(e)
            errors[provider] = {
                "message": msg,
                "no_credits": _is_no_credits_msg(msg),
            }
            logger.error(f"[Regenerate] Error con {provider}: {msg}")
            continue

    if any(err.get("no_credits") for err in errors.values()):
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

ALLOWED_PROVIDERS = {"gemini", "openai"}


def _header_provider(request) -> str:
    """
    Lee el header X-LLM-Provider (openai|gemini) enviado por el frontend.
    Si viene algo inválido, cae a 'gemini'.
    """
    preferred = (
        request.headers.get("X-LLM-Provider")
        or request.META.get("HTTP_X_LLM_PROVIDER")
        or ""
    ).strip().lower()

    if preferred not in ALLOWED_PROVIDERS:
        preferred = "gemini"

    return preferred


def _provider_order(preferred: str) -> List[str]:
    preferred = (preferred or "").strip().lower()
    if preferred not in ALLOWED_PROVIDERS:
        preferred = "gemini"
    secondary = "openai" if preferred == "gemini" else "gemini"
    return [preferred, secondary]


def _is_no_credits_msg(msg: str) -> bool:
    m = (msg or "").lower()
    # heurística suficiente para 402/429/quotas/creditos
    return any(kw in m for kw in [
        "quota", "over quota", "insufficient", "billing", "payment required",
        "credit", "out of credits", "429", "402", "rate limit"
    ])



# =========================================================
# Endpoints
# =========================================================

@api_view(['POST'])
def sessions(request):
    data = request.data
    logger.info(f"[Sessions] Creando sesión con datos: topic={data.get('topic')}, difficulty={data.get('difficulty')}, types={data.get('types')}, counts={data.get('counts')}")
    
    topic = data.get('topic', '')
    difficulty = _normalize_difficulty(data.get('difficulty', ''))
    types = data.get('types', [])  # ["mcq","vf"]
    counts = data.get('counts', {})

    if not topic:
        logger.warning("[Sessions] Error: topic requerido pero no proporcionado")
        return JsonResponse({'error':'topic required'}, status=400)
    cat = find_category_for_topic(topic)
    if not cat:
        logger.warning(f"[Sessions] Error: topic '{topic}' fuera de dominio")
        return JsonResponse({
            'error':'topic fuera de dominio. Temas permitidos: ' + ', '.join(ALLOWED_TAXONOMY)
        }, status=400)

    valid_types = {'mcq','vf','short'}
    if not types:
        types = ['mcq','vf']
    for t in types:
        if t not in valid_types:
            logger.warning(f"[Sessions] Error: tipo '{t}' no permitido")
            return JsonResponse({'error':f'type {t} not allowed'}, status=400)

    total = 0
    for t in types:
        try:
            c = int(counts.get(t, 0))
        except:
            logger.warning(f"[Sessions] Error: count para '{t}' no es un entero")
            return JsonResponse({'error':f'count for {t} must be integer'}, status=400)
        if c < 0 or c > MAX_PER_TYPE:
            logger.warning(f"[Sessions] Error: count para '{t}' fuera de rango (0..{MAX_PER_TYPE})")
            return JsonResponse({'error':f'count for {t} must be 0..{MAX_PER_TYPE}'}, status=400)
        total += c

    if total == 0:
        logger.warning("[Sessions] Error: total de preguntas debe ser > 0")
        return JsonResponse({'error': 'total questions must be > 0'}, status=400)
    if total > MAX_TOTAL_QUESTIONS:
        logger.warning(f"[Sessions] Error: total de preguntas ({total}) excede máximo ({MAX_TOTAL_QUESTIONS})")
        return JsonResponse({'error': f'total questions ({total}) exceed max {MAX_TOTAL_QUESTIONS}'}, status=400)
    try:
        session = GenerationSession.objects.create(
            topic=topic,
            category=cat,
            difficulty=difficulty,
            types=types,
            counts=counts
        )
        logger.info(f"[Sessions] Sesión creada exitosamente: {session.id}")
    except Exception as e:
        logger.error(f"[Sessions] Error al crear sesión: {str(e)}", exc_info=True)
        capture_exception(e)
        return JsonResponse({'error': f'Error al crear sesión: {str(e)}'}, status=500)

    
    # Intentar generar portada asociada a la sesión (timeout corto)
        # Intentar generar portada asociada a la sesión (timeout corto)
    preferred = _header_provider(request)
    provider_used = preferred
    prompt_for_image = f"{topic} - {difficulty} quiz cover"

    try:
        logger.info(f"[Sessions] Intentando generar imagen de portada para sesión {session.id}")
        
        # ⬇️ importante: pedir también el proveedor realmente usado
        result = generate_cover_image(
            prompt_for_image,
            preferred_provider=preferred,
            size=1024,
            timeout_secs=10,
            return_provider=True,
        )

        if isinstance(result, tuple):
            img_rel, provider_used = result
        else:
            img_rel, provider_used = result, preferred

        if img_rel:
            session.cover_image = img_rel
            session.save(update_fields=['cover_image'])
            logger.info(f"[Sessions] Imagen de portada generada y guardada: {img_rel}")

            # 🔹 Registrar consumo de crédito en ImageGenerationLog
            user, user_identifier = _user_and_identifier(request)
            _log_image_usage(
                user=user,
                user_identifier=user_identifier,
                prompt=prompt_for_image,
                provider=provider_used or preferred,
                image_path=img_rel,
                reused_from_cache=False,
            )

            # 🔹 Recalcular estado de créditos usando el proveedor REAL
            img_status = _image_rate_limit_status(user_identifier, provider_used or preferred)
            image_rate_limit = {
                "provider": img_status.get("provider"),
                "used": img_status.get("used"),
                "remaining": img_status.get("remaining"),
                "limit": IMAGE_DAILY_LIMIT,
            }
        else:
            image_rate_limit = None

    except Exception as e:
        logger.warning(f"[Sessions] Error al generar imagen de portada (no crítico): {str(e)}")
        capture_exception(e)
        image_rate_limit = None

    # Construir cover_image como URL absoluta vía proxy (igual que en /preview/)
    if getattr(session, "cover_image", ""):
        try:
            cover_url = request.build_absolute_uri(f"/api/media/proxy/{session.cover_image}")
        except Exception:
            cover_url = f"{settings.MEDIA_URL}{session.cover_image}"
    else:
        cover_url = None

    resp = {
        "session_id": str(session.id),
        "topic": topic,
        "difficulty": difficulty,
        "cover_image": cover_url,
    }

    if image_rate_limit is not None:
        resp["image_rate_limit"] = image_rate_limit

    return JsonResponse(resp, status=201)

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

            # Si la sesión no tiene imagen de portada persistida, intentar generarla
            try:
                if not getattr(session, 'cover_image', ''):
                    logger.info(f"[CoverImage] Intentando generar imagen para sesión {session.id}, tema: {topic}")
                    prompt_for_image = f"{topic} - {difficulty} quiz cover"
                    img_rel = generate_cover_image(prompt_for_image, preferred_provider=preferred, size=1024, timeout_secs=10)
                    if img_rel:
                        session.cover_image = img_rel
                        session.save(update_fields=['cover_image'])
                        logger.info(f"[CoverImage] Imagen generada exitosamente: {img_rel}")
                    else:
                        logger.warning(f"[CoverImage] generate_cover_image retornó None para sesión {session.id}")
            except Exception as e:
                logger.error(f"[CoverImage] Error al generar imagen para sesión {session.id}: {str(e)}", exc_info=True)
                capture_exception(e)


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
            
            # Incluir información de regeneración
            resp['cover_regeneration_count'] = getattr(session, 'cover_regeneration_count', 0) or 0
            resp['cover_regeneration_remaining'] = max(0, 3 - (getattr(session, 'cover_regeneration_count', 0) or 0))
            
            # Incluir historial de imágenes
            history = getattr(session, 'cover_image_history', []) or []
            if not isinstance(history, list):
                history = []
            history_urls = []
            for img_path in history:
                try:
                    img_url = request.build_absolute_uri(f"/api/media/proxy/{img_path}")
                except Exception:
                    img_url = f"{settings.MEDIA_URL}{img_path}"
                history_urls.append({
                    'path': img_path,
                    'url': img_url
                })
            resp['cover_image_history'] = history_urls
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
            # esto también suele ser importante de monitorear
            capture_exception(e)
            return JsonResponse(
                {
                    "error": "no_providers_available",
                    "message": "No hay créditos disponibles en los proveedores configurados (Gemini/OpenAI).",
                },
                status=503
            )
        # otros errores
        capture_exception(e)
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
            capture_exception(e)
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
            "env_key_present": has_any_gemini_key(),
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
        capture_exception(e)
        return JsonResponse(
            {'error': 'genai_unavailable', 'message': str(e)},
            status=503
        )
    except Exception as e:
        capture_exception(e)
        return JsonResponse({'error': str(e)}, status=500)



def _store_image_bytes(image_bytes: bytes) -> str:
    if isinstance(image_bytes, (bytes, bytearray)):
        image_bytes = bytes(image_bytes)
    else:
        raise ValueError("image_bytes debe ser bytes")

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

    logger.info(f"[CoverImage] Imagen guardada exitosamente en {filepath}")
    return f"generated/{filename}"


def _generate_cover_image_with_openai(prompt: str, size: int) -> str:
    client = _configure_openai()
    logger.info("[CoverImage] Generando imagen con OpenAI")

    response = client.images.generate(
        model="dall-e-3",
        prompt=f"Genera una imagen {size}x{size} educativa y colorida para un quiz sobre: {prompt}.",
        size=f"{size}x{size}",
        response_format="b64_json",
    )

    if not response.data:
        raise RuntimeError("Respuesta vacía de OpenAI para imagen")
    image_b64 = response.data[0].b64_json
    image_bytes = base64.b64decode(image_b64)
    return _store_image_bytes(image_bytes)

def generate_cover_image(
    prompt: str,
    preferred_provider: str = "gemini",
    size: int = 1024,
    timeout_secs: int = 10,  # ahora mismo no lo usamos, pero lo dejamos en la firma
    return_provider: bool = False,
) -> Union[Optional[str], Tuple[Optional[str], Optional[str]]]:
    """
    Genera una imagen de portada y devuelve la ruta relativa dentro de MEDIA_ROOT
    (ej: 'generated/image_x.png').

    Respeta el proveedor preferido (Gemini ⇄ OpenAI) con fallback.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        logger.warning("[CoverImage] Prompt vacío, no se puede generar imagen")
        return None

    errors: Dict[str, str] = {}
    order = _provider_order(preferred_provider)

    for provider in order:
        try:
            if provider == "gemini":
                image_path = _generate_cover_image_with_gemini(prompt, size)
            else:
                image_path = _generate_cover_image_with_openai(prompt, size)

            if return_provider:
                return image_path, provider
            return image_path
        except Exception as e:
            msg = str(e)
            errors[provider] = msg
            logger.error(f"[CoverImage] Error con {provider}: {msg}")
            continue

    if any(_is_no_credits_msg(msg) for msg in errors.values()):
        raise RuntimeError("no_providers_available")

    raise RuntimeError(f"providers_failed: {errors}")

@api_view(['POST'])
def gemini_generate_image(request):
    prompt = (request.data.get('prompt') or '').strip()
    session_id = (request.data.get('session_id') or request.GET.get('session_id'))
    preferred = _header_provider(request)  # 'gemini' o 'openai'
    if not prompt:
        return JsonResponse({'error': 'prompt required'}, status=400)

    user, user_identifier = _user_and_identifier(request)
    cached = _get_cached_image(user_identifier, prompt)
    if cached:
        logger.info(f"[CoverImage] Devolviendo imagen cacheada para {user_identifier}")
        _log_image_usage(
            user=user,
            user_identifier=user_identifier,
            prompt=prompt,
            provider="cache",
            image_path=cached.image_path,
            reused_from_cache=True,
            estimated_cost_usd=0.0,
        )

        # ⚠️ importante: solo para info, no cuenta para el límite (reused_from_cache=True)
        status_info = _image_rate_limit_status(user_identifier, preferred)

        if session_id:
            try:
                ss = GenerationSession.objects.get(id=session_id)
                if not getattr(ss, 'cover_image', ''):
                    ss.cover_image = cached.image_path
                    ss.save(update_fields=['cover_image'])
            except Exception:
                pass

        response = _build_image_response(
            cached.image_path,
            request,
            remaining=status_info.get("remaining", IMAGE_DAILY_LIMIT),
            reused=True,
            cache_expires=cached.expires_at,
            provider=preferred,  # 👈 proveedor que está usando el frontend
        )
        return response

    # ⬇️ aquí, en vez de sin proveedor
    status_info = _image_rate_limit_status(user_identifier, preferred)
    if status_info['remaining'] <= 0:
        logger.warning(
            f"[CoverImage] Límite diario alcanzado para {user_identifier} con proveedor {preferred}: "
            f"{status_info['used']} / {IMAGE_DAILY_LIMIT}"
        )
        resp = JsonResponse({
            'error': 'rate_limit_exceeded',
            'message': f'Has alcanzado el límite diario de generación de imágenes ({IMAGE_DAILY_LIMIT}) para {preferred}. '
                       'Intenta mañana o reutiliza prompts recientes.'
        }, status=429)
        resp['X-RateLimit-Limit'] = str(IMAGE_DAILY_LIMIT)
        resp['X-RateLimit-Remaining'] = '0'
        resp['X-RateLimit-Provider'] = preferred
        return resp

    if status_info['remaining'] <= 2:
        logger.warning(
            f"[CoverImage] Advertencia: {user_identifier} cerca del límite de imágenes para {preferred}. "
            f"Restantes: {status_info['remaining']}"
        )

    try:
        result = generate_cover_image(
            prompt,
            preferred_provider=preferred,
            size=1024,
            timeout_secs=10,
            return_provider=True,
        )
        if isinstance(result, tuple):
            filepath_rel, provider_used = result
        else:
            filepath_rel, provider_used = result, preferred

        ...
        cache_expires = _save_cache_entry(user, user_identifier, prompt, filepath_rel)
        _log_image_usage(
            user=user,
            user_identifier=user_identifier,
            prompt=prompt,
            provider=provider_used or preferred,
            image_path=filepath_rel,
            reused_from_cache=False,
        )

        # 🔁 volver a calcular con el proveedor que realmente consumió créditos
        status_info = _image_rate_limit_status(user_identifier, provider_used or preferred)

        return _build_image_response(
            filepath_rel,
            request,
            remaining=status_info.get("remaining", IMAGE_DAILY_LIMIT),
            reused=False,
            cache_expires=cache_expires,
            provider=provider_used or preferred,
        )

    except RuntimeError as e:
        capture_exception(e)
        return JsonResponse({'error': 'genai_unavailable', 'message': str(e)}, status=503)
    except Exception as e:
        capture_exception(e)
        return JsonResponse({'error': 'generate_failed', 'message': str(e)}, status=500)



@api_view(['POST'])
def regenerate_cover_image(request, session_id):
    """
    Regenera la imagen de portada de una sesión.
    Límite: máximo 3 regeneraciones por sesión.
    Mantiene historial de últimas 3 imágenes para poder revertir.
    
    POST /api/sessions/<session_id>/regenerate-cover/
    """
    MAX_REGENERATIONS = 3
    
    try:
        session = GenerationSession.objects.get(id=session_id)
    except GenerationSession.DoesNotExist:
        return JsonResponse({'error': 'session_not_found'}, status=404)
    
    # Validar límite de regeneraciones
    current_count = getattr(session, 'cover_regeneration_count', 0) or 0
    if current_count >= MAX_REGENERATIONS:
        return JsonResponse({
            'error': 'regeneration_limit_reached',
            'message': f'Se ha alcanzado el límite de {MAX_REGENERATIONS} regeneraciones por sesión',
            'count': current_count,
            'max': MAX_REGENERATIONS
        }, status=400)

    user, user_identifier = _user_and_identifier(request)
    rate_status = _image_rate_limit_status(user_identifier)

    # Construir prompt basado en el tema y dificultad
    topic = session.topic or 'Quiz'
    difficulty = session.difficulty or 'Media'
    prompt_for_image = f"{topic} - {difficulty} quiz cover"
    preferred = _header_provider(request)

    cached = _get_cached_image(user_identifier, prompt_for_image)
    cache_expires = getattr(cached, "expires_at", None)
    provider_used = preferred
    reused = False

    if cached:
        new_image_path = cached.image_path
        reused = True
    else:
        if rate_status['remaining'] <= 0:
            return JsonResponse({
                'error': 'rate_limit_exceeded',
                'message': 'Has alcanzado el límite diario de generación de imágenes (10). Intenta mañana o reutiliza prompts recientes.'
            }, status=429)

        # Generar nueva imagen con timeout de 15 segundos
        result = generate_cover_image(
            prompt_for_image,
            preferred_provider=preferred,
            size=1024,
            timeout_secs=15,
            return_provider=True,
        )
        if isinstance(result, tuple):
            new_image_path, provider_used = result
        else:
            new_image_path, provider_used = result, preferred

    if not new_image_path:
        return JsonResponse({
            'error': 'image_generation_failed',
            'message': 'No se pudo generar la nueva imagen. Intenta de nuevo más tarde.'
        }, status=500)

    if not reused:
        cache_expires = _save_cache_entry(user, user_identifier, prompt_for_image, new_image_path)
        _log_image_usage(
            user=user,
            user_identifier=user_identifier,
            prompt=prompt_for_image,
            provider=provider_used or preferred,
            image_path=new_image_path,
            reused_from_cache=False,
        )
        rate_status = _image_rate_limit_status(user_identifier)
    else:
        _log_image_usage(
            user=user,
            user_identifier=user_identifier,
            prompt=prompt_for_image,
            provider="cache",
            image_path=new_image_path,
            reused_from_cache=True,
            estimated_cost_usd=0.0,
        )
    
    # Obtener historial actual (máximo 3 imágenes)
    history = getattr(session, 'cover_image_history', []) or []
    if not isinstance(history, list):
        history = []
    
    # Agregar imagen actual al historial (si existe) antes de actualizar
    current_image = getattr(session, 'cover_image', '') or ''
    if current_image:
        # Insertar al inicio (más reciente primero)
        history.insert(0, current_image)
        # Mantener solo las últimas 3
        history = history[:3]
    
    # Construir URL absoluta para la nueva imagen
    try:
        proxy_url = request.build_absolute_uri(f"/api/media/proxy/{new_image_path}")
    except Exception:
        proxy_url = f"{settings.MEDIA_URL}{new_image_path}"
    
    # Actualizar sesión
    session.cover_image = new_image_path
    session.cover_regeneration_count = current_count + 1
    session.cover_image_history = history
    session.save(update_fields=['cover_image', 'cover_regeneration_count', 'cover_image_history'])
    
    # Construir historial con URLs absolutas para el frontend
    history_urls = []
    for img_path in history:
        try:
            img_url = request.build_absolute_uri(f"/api/media/proxy/{img_path}")
        except Exception:
            img_url = f"{settings.MEDIA_URL}{img_path}"
        history_urls.append({
            'path': img_path,
            'url': img_url
        })
    
    return JsonResponse({
        'success': True,
        'image_url': proxy_url,
        'image_path': new_image_path,
        'count': session.cover_regeneration_count,
        'remaining': MAX_REGENERATIONS - session.cover_regeneration_count,
        'history': history_urls,
        'cache_reused': reused,
        'cache_expires_at': cache_expires.isoformat() if cache_expires else None,
        'rate_limit_remaining': rate_status.get('remaining'),
        'provider': provider_used,
    })


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
        capture_exception(e)
        return JsonResponse({'error': 'save_failed', 'message': str(e)}, status=500)


    resp = {
        'ok': True,
        'session_id': str(session.id),
        'cover_image': (request.build_absolute_uri(f"/api/media/proxy/{session.cover_image}") if getattr(session, 'cover_image', '') else '')
    }
    return JsonResponse(resp, status=200)