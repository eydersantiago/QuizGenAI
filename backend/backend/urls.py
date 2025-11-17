from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.conf import settings
from django.conf.urls.static import static

def root_health(_request):
    return JsonResponse({"status": "ok"})

urlpatterns = [
    path("", root_health, name="root_health"),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),  # <--- muy importante
]

# Servir media en DEBUG (archivos subidos / generados)
import sys

# Servir media en desarrollo: cuando DEBUG=True o si estamos ejecutando el servidor
# de desarrollo (`manage.py runserver`). Esto facilita probar imágenes generadas
# localmente sin requerir un servidor de archivos externo.
if settings.DEBUG or any(arg.endswith('runserver') for arg in sys.argv):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
