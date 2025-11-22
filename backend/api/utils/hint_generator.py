# api/utils/hint_generator.py
import re
from dotenv import load_dotenv
import google.generativeai as genai

from api.utils.gemini_keys import get_next_gemini_key

load_dotenv()

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


def _build_gemini_model():
    api_key = get_next_gemini_key()
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-2.5-flash')


def generate_hint_with_gemini(question_text: str):
    print(f"[Hint] Gemini para: {question_text[:50]}...")
    model = _build_gemini_model()
    response = model.generate_content(_base_prompt(question_text))
    raw = response.text if hasattr(response, "text") else str(response)
    return clean_hint_text(raw)[:120]


def generate_hint(question_text: str) -> str:
    try:
        return generate_hint_with_gemini(question_text)
    except Exception as e:
        print(f"[Hint] Error Gemini: {e}")
        return "⚠️ No se pudo generar pista en este momento."
