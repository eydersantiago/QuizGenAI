# backend/api/views/intent_router_views.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .services.intent_router import IntentRouter
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


class IntentRouterViewSet(viewsets.ViewSet):
    """Endpoints para procesamiento de intenciones"""
    permission_classes = [IsAuthenticated]
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.router = IntentRouter()
    
    @action(detail=False, methods=['post'])
    def parse(self, request):
        """
        Parsea un comando de voz y devuelve la intención detectada
        
        Body: {
            "text": "genera un quiz de matemáticas fácil"
        }
        """
        text = request.data.get('text', '').strip()
        
        if not text:
            return Response(
                {'error': 'El campo "text" es requerido'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Redactar PII antes de enviar a LLMs
        text_redacted = self._redact_pii(text)
        
        # Parsear intención
        result = self.router.route(text_redacted, str(request.user.id))
        
        # Log analytics
        logger.info(
            f"Intent parsed: {result.intent}",
            extra={
                'user_id': request.user.id,
                'intent': result.intent,
                'confidence': result.confidence,
                'backend': result.backend_used.value,
                'latency_ms': result.latency_ms,
                'event': 'intent_recognized',
                'has_error': result.error is not None
            }
        )
        
        response_data = {
            'intent': result.intent,
            'confidence': result.confidence,
            'slots': result.slots,
            'backend_used': result.backend_used.value,
            'latency_ms': round(result.latency_ms, 2)
        }
        
        if result.error:
            response_data['warning'] = result.error
        
        return Response(response_data)
    
    @action(detail=False, methods=['post'])
    def batch_parse(self, request):
        """
        Parsea múltiples comandos en batch
        
        Body: {
            "texts": ["comando 1", "comando 2", ...]
        }
        """
        texts = request.data.get('texts', [])
        
        if not isinstance(texts, list) or len(texts) == 0:
            return Response(
                {'error': 'El campo "texts" debe ser un array no vacío'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if len(texts) > 10:
            return Response(
                {'error': 'Máximo 10 textos por batch'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        results = []
        for text in texts:
            text_redacted = self._redact_pii(text.strip())
            result = self.router.route(text_redacted, str(request.user.id))
            
            results.append({
                'text': text,
                'intent': result.intent,
                'confidence': result.confidence,
                'slots': result.slots,
                'backend_used': result.backend_used.value,
                'latency_ms': round(result.latency_ms, 2)
            })
        
        return Response({'results': results})
    
    @action(detail=False, methods=['get'])
    def health(self, request):
        """Verifica el estado de los backends"""
        health_status = {
            'grammar': 'ok',
            'gemini': 'disabled',
            'perplexity': 'disabled'
        }
        
        # Test Gemini
        if self.router.use_gemini:
            try:
                test_result = self.router.gemini.parse_intent("siguiente")
                health_status['gemini'] = 'ok'
            except Exception as e:
                health_status['gemini'] = f'error: {str(e)}'
        
        # Test Perplexity
        if self.router.use_perplexity:
            try:
                test_result = self.router.perplexity.parse_intent("siguiente")
                health_status['perplexity'] = 'ok'
            except Exception as e:
                health_status['perplexity'] = f'error: {str(e)}'
        
        all_ok = all(v in ['ok', 'disabled'] for v in health_status.values())
        
        return Response({
            'status': 'healthy' if all_ok else 'degraded',
            'backends': health_status
        })
    
    @action(detail=False, methods=['get'])
    def supported_intents(self, request):
        """Lista de intents soportados con ejemplos"""
        intents_info = {
            'generate_quiz': {
                'description': 'Generar un nuevo quiz',
                'slots': ['topic', 'difficulty', 'num_questions'],
                'examples': [
                    'genera un quiz de matemáticas',
                    'crea 10 preguntas fáciles de historia',
                    'hazme un test de física difícil'
                ]
            },
            'read_question': {
                'description': 'Leer una pregunta específica',
                'slots': ['question_number'],
                'examples': [
                    'lee la pregunta 3',
                    'leer pregunta número 5',
                    'pregunta 1'
                ]
            },
            'navigate_next': {
                'description': 'Ir a la siguiente pregunta',
                'slots': [],
                'examples': ['siguiente', 'próxima', 'continuar', 'adelante']
            },
            'navigate_previous': {
                'description': 'Ir a la pregunta anterior',
                'slots': [],
                'examples': ['anterior', 'atrás', 'volver']
            },
            'show_answers': {
                'description': 'Mostrar respuestas',
                'slots': [],
                'examples': ['muestra las respuestas', 'ver opciones']
            },
            'regenerate': {
                'description': 'Regenerar una pregunta',
                'slots': ['question_number'],
                'examples': [
                    'regenera la pregunta 2',
                    'cambiar pregunta 4',
                    'vuelve a generar la 1'
                ]
            },
            'export': {
                'description': 'Exportar el quiz',
                'slots': [],
                'examples': ['exportar', 'descargar quiz', 'guardar']
            },
            'repeat': {
                'description': 'Repetir última acción',
                'slots': [],
                'examples': ['repite', 'otra vez', 'de nuevo']
            },
            'slower': {
                'description': 'Hablar más lento',
                'slots': [],
                'examples': ['más lento', 'despacio']
            },
            'pause': {
                'description': 'Pausar',
                'slots': [],
                'examples': ['pausa', 'detén', 'stop']
            },
            'resume': {
                'description': 'Reanudar',
                'slots': [],
                'examples': ['continúa', 'reanuda', 'resume']
            },
            'skip': {
                'description': 'Saltar pregunta',
                'slots': [],
                'examples': ['saltar', 'omitir', 'skip']
            },
            'finish': {
                'description': 'Terminar sesión',
                'slots': [],
                'examples': ['terminar', 'finalizar', 'salir']
            }
        }
        
        return Response({
            'total_intents': len(intents_info),
            'intents': intents_info
        })
    
    def _redact_pii(self, text: str) -> str:
        """Redacta información personal identificable"""
        import re
        
        # Redactar emails
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', text)
        
        # Redactar números de teléfono (colombianos)
        text = re.sub(r'\b3\d{9}\b', '[PHONE]', text)
        text = re.sub(r'\b\d{7,10}\b', '[PHONE]', text)
        
        # Redactar números de identificación
        text = re.sub(r'\b\d{8,10}\b', '[ID]', text)
        
        return text