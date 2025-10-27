# api/view_hint.py
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .utils.hint_generator import generate_hint

@api_view(["POST"])
def hint_view(request):
    """
    Endpoint: POST /api/hint/
    Body: { "question": "texto de la pregunta" }
    """
    try:
        question = request.data.get("question", "").strip()
        if not question:
            return Response({"error": "Falta el texto de la pregunta"}, status=400)

        hint = generate_hint(question)
        return Response({"hint": hint})
    except Exception as e:
        print("[HintView] Error:", e)
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
