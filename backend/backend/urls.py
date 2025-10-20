from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

def root_health(_request):
    return JsonResponse({"status": "ok"})

urlpatterns = [
    path("", root_health, name="root_health"),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),  # <--- muy importante
]
