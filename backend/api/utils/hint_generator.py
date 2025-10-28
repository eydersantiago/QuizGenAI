# api/utils/hint_generator.py
import os, re
from dotenv import load_dotenv
import requests
import google.generativeai as genai

load_dotenv()

PPLX_API_KEY = os.getenv("PPLX_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-2.5-flash')

THINK_BLOCK_RE = re.compile(r"</?think\b[^>]*>", re.IGNORECASE)
ANY_TAG_RE = re.compile(r"<[^>]+>")

def clean_hint_text(text: str) -> str:
    if not text:
        return ""
    # quita bloques <think> y cualquier etiqueta
    t = THINK_BLOCK_RE.sub("", text)
    t = ANY_TAG_RE.sub("", t)
    t = t.replace("\n", " ").strip()
    return t

def _base_prompt(question_text: str) -> str:
    return (
        "Genera una pista muy corta (máx. 120 caracteres) para resolver la pregunta.\n"
        "No des la respuesta, ni palabras clave explícitas.\n"
        f"Pregunta: {question_text}"
    )

def generate_hint_with_perplexity(question_text: str):
    if not PPLX_API_KEY:
        raise ValueError("⚠️ Falta PPLX_API_KEY")

    print(f"[Hint] PPLX para: {question_text[:50]}...")
    # Usa modelo no-reasoning para evitar <think>
    model_name = os.getenv("PPLX_MODEL", "sonar-pro")

    response = requests.post(
        "https://api.perplexity.ai/chat/completions",
        headers={
            "Authorization": f"Bearer {PPLX_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": model_name,
            "messages": [
                {"role": "system", "content": "Eres un asistente que da pistas educativas sin revelar respuestas."},
                {"role": "user", "content": _base_prompt(question_text)},
            ],
            "temperature": 0.3,
           # algunas cuentas soportan esto; si no, no pasa nada
            "response_format": {"type": "text"},
        },
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return clean_hint_text(raw)[:120]

def generate_hint_with_gemini(question_text: str):
    if not GEMINI_API_KEY:
        raise ValueError("⚠️ Falta GEMINI_API_KEY")

    print(f"[Hint] Gemini para: {question_text[:50]}...")
    response = gemini_model.generate_content(_base_prompt(question_text))
    raw = response.text if hasattr(response, "text") else str(response)
    return clean_hint_text(raw)[:120]

def generate_hint(question_text: str) -> str:
    try:
        return generate_hint_with_perplexity(question_text)
    except Exception as e1:
        print(f"[Hint] Error PPLX: {e1}. Probando Gemini…")
        try:
            return generate_hint_with_gemini(question_text)
        except Exception as e2:
            print(f"[Hint] Error Gemini: {e2}")
            return "⚠️ No se pudo generar pista en este momento."
