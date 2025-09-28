# api/views_metrics.py
from django.http import JsonResponse, HttpResponse
from rest_framework.decorators import api_view

from .services.metrics import compute_metrics, build_metrics_csv


@api_view(["GET"])
def metrics_summary(request):
    """
    GET /api/metrics/?start=YYYY-MM-DD&end=YYYY-MM-DD
    Devuelve JSON con métricas agregadas (HU-11).
    """
    start = request.GET.get("start")
    end = request.GET.get("end")
    metrics = compute_metrics(start=start, end=end)
    return JsonResponse(metrics, status=200)


@api_view(["GET"])
def metrics_export(request):
    """
    GET /api/metrics/export/?start=YYYY-MM-DD&end=YYYY-MM-DD
    Devuelve CSV con métricas agregadas (HU-11).
    """
    start = request.GET.get("start")
    end = request.GET.get("end")
    metrics = compute_metrics(start=start, end=end)
    csv_text = build_metrics_csv(metrics)

    resp = HttpResponse(csv_text, content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="qgai_metrics.csv"'
    return resp
