# api/view_hint.py
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .utils.hint_generator import generate_hint, clean_hint_text

@api_view(["POST"])
def hint_view(request):
    """
    Endpoint: POST /api/hint/
    Body aceptado:
      - {"question": "texto"}  OR
      - {"question":"texto", "meta": { "type":"mcq"|"vf"|"short", "options":[...], "answer":"A"|... }}
    """
    try:
        data = request.data or {}
        qtxt = (data.get("question") or "").strip()
        meta = data.get("meta") or {}

        if not qtxt:
            return Response({"error": "Falta el texto de la pregunta"}, status=400)

        # Si es MCQ y tenemos opciones/answer: pista “entre A y B”
        qtype = (meta.get("type") or "").lower()
        options = meta.get("options") or []
        answer = (meta.get("answer") or "").strip()

        if qtype == "mcq" and isinstance(options, list) and options and answer:
            # Letra correcta (A..D)
            correct_letter = str(answer).strip().upper()[:1] or ""
            letters = ["A","B","C","D"][:len(options)]
            # elige un distractor distinto
            distractors = [L for L in letters if L != correct_letter]
            other = distractors[0] if distractors else ""
            # orden aleatorio para no revelar patrón
            pair = sorted([correct_letter, other])
            hint = f"Está entre {pair[0]} y {pair[1]}."
            return Response({"hint": hint})

        # Caso general: usa LLM pero limpia <think> y etiquetas
        hint = generate_hint(qtxt)
        hint = clean_hint_text(hint)[:120] or "Reflexiona sobre el propósito central antes de ver ejemplos."
        return Response({"hint": hint})

    except Exception as e:
        print("[HintView] Error:", e)
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
