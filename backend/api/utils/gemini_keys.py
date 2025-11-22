import os
import itertools
from typing import List

_key_cycle = None
_keys_cache: List[str] | None = None

def _load_keys() -> List[str]:
    global _keys_cache
    if _keys_cache is not None:
        return _keys_cache

    raw_list = os.getenv("GEMINI_API_KEYS")
    if raw_list:
        keys = [k.strip() for k in raw_list.split(",") if k.strip()]
    else:
        single = os.getenv("GEMINI_API_KEY", "").strip()
        keys = [single] if single else []

    _keys_cache = keys
    return keys

def get_next_gemini_key() -> str:
    """Return the next Gemini API key available.

    If multiple keys are configured via ``GEMINI_API_KEYS`` (comma-separated),
    the keys are rotated in round-robin order. Falls back to ``GEMINI_API_KEY``
    for backwards compatibility.
    """
    global _key_cycle
    keys = _load_keys()
    if not keys:
        raise RuntimeError("GEMINI_API_KEY(S) not set")

    if len(keys) == 1:
        return keys[0]

    if _key_cycle is None:
        _key_cycle = itertools.cycle(keys)
    return next(_key_cycle)

def has_any_gemini_key() -> bool:
    return bool(_load_keys())
