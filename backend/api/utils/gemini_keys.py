# api/utils/gemini_keys.py

import os
import itertools
from typing import List
import logging

logger = logging.getLogger(__name__)

_key_cycle = None
_keys_cache: List[str] | None = None


def _mask_key(key: str) -> str:
    """
    Enmascara la key para logging seguro.
    Ejemplo: AIzaSyA..... -> AIzaSyAm...rukk
    """
    if not key:
        return "<empty>"
    k = key.strip()
    if len(k) <= 10:
        return k[:3] + "..."  # muy corta, solo primeros 3
    return f"{k[:8]}...{k[-4:]}"


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

    # 🔹 LOG: cuántas keys encontró y cuáles (enmascaradas)
    if not keys:
        logger.warning("[GeminiKeys] No se encontró ninguna GEMINI_API_KEY(S) en el entorno.")
    else:
        masked = [ _mask_key(k) for k in keys ]
        logger.info(
            "[GeminiKeys] Cargadas %d Gemini API key(s) desde el entorno: %s",
            len(keys),
            ", ".join(masked),
        )

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
        # 🔹 LOG: error crítico
        logger.error("[GeminiKeys] get_next_gemini_key llamado sin keys configuradas.")
        raise RuntimeError("GEMINI_API_KEY(S) not set")

    if len(keys) == 1:
        # 🔹 LOG: está usando la única key disponible
        logger.debug(
            "[GeminiKeys] Usando única Gemini API key configurada: %s",
            _mask_key(keys[0]),
        )
        return keys[0]

    if _key_cycle is None:
        _key_cycle = itertools.cycle(keys)

    key = next(_key_cycle)
    try:
        idx = keys.index(key)
    except ValueError:
        idx = -1

    # 🔹 LOG: qué key usa en esta llamada (índice + key enmascarada)
    logger.info(
        "[GeminiKeys] Rotación de Gemini key -> usando key #%s/%s: %s",
        idx + 1 if idx >= 0 else "?",
        len(keys),
        _mask_key(key),
    )

    return key


def has_any_gemini_key() -> bool:
    return bool(_load_keys())


def get_gemini_key_count() -> int:
    """Return how many Gemini API keys are configured.

    Useful to tune retry/backoff strategies so we exhaust all configured keys
    before falling back to unpreferred providers.
    """
    try:
        return len(_load_keys())
    except Exception:
        return 0
