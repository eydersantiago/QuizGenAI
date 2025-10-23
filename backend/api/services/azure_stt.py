# api/services/azure_stt.py
import os
import time
import requests

SPEECH_REGION = os.getenv("SPEECH_REGION", "")
SPEECH_KEY = os.getenv("SPEECH_KEY", "")

# Token endpoint (igual que para TTS)
_TOKEN_URL = f"https://{SPEECH_REGION}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
# Short-form STT (<= ~60 s) - conversación, con puntuación
_STT_URL = (
    f"https://{SPEECH_REGION}.stt.speech.microsoft.com/"
    "speech/recognition/conversation/cognitiveservices/v1"
)

def issue_token() -> str:
    r = requests.post(
        _TOKEN_URL,
        headers={"Ocp-Apim-Subscription-Key": SPEECH_KEY},
        timeout=10,
    )
    r.raise_for_status()
    return r.text

def recognize_short_audio(
    audio_bytes: bytes,
    content_type: str = "audio/wav; codecs=audio/pcm; samplerate=16000",
    language: str = "es-ES",
    result_format: str = "detailed",  # "simple" | "detailed"
):
    """
    Envía audio corto a Azure STT y devuelve (texto, json_bruto, latency_ms).
    Soporta WAV PCM 16kHz y OGG/Opus (p.ej. 'audio/ogg; codecs=opus').
    """
    assert SPEECH_REGION and SPEECH_KEY, "Configura SPEECH_REGION y SPEECH_KEY"

    token = issue_token()
    params = {"language": language, "format": result_format}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
        "Accept": "application/json;text/xml",
        "User-Agent": "quizgenai-backend",
        # Opcional: filtro de blasfemias: "masked" | "removed" | "raw"
        "Profanity": "masked",
    }

    t0 = time.perf_counter()
    r = requests.post(_STT_URL, params=params, headers=headers, data=audio_bytes, timeout=60)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    r.raise_for_status()
    data = r.json()

    # "detailed" devuelve NBest; "simple" devuelve DisplayText
    text = ""
    confidence = None
    if "DisplayText" in data:
        text = data.get("DisplayText") or ""
    elif "NBest" in data:
        # Toma la mejor hipótesis
        nbest = data.get("NBest") or []
        if nbest:
            text = nbest[0].get("Display", "") or nbest[0].get("Lexical", "")
            confidence = nbest[0].get("Confidence")

    return text.strip(), data, latency_ms, confidence
