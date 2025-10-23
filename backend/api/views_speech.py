# api/views_speech.py
import os, requests
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.conf import settings

SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY") or getattr(settings, "AZURE_SPEECH_KEY", None)
SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION") or getattr(settings, "AZURE_SPEECH_REGION", None)

@require_GET
def speech_token(request):
    if not SPEECH_KEY or not SPEECH_REGION:
        return JsonResponse({"error": "Missing AZURE_SPEECH_KEY/AZURE_SPEECH_REGION"}, status=500)

    r = requests.post(
        f"https://{SPEECH_REGION}.api.cognitive.microsoft.com/sts/v1.0/issueToken",
        headers={"Ocp-Apim-Subscription-Key": SPEECH_KEY},
        timeout=10,
    )
    if r.status_code != 200:
        return JsonResponse({"error": "Could not obtain speech token"}, status=500)
    return JsonResponse({"token": r.text, "region": SPEECH_REGION})
