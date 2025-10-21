# api/services/voice_metrics.py
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from django.db.models import Avg, Count, Q
from ..models import VoiceMetricEvent

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    """
    Convierte un string de fecha 'YYYY-MM-DD' a datetime.
    Retorna None si la conversión falla o si s es None.
    """
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except Exception:
        return None


def _calculate_percentile(values_list: List[float], percentile: int) -> float:
    """
    Calcula el percentil especificado de una lista de valores.

    Args:
        values_list: Lista de valores numéricos
        percentile: Percentil a calcular (0-100)

    Returns:
        Valor del percentil calculado, o 0.0 si la lista está vacía
    """
    if not values_list:
        return 0.0

    if HAS_NUMPY:
        return float(np.percentile(values_list, percentile))

    # Implementación manual sin numpy
    sorted_values = sorted(values_list)
    n = len(sorted_values)

    if n == 1:
        return float(sorted_values[0])

    # Usar interpolación lineal
    position = (percentile / 100.0) * (n - 1)
    lower_index = int(position)
    upper_index = min(lower_index + 1, n - 1)

    if lower_index == upper_index:
        return float(sorted_values[lower_index])

    # Interpolación
    fraction = position - lower_index
    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]

    return float(lower_value + (upper_value - lower_value) * fraction)


def compute_voice_metrics(start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, Any]:
    """
    Calcula métricas agregadas de eventos de voz (STT/TTS).

    Args:
        start: Fecha de inicio en formato 'YYYY-MM-DD' (opcional)
        end: Fecha de fin en formato 'YYYY-MM-DD' (opcional)

    Returns:
        Diccionario con todas las métricas calculadas:
        - stt_latency_p50_ms: Percentil 50 de latencias STT
        - stt_latency_p95_ms: Percentil 95 de latencias STT
        - tts_latency_p50_ms: Percentil 50 de latencias TTS
        - tts_latency_p95_ms: Percentil 95 de latencias TTS
        - total_intents: Cantidad de intenciones reconocidas
        - intent_avg_confidence: Promedio de confianza en intenciones
        - intent_accuracy_rate: % de intenciones con confidence >= 0.8
        - fallback_count: Cantidad de fallbacks activados
        - fallback_rate: Ratio de fallback respecto a intenciones
        - barge_in_count: Cantidad de interrupciones
        - suggestions_shown: Cantidad de sugerencias mostradas
        - suggestions_accepted: Cantidad de sugerencias aceptadas
        - suggestion_accept_rate: Ratio de aceptación de sugerencias
        - backend_distribution: Distribución por backend utilizado
    """
    # Aplicar filtros de fecha
    qs = VoiceMetricEvent.objects.all()

    start_dt = _parse_date(start)
    end_dt = _parse_date(end)

    if start_dt:
        qs = qs.filter(timestamp__gte=start_dt)
    if end_dt:
        # Incluir todo el día fin
        qs = qs.filter(timestamp__lt=(end_dt + timedelta(days=1)))

    # --- STT Latencies ---
    stt_events = qs.filter(event_type='stt_final', latency_ms__isnull=False)
    stt_latencies = list(stt_events.values_list('latency_ms', flat=True))

    stt_latency_p50_ms = _calculate_percentile(stt_latencies, 50)
    stt_latency_p95_ms = _calculate_percentile(stt_latencies, 95)

    # --- TTS Latencies ---
    tts_events = qs.filter(event_type='tts_complete', latency_ms__isnull=False)
    tts_latencies = list(tts_events.values_list('latency_ms', flat=True))

    tts_latency_p50_ms = _calculate_percentile(tts_latencies, 50)
    tts_latency_p95_ms = _calculate_percentile(tts_latencies, 95)

    # --- Intent Metrics ---
    intent_events = qs.filter(event_type='intent_recognized')
    total_intents = intent_events.count()

    # Promedio de confianza en intenciones
    intent_stats = intent_events.filter(confidence__isnull=False).aggregate(
        avg_confidence=Avg('confidence')
    )
    intent_avg_confidence = round(intent_stats['avg_confidence'] or 0.0, 4)

    # Accuracy rate (confidence >= 0.8)
    high_confidence_count = intent_events.filter(confidence__gte=0.8).count()
    intent_accuracy_rate = 0.0
    if total_intents > 0:
        intent_accuracy_rate = round(high_confidence_count / total_intents, 4)

    # --- Fallback Metrics ---
    fallback_count = qs.filter(event_type='fallback_triggered').count()
    fallback_rate = 0.0
    if total_intents > 0:
        fallback_rate = round(fallback_count / total_intents, 4)

    # --- Barge-in ---
    barge_in_count = qs.filter(event_type='barge_in').count()

    # --- Suggestion Metrics ---
    suggestions_shown = qs.filter(event_type='suggestion_shown').count()
    suggestions_accepted = qs.filter(event_type='suggestion_accepted').count()

    suggestion_accept_rate = 0.0
    if suggestions_shown > 0:
        suggestion_accept_rate = round(suggestions_accepted / suggestions_shown, 4)

    # --- Backend Distribution ---
    backend_events = qs.filter(backend_used__isnull=False)
    backend_distribution = {}

    for backend_name in backend_events.values_list('backend_used', flat=True).distinct():
        count = backend_events.filter(backend_used=backend_name).count()
        backend_distribution[backend_name] = count

    # Construir diccionario de métricas
    metrics = {
        "stt_latency_p50_ms": round(stt_latency_p50_ms, 2),
        "stt_latency_p95_ms": round(stt_latency_p95_ms, 2),
        "tts_latency_p50_ms": round(tts_latency_p50_ms, 2),
        "tts_latency_p95_ms": round(tts_latency_p95_ms, 2),
        "total_intents": total_intents,
        "intent_avg_confidence": intent_avg_confidence,
        "intent_accuracy_rate": intent_accuracy_rate,
        "fallback_count": fallback_count,
        "fallback_rate": fallback_rate,
        "barge_in_count": barge_in_count,
        "suggestions_shown": suggestions_shown,
        "suggestions_accepted": suggestions_accepted,
        "suggestion_accept_rate": suggestion_accept_rate,
        "backend_distribution": backend_distribution,
        "filters": {
            "start": start,
            "end": end,
            "date_filter_applied": start_dt is not None or end_dt is not None,
        }
    }

    return metrics


