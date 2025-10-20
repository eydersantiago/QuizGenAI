# sitecustomize.py
# Shim para añadir typing_extensions.Sentinel si falta (Azure App Service).
try:
    import typing_extensions as _te
    if not hasattr(_te, "Sentinel"):
        class _SentinelType:
            __slots__ = ("_name",)
            def __init__(self, name): self._name = name
            def __repr__(self): return self._name
        def Sentinel(name: str, *, module: str | None = None,
                     qualname: str | None = None, repr: str | None = None):
            obj = _SentinelType(repr or name)
            if module:   setattr(obj, "__module__", module)
            if qualname: setattr(obj, "__qualname__", qualname)
            return obj
        _te.Sentinel = Sentinel
except Exception:
    pass
