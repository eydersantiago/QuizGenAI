import os
from dotenv import load_dotenv
import requests
import google.generativeai as genai

# --- Cargar variables de entorno ---
load_dotenv()

# --- Configuración de APIs ---
PPLX_API_KEY = os.getenv("PPLX_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configurar Gemini
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-2.5-flash')  # o 'gemini-1.5-pro-latest'

# --- Función base ---
def _base_prompt(question_text: str) -> str:
    return (
        f"Genera una pista corta (máx. 120 caracteres) sobre esta pregunta, "
        f"sin dar la respuesta ni palabras clave explícitas. "
        f"Usa tono neutral y educativo.\n\nPregunta: {question_text}"
    )

# --- Generar pista con Perplexity ---
def generate_hint_with_perplexity(question_text: str):
    if not PPLX_API_KEY:
        raise ValueError("⚠️ Falta PPLX_API_KEY")

    print(f"[Hint] Generando pista (Perplexity) para: {question_text[:50]}...")

    response = requests.post(
        "https://api.perplexity.ai/chat/completions",
        headers={
            "Authorization": f"Bearer {PPLX_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "sonar-reasoning-pro",
            "messages": [
                {"role": "system", "content": "Eres un asistente que da pistas educativas sin revelar respuestas."},
                {"role": "user", "content": _base_prompt(question_text)},
            ],
            "temperature": 0.5,
        },
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    hint = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return hint.strip().replace("\n", " ")[:120]

# --- Generar pista con Gemini ---
def generate_hint_with_gemini(question_text: str):
    if not GEMINI_API_KEY:
        raise ValueError("⚠️ Falta GEMINI_API_KEY")

    print(f"[Hint] Generando pista (Gemini) para: {question_text[:50]}...")

    # Usamos el SDK oficial → sin URLs directas
    response = gemini_model.generate_content(_base_prompt(question_text))
    hint = response.text if hasattr(response, "text") else str(response)
    return hint.strip().replace("\n", " ")[:120]

# --- Función principal para generar pista ---
def generate_hint(question_text: str) -> str:
    try:
        return generate_hint_with_perplexity(question_text)
    except Exception as e1:
        print(f"[Hint] Error con Perplexity: {e1}. Probando Gemini...")
        try:
            return generate_hint_with_gemini(question_text)
        except Exception as e2:
            print(f"[Hint] Error con Gemini: {e2}")
            return "⚠️ No se pudo generar pista en este momento."
