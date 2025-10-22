# api/views_intent_router.py
import re
import time
from typing import Dict, Any, List
from django.http import JsonResponse
from rest_framework.decorators import api_view
from rest_framework import status

from .models import VoiceMetricEvent  # ya lo tienes
# Si prefieres registrar métricas vía endpoint en vez de ORM directo,
# podrías usar requests.post(...) a /api/voice-metrics/log/, pero con ORM es más simple.

# --- catálogo simple de intents soportados ---
SUPPORTED_INTENTS: Dict[str, Dict[str, Any]] = {
    "navigate_next": {
        "description": "Ir a la siguiente pregunta",
        "slots": [],
        "examples": ["siguiente", "continúa", "avanza", "next"],
    },
    "navigate_previous": {
        "description": "Ir a la pregunta anterior",
        "slots": [],
        "examples": ["anterior", "atrás", "volver", "back"],
    },
    "generate_quiz": {
        "description": "Generar un nuevo cuestionario",
        "slots": ["topic", "difficulty"],
        "examples": ["genera un quiz de redes", "crear cuestionario de álgebra fácil"],
    },
    "read_question": {
        "description": "Leer la pregunta actual",
        "slots": [],
        "examples": ["lee la pregunta", "leer en voz alta"],
    },
    "show_answers": {
        "description": "Mostrar opciones de respuesta",
        "slots": [],
        "examples": ["muestra las respuestas", "ver opciones"],
    },
    "repeat": {
        "description": "Repetir la última acción o lectura",
        "slots": [],
        "examples": ["repite", "de nuevo", "otra vez"],
    },
    "pause": {
        "description": "Pausar lectura/acción",
        "slots": [],
        "examples": ["pausa", "detener"],
    },
    "resume": {
        "description": "Reanudar lectura/acción",
        "slots": [],
        "examples": ["continúa", "reanudar"],
    },
    "skip": {
        "description": "Saltar pregunta",
        "slots": [],
        "examples": ["saltar", "omitir"],
    },
    "finish": {
        "description": "Finalizar el quiz",
        "slots": [],
        "examples": ["terminar", "finalizar", "salir"],
    },
    "slower": {
        "description": "Leer más despacio",
        "slots": [],
        "examples": ["más despacio", "lento"],
    },
}

# patrones locales (fallback "grammar")
_PATTERNS = [
    ("navigate_next", re.compile(r"\b(siguiente|próxima?|continua?r?|adelante|next|avanza|sigue)\b", re.I)),
    ("navigate_previous", re.compile(r"\b(anterior|atrás|volver|back)\b", re.I)),
    ("generate_quiz", re.compile(r"\b(genera?r?|crea?r?|arma|haz|hazme|quiz|cuestionario|test)\b", re.I)),
    ("read_question", re.compile(r"\b(lee?r?|pregunta)\b", re.I)),
    ("show_answers", re.compile(r"\b(muestra?r?|mostrar|ver|respuestas?|opciones)\b", re.I)),
    ("repeat", re.compile(r"\b(repite?r?|otra\s+vez|de\s+nuevo)\b", re.I)),
    ("pause", re.compile(r"\b(pausa?r?|detene?r?|stop)\b", re.I)),
    ("resume", re.compile(r"\b(continua?r?|reanuda?r?|resume)\b", re.I)),
    ("skip", re.compile(r"\b(salta?r?|omitir|skip)\b", re.I)),
    ("finish", re.compile(r"\b(terminar|finalizar|salir|finish)\b", re.I)),
    ("slower", re.compile(r"\b(lento|despacio|slower)\b", re.I)),
]


def _match_intent(text: str) -> Dict[str, Any]:
    """Router local tipo 'grammar' con latencia simulada y slots vacíos."""
    t0 = time.perf_counter()
    text_norm = (text or "").strip()

    intent = "unknown"
    confidence = 0.0
    slots: Dict[str, Any] = {}

    for name, pattern in _PATTERNS:
        if pattern.search(text_norm):
            intent = name
            confidence = 0.6  # heurística
            break

    latency_ms = int((time.perf_counter() - t0) * 1000)

    return {
        "intent": intent,
        "confidence": confidence,
        "slots": slots,
        "backend_used": "grammar",
        "latency_ms": latency_ms,
        "warning": None if intent != "unknown" else "Intent not recognized (local grammar)",
    }


def _log_intent_event(result: Dict[str, Any], request) -> None:
    """Registra evento de intención en VoiceMetricEvent."""
    try:
        VoiceMetricEvent.objects.create(
            event_type="intent_recognized",
            session_id=request.data.get("session_id") or request.GET.get("session_id"),
            user=request.user if request.user.is_authenticated else None,
            latency_ms=result.get("latency_ms"),
            confidence=result.get("confidence"),
            intent=result.get("intent"),
            backend_used=result.get("backend_used") or "grammar",
            text_length=len((request.data.get("text") or "").strip()),
            metadata={"source": "intent-router", "warning": result.get("warning")},
        )
    except Exception:
        # No interrumpir la respuesta si fallan las métricas
        pass


@api_view(["GET"])
def intent_health(request):
    """GET /api/intent-router/health/"""
    # Aquí podrías chequear backends reales (Gemini, Perplexity, etc.)
    data = {
        "status": "ok",
        "backends": {
            "grammar": "ok",
            "gemini": "disabled",
            "perplexity": "disabled",
        },
    }
    return JsonResponse(data, status=status.HTTP_200_OK)


@api_view(["GET"])
def supported_intents(request):
    """GET /api/intent-router/supported_intents/"""
    return JsonResponse(
        {
            "total_intents": len(SUPPORTED_INTENTS),
            "intents": SUPPORTED_INTENTS,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
def parse_intent(request):
    """POST /api/intent-router/parse/  Body: {text, session_id?}"""
    text = (request.data.get("text") or "").strip()
    if not text:
        return JsonResponse({"error": "text is required"}, status=status.HTTP_400_BAD_REQUEST)

    result = _match_intent(text)
    _log_intent_event(result, request)

    return JsonResponse(
        {
            "intent": result["intent"],
            "confidence": result["confidence"],
            "slots": result["slots"],
            "backend_used": result["backend_used"],
            "latency_ms": result["latency_ms"],
            "warning": result["warning"],
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
def batch_parse_intents(request):
    """POST /api/intent-router/batch_parse/  Body: {texts: []}"""
    texts: List[str] = request.data.get("texts") or []
    if not isinstance(texts, list) or len(texts) == 0:
        return JsonResponse({"results": []}, status=status.HTTP_200_OK)

    results = []
    for t in texts:
        r = _match_intent(t or "")
        results.append(
            {
                "text": t,
                "intent": r["intent"],
                "confidence": r["confidence"],
                "slots": r["slots"],
                "backend_used": r["backend_used"],
                "latency_ms": r["latency_ms"],
            }
        )
    # Opcional: registrar un evento resumido
    try:
        VoiceMetricEvent.objects.create(
            event_type="intent_batch",
            metadata={"count": len(texts)},
            backend_used="grammar",
        )
    except Exception:
        pass

    return JsonResponse({"results": results}, status=status.HTTP_200_OK)
