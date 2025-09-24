import os
from django.http import JsonResponse
from rest_framework.decorators import api_view
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

@api_view(['POST'])
def gemini_generate(request):
	prompt = request.data.get('prompt', '')
	api_key = os.getenv('GEMINI_API_KEY')
	if not api_key:
		return JsonResponse({'error': 'API key not configured'}, status=500)
	genai.configure(api_key=api_key)
	try:
		model = genai.GenerativeModel('gemini-2.0-flash')
		response = model.generate_content(prompt)
		return JsonResponse({'result': response.text})
	except Exception as e:
		return JsonResponse({'error': str(e)}, status=500)
