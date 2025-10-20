# typing_extensions.py  (en la raíz, junto a manage.py)
# Reexporta el del agente y añade Sentinel si falta.
import importlib.util, sys

# Carga explícita del archivo del agente:
_spec = importlib.util.spec_from_file_location(
    "te_agent", "/agents/python/typing_extensions.py"
)
_te = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_te)

# Reexporta todo a nuestro módulo
globals().update(vars(_te))

# Añade Sentinel si no está
if "Sentinel" not in globals():
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
    globals()["Sentinel"] = Sentinel
