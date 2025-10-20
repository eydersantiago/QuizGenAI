# backend/wsgi.py
import os

# --- SHIM de compatibilidad para Azure: añade typing_extensions.Sentinel si falta ---
try:
    import typing_extensions as _te  # puede venir del agente de Azure (/agents/python)
    if not hasattr(_te, "Sentinel"):
        class _SentinelType:
            __slots__ = ("_name",)
            def __init__(self, name): self._name = name
            def __repr__(self): return self._name

        def Sentinel(name: str, *, module: str | None = None,
                     qualname: str | None = None, repr: str | None = None):
            inst = _SentinelType(repr or name)
            if module:   setattr(inst, "__module__", module)
            if qualname: setattr(inst, "__qualname__", qualname)
            return inst

        _te.Sentinel = Sentinel
except Exception:
    # si algo falla aquí, no empeoramos: Django seguirá mostrando el error original
    pass
# --- fin SHIM ---

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