def build_voice_metrics_csv(metrics: Dict[str, Any]) -> str:
    """
    Convierte un diccionario de métricas de voz a formato CSV.

    Args:
        metrics: Diccionario con métricas de voz

    Returns:
        String en formato CSV con cabecera "metric,value"
    """
    lines = []

    def add(key: str, value: Any) -> None:
        """Añade una línea al CSV"""
        lines.append(f"{key},{value}")

    # Métricas de latencia
    add("stt_latency_p50_ms", metrics.get("stt_latency_p50_ms", 0))
    add("stt_latency_p95_ms", metrics.get("stt_latency_p95_ms", 0))
    add("tts_latency_p50_ms", metrics.get("tts_latency_p50_ms", 0))
    add("tts_latency_p95_ms", metrics.get("tts_latency_p95_ms", 0))

    # Métricas de intención
    add("total_intents", metrics.get("total_intents", 0))
    add("intent_avg_confidence", metrics.get("intent_avg_confidence", 0))
    add("intent_accuracy_rate", metrics.get("intent_accuracy_rate", 0))

    # Métricas de fallback
    add("fallback_count", metrics.get("fallback_count", 0))
    add("fallback_rate", metrics.get("fallback_rate", 0))

    # Métricas de interacción
    add("barge_in_count", metrics.get("barge_in_count", 0))
    add("suggestions_shown", metrics.get("suggestions_shown", 0))
    add("suggestions_accepted", metrics.get("suggestions_accepted", 0))
    add("suggestion_accept_rate", metrics.get("suggestion_accept_rate", 0))

    # Distribución por backend
    backend_dist = metrics.get("backend_distribution", {})
    for backend_name, count in backend_dist.items():
        add(f"backend_distribution.{backend_name}", count)

    # Filtros aplicados
    filters = metrics.get("filters", {})
    add("filters.start", filters.get("start") or "")
    add("filters.end", filters.get("end") or "")
    add("filters.date_filter_applied", filters.get("date_filter_applied", False))

    return "metric,value\n" + "\n".join(lines) + "\n"
