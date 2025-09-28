# api/services/metrics.py
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Dict, Any, Iterable, Tuple, Optional

from django.db.models import QuerySet
from ..models import GenerationSession, RegenerationLog


def _has_created_at(model_cls) -> bool:
    try:
        model_cls._meta.get_field("created_at")
        return True
    except Exception:
        return False


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # YYYY-MM-DD
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except Exception:
        return None


def _apply_date_range(qs: QuerySet, start: Optional[str], end: Optional[str]) -> QuerySet:
    if not _has_created_at(qs.model):
        # El modelo no tiene created_at → retornar sin filtro para no romper
        return qs
    start_dt = _parse_date(start)
    end_dt = _parse_date(end)
    if start_dt:
        qs = qs.filter(created_at__gte=start_dt)
    if end_dt:
        # incluir todo el día fin
        qs = qs.filter(created_at__lt=(end_dt + timedelta(days=1)))
    return qs


def _count_questions_from_sessions(sessions: Iterable[GenerationSession]) -> int:
    total = 0
    for s in sessions:
        try:
            if isinstance(s.latest_preview, list):
                total += len(s.latest_preview)
            else:
                # Fallback: suma por configuración counts si existe
                if isinstance(s.counts, dict):
                    total += sum(int(v or 0) for v in s.counts.values())
        except Exception:
            pass
    return total


def _distribution_by_difficulty(sessions: Iterable[GenerationSession]) -> Dict[str, int]:
    c = Counter()
    for s in sessions:
        diff = (s.difficulty or "").strip() or "N/D"
        c[diff] += 1
    return dict(c)


def _distribution_by_type_counts(sessions: Iterable[GenerationSession]) -> Dict[str, int]:
    """
    Suma las cantidades configuradas por tipo (counts) a lo largo de las sesiones.
    """
    c = Counter()
    for s in sessions:
        try:
            counts = s.counts or {}
            for t, n in counts.items():
                c[str(t)] += int(n or 0)
        except Exception:
            pass
    return dict(c)


def compute_metrics(start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, Any]:
    """
    Retorna un diccionario con:
      - total_sessions
      - total_questions_generated
      - total_regenerations
      - regeneration_rate
      - distribution: { difficulty: {...}, type: {...} }
    Admite filtros de fecha (YYYY-MM-DD) si los modelos tienen created_at.
    """
    sessions_qs = _apply_date_range(GenerationSession.objects.all(), start, end)
    regens_qs = _apply_date_range(RegenerationLog.objects.all(), start, end)

    sessions_list = list(sessions_qs)
    total_sessions = len(sessions_list)
    total_questions_generated = _count_questions_from_sessions(sessions_list)
    total_regenerations = regens_qs.count()

    regeneration_rate = 0.0
    denom = total_questions_generated if total_questions_generated > 0 else 1
    regeneration_rate = round(total_regenerations / denom, 4)

    metrics = {
        "total_sessions": total_sessions,
        "total_questions_generated": total_questions_generated,
        "total_regenerations": total_regenerations,
        "regeneration_rate": regeneration_rate,
        "distribution": {
            "difficulty": _distribution_by_difficulty(sessions_list),
            "type": _distribution_by_type_counts(sessions_list),
        },
        "filters": {
            "start": start,
            "end": end,
            "date_filter_applied": _has_created_at(GenerationSession) and _has_created_at(RegenerationLog),
        }
    }
    return metrics


def build_metrics_csv(metrics: Dict[str, Any]) -> str:
    """
    Construye un CSV simple a partir del diccionario de métricas.
    Formato:
      - Cabecera MÉTRICA,VALOR
      - Distribuciones se expanden en filas: distribution.difficulty.<clave>,<valor>
    """
    lines = []
    def add(k, v):
        lines.append(f"{k},{v}")

    add("total_sessions", metrics.get("total_sessions", 0))
    add("total_questions_generated", metrics.get("total_questions_generated", 0))
    add("total_regenerations", metrics.get("total_regenerations", 0))
    add("regeneration_rate", metrics.get("regeneration_rate", 0))

    dist = metrics.get("distribution", {})
    for k, m in dist.get("difficulty", {}).items():
        add(f"distribution.difficulty.{k}", m)
    for k, m in dist.get("type", {}).items():
        add(f"distribution.type.{k}", m)

    filters = metrics.get("filters", {})
    add("filters.start", filters.get("start") or "")
    add("filters.end", filters.get("end") or "")
    add("filters.date_filter_applied", filters.get("date_filter_applied"))

    return "metric,value\n" + "\n".join(lines) + "\n"
