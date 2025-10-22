# api/services/azure_speech.py
import time, hashlib, os, base64
import requests
from django.conf import settings

SPEECH_REGION = os.getenv("SPEECH_REGION", "")
SPEECH_KEY = os.getenv("SPEECH_KEY", "")
TOKEN_URL = f"https://{SPEECH_REGION}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
TTS_URL = f"https://{SPEECH_REGION}.tts.speech.microsoft.com/cognitiveservices/v1"

# Cache en disco para ahorrar créditos (no vuelve a sintetizar el mismo texto+voz+formato)
CACHE_DIR = os.path.join(getattr(settings, "BASE_DIR", "."), "tts_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

def _hash_key(voice: str, fmt: str, text: str) -> str:
    h = hashlib.sha256()
    h.update((voice + "|" + fmt + "|" + text).encode("utf-8"))
    return h.hexdigest()

def issue_token() -> str:
    # Token ~10 min
    r = requests.post(
        TOKEN_URL,
        headers={"Ocp-Apim-Subscription-Key": SPEECH_KEY},
        timeout=10,
    )
    r.raise_for_status()
    return r.text

def synthesize(text: str,
               voice: str = "es-ES-AlvaroNeural",
               fmt: str = "audio-16khz-32kbitrate-mono-mp3") -> bytes:
    """
    Devuelve audio bytes. Usa cache por (voice, fmt, text).
    """
    key = _hash_key(voice, fmt, text)
    cached = os.path.join(CACHE_DIR, f"{key}.bin")
    if os.path.exists(cached):
        with open(cached, "rb") as f:
            return f.read()

    token = issue_token()
    ssml = f"""
<speak version="1.0" xml:lang="es-ES">
  <voice name="{voice}">
    <prosody rate="0%" pitch="0%">{text}</prosody>
  </voice>
</speak>""".strip()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": fmt,
        "User-Agent": "quizgenai-backend"
    }
    t0 = time.perf_counter()
    r = requests.post(TTS_URL, data=ssml.encode("utf-8"), headers=headers, timeout=30)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    r.raise_for_status()
    audio = r.content

    # guarda cache
    with open(cached, "wb") as f:
        f.write(audio)

    return audio, latency_ms
