# backend/api/services/intent_router.py

import re
import time
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import google.generativeai as genai
from openai import OpenAI
import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class IntentBackend(Enum):
    GRAMMAR = "grammar"
    GEMINI = "gemini"
    PERPLEXITY = "perplexity"
    FALLBACK = "fallback"


@dataclass
class IntentResult:
    intent: str
    confidence: float
    slots: Dict
    backend_used: IntentBackend
    latency_ms: float
    raw_text: str = ""
    error: Optional[str] = None


class IntentGrammar:
    """Sistema de gramática/regex para comandos básicos"""
    
    INTENT_PATTERNS = {
        'generate_quiz': [
            r'(?:genera?|crea?|arma|haz|hazme)\s+(?:un\s+)?(?:quiz|cuestionario|examen|test)?\s*(?:de|sobre|acerca\s+de)?\s+(.+)',
            r'(?:quiz|cuestionario|test)\s+(?:de|sobre)\s+(.+)',
        ],
        'read_question': [
            r'(?:lee?|leeme|leer)\s+(?:la\s+)?pregunta\s+(\d+)',
            r'pregunta\s+(?:número\s+)?(\d+)',
        ],
        'navigate_next': [
            r'(?:siguiente|próxima?|adelante|continua?r?|next)',
        ],
        'navigate_previous': [
            r'(?:anterior|atrás|volver|back)',
        ],
        'show_answers': [
            r'(?:muestra?|mostrar|ver|enseña?r?)\s+(?:las\s+)?(?:respuestas?|opciones)',
        ],
        'regenerate': [
            r'(?:regenera?r?|vuelve\s+a\s+generar)\s+(?:la\s+)?pregunta\s+(\d+)',
            r'(?:regenera?r?|cambiar)\s+(?:pregunta\s+)?(\d+)',
        ],
        'export': [
            r'(?:exporta?r?|descargar|guardar)\s+(?:el\s+)?(?:quiz|cuestionario|test)?',
        ],
        'repeat': [
            r'(?:repite?|repetir|otra\s+vez|de\s+nuevo)',
        ],
        'slower': [
            r'(?:más\s+lento|despacio|slower)',
        ],
        'pause': [
            r'(?:pausa?|pausar|detene?r?|stop)',
        ],
        'resume': [
            r'(?:continua?r?|reanuda?r?|resume)',
        ],
        'skip': [
            r'(?:salta?r?|omitir|skip)',
        ],
        'finish': [
            r'(?:terminar|finalizar|salir|finish)',
        ],
    }
    
    # Mapeo de sinónimos para difficulty
    DIFFICULTY_MAP = {
        'fácil': 'easy',
        'facil': 'easy',
        'sencillo': 'easy',
        'sencilla': 'easy',
        'simple': 'easy',
        'básico': 'easy',
        'basico': 'easy',
        'medio': 'medium',
        'media': 'medium',
        'intermedio': 'medium',
        'intermedia': 'medium',
        'normal': 'medium',
        'difícil': 'hard',
        'dificil': 'hard',
        'complicado': 'hard',
        'complicada': 'hard',
        'avanzado': 'hard',
        'avanzada': 'hard',
    }
    
    @classmethod
    def match(cls, text: str) -> Optional[Tuple[str, Dict, float]]:
        """
        Intenta hacer match con gramática/regex
        Returns: (intent, slots, confidence) o None
        """
        text_lower = text.lower().strip()
        
        for intent, patterns in cls.INTENT_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, text_lower, re.IGNORECASE)
                if match:
                    slots = cls._extract_slots(intent, match, text_lower)
                    confidence = cls._calculate_confidence(intent, text_lower)
                    return intent, slots, confidence
        
        return None
    
    @classmethod
    def _extract_slots(cls, intent: str, match, text: str) -> Dict:
        """Extrae slots del match"""
        slots = {}
        
        if intent == 'generate_quiz':
            # Extraer tema
            slots['topic'] = match.group(1).strip()
            
            # Buscar dificultad
            for key, value in cls.DIFFICULTY_MAP.items():
                if key in text:
                    slots['difficulty'] = value
                    break
            
            # Buscar número de preguntas
            num_match = re.search(r'(\d+)\s+(?:preguntas?|items?)', text)
            if num_match:
                slots['num_questions'] = int(num_match.group(1))
        
        elif intent in ['read_question', 'regenerate']:
            if match.groups():
                slots['question_number'] = int(match.group(1))
        
        return slots
    
    @classmethod
    def _calculate_confidence(cls, intent: str, text: str) -> float:
        """Calcula score de confianza basado en palabras clave"""
        base_confidence = 0.85
        
        # Palabras clave que aumentan confianza
        keyword_boost = {
            'generate_quiz': ['genera', 'crea', 'quiz', 'cuestionario'],
            'read_question': ['lee', 'leer', 'pregunta'],
            'navigate_next': ['siguiente', 'próxima'],
        }
        
        if intent in keyword_boost:
            matches = sum(1 for word in keyword_boost[intent] if word in text)
            boost = min(matches * 0.05, 0.15)
            return min(base_confidence + boost, 1.0)
        
        return base_confidence


class GeminiNLU:
    """Cliente para Gemini API"""
    
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-pro')
        self.timeout = 3.0  # 3 segundos
        
        self.system_prompt = """Eres un clasificador de intenciones para una app de quiz educativa.
Analiza el comando de voz del usuario y devuelve SOLO un JSON con este formato:
{
  "intent": "nombre_del_intent",
  "confidence": 0.95,
  "slots": {"param": "valor"}
}

Intents válidos:
- generate_quiz: crear quiz (slots: topic, difficulty, num_questions)
- read_question: leer pregunta (slots: question_number)
- navigate_next: siguiente pregunta
- navigate_previous: pregunta anterior
- show_answers: mostrar respuestas
- regenerate: regenerar pregunta (slots: question_number)
- export: exportar quiz
- repeat: repetir última acción
- slower: hablar más lento
- pause: pausar
- resume: reanudar
- skip: saltar pregunta
- finish: terminar sesión
- unknown: no se entiende

SOLO devuelve el JSON, sin explicaciones."""
    
    def parse_intent(self, text: str) -> Tuple[str, Dict, float]:
        """Parsea intención usando Gemini"""
        try:
            prompt = f"{self.system_prompt}\n\nComando del usuario: \"{text}\""
            
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=200,
                )
            )
            
            # Parsear respuesta JSON
            import json
            result_text = response.text.strip()
            
            # Limpiar markdown si existe
            if result_text.startswith('```'):
                result_text = result_text.split('```')[1]
                if result_text.startswith('json'):
                    result_text = result_text[4:]
                result_text = result_text.strip()
            
            result = json.loads(result_text)
            
            return (
                result.get('intent', 'unknown'),
                result.get('slots', {}),
                result.get('confidence', 0.5)
            )
            
        except Exception as e:
            logger.error(f"Gemini parsing error: {e}")
            raise


class PerplexityNLU:
    """Cliente para Perplexity API"""
    
    def __init__(self):
        self.api_key = settings.PERPLEXITY_API_KEY
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.perplexity.ai"
        )
        self.timeout = 4.0  # 4 segundos
        
        self.system_prompt = """You are an intent classifier for an educational quiz app.
Analyze the voice command and return ONLY a JSON with this format:
{
  "intent": "intent_name",
  "confidence": 0.95,
  "slots": {"param": "value"}
}

Valid intents: generate_quiz, read_question, navigate_next, navigate_previous, 
show_answers, regenerate, export, repeat, slower, pause, resume, skip, finish, unknown

Return ONLY the JSON, no explanations."""
    
    def parse_intent(self, text: str) -> Tuple[str, Dict, float]:
        """Parsea intención usando Perplexity"""
        try:
            response = self.client.chat.completions.create(
                model="llama-3.1-sonar-small-128k-online",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": f"Command: \"{text}\""}
                ],
                temperature=0.1,
                max_tokens=200,
                timeout=self.timeout
            )
            
            # Parsear respuesta
            import json
            result_text = response.choices[0].message.content.strip()
            
            # Limpiar markdown
            if result_text.startswith('```'):
                result_text = result_text.split('```')[1]
                if result_text.startswith('json'):
                    result_text = result_text[4:]
                result_text = result_text.strip()
            
            result = json.loads(result_text)
            
            return (
                result.get('intent', 'unknown'),
                result.get('slots', {}),
                result.get('confidence', 0.5)
            )
            
        except Exception as e:
            logger.error(f"Perplexity parsing error: {e}")
            raise


class IntentRouter:
    """Router principal con fallback en cascada"""
    
    def __init__(self):
        self.grammar = IntentGrammar()
        self.gemini = None
        self.perplexity = None
        
        # Feature flags from settings/env
        self.use_gemini = getattr(settings, 'ENABLE_GEMINI_NLU', True)
        self.use_perplexity = getattr(settings, 'ENABLE_PERPLEXITY_NLU', True)
        
        # Umbrales
        self.grammar_threshold = 0.7
        self.llm_threshold = 0.6
        
        # Rate limiting
        self.rate_limit_key_prefix = "intent_router_rate_limit"
        self.rate_limit_per_user = 100  # por hora
    
    def _check_rate_limit(self, user_id: str) -> bool:
        """Verifica rate limit por usuario"""
        key = f"{self.rate_limit_key_prefix}:{user_id}"
        current = cache.get(key, 0)
        
        if current >= self.rate_limit_per_user:
            return False
        
        cache.set(key, current + 1, 3600)  # 1 hora
        return True
    
    def route(self, text: str, user_id: str) -> IntentResult:
        """
        Pipeline principal: Grammar → Gemini → Perplexity → Fallback
        """
        start_time = time.time()
        
        # Rate limiting
        if not self._check_rate_limit(user_id):
            logger.warning(f"Rate limit exceeded for user {user_id}")
            return IntentResult(
                intent='unknown',
                confidence=0.0,
                slots={},
                backend_used=IntentBackend.FALLBACK,
                latency_ms=0,
                error="Rate limit exceeded"
            )
        
        # 1. Intentar con gramática primero
        grammar_result = self.grammar.match(text)
        if grammar_result:
            intent, slots, confidence = grammar_result
            
            if confidence >= self.grammar_threshold:
                latency = (time.time() - start_time) * 1000
                logger.info(f"Grammar match: {intent} (conf: {confidence})")
                
                return IntentResult(
                    intent=intent,
                    confidence=confidence,
                    slots=slots,
                    backend_used=IntentBackend.GRAMMAR,
                    latency_ms=latency,
                    raw_text=text
                )
        
        # 2. Intentar con Gemini
        if self.use_gemini:
            try:
                if not self.gemini:
                    self.gemini = GeminiNLU()
                
                gemini_start = time.time()
                intent, slots, confidence = self.gemini.parse_intent(text)
                gemini_latency = (time.time() - gemini_start) * 1000
                
                if gemini_latency > 3000:  # Timeout
                    logger.warning(f"Gemini timeout: {gemini_latency}ms")
                    raise TimeoutError("Gemini exceeded timeout")
                
                if confidence >= self.llm_threshold:
                    latency = (time.time() - start_time) * 1000
                    logger.info(f"Gemini match: {intent} (conf: {confidence}, latency: {gemini_latency}ms)")
                    
                    return IntentResult(
                        intent=intent,
                        confidence=confidence,
                        slots=slots,
                        backend_used=IntentBackend.GEMINI,
                        latency_ms=latency,
                        raw_text=text
                    )
                    
            except Exception as e:
                logger.error(f"Gemini failed: {e}")
        
        # 3. Fallback a Perplexity
        if self.use_perplexity:
            try:
                if not self.perplexity:
                    self.perplexity = PerplexityNLU()
                
                perplexity_start = time.time()
                intent, slots, confidence = self.perplexity.parse_intent(text)
                perplexity_latency = (time.time() - perplexity_start) * 1000
                
                latency = (time.time() - start_time) * 1000
                logger.info(f"Perplexity match: {intent} (conf: {confidence}, latency: {perplexity_latency}ms)")
                
                return IntentResult(
                    intent=intent,
                    confidence=confidence,
                    slots=slots,
                    backend_used=IntentBackend.PERPLEXITY,
                    latency_ms=latency,
                    raw_text=text
                )
                
            except Exception as e:
                logger.error(f"Perplexity failed: {e}")
        
        # 4. Fallback final - comandos básicos
        latency = (time.time() - start_time) * 1000
        fallback_intent = self._fallback_intent(text)
        
        logger.warning(f"All backends failed, using fallback: {fallback_intent}")
        
        return IntentResult(
            intent=fallback_intent,
            confidence=0.3,
            slots={},
            backend_used=IntentBackend.FALLBACK,
            latency_ms=latency,
            raw_text=text,
            error="All backends failed"
        )
    
    def _fallback_intent(self, text: str) -> str:
        """Fallback simple basado en palabras clave"""
        text_lower = text.lower()
        
        # Comandos más comunes
        if any(word in text_lower for word in ['siguiente', 'próxima', 'next']):
            return 'navigate_next'
        elif any(word in text_lower for word in ['anterior', 'atrás', 'back']):
            return 'navigate_previous'
        elif any(word in text_lower for word in ['genera', 'crea', 'haz']):
            return 'generate_quiz'
        elif any(word in text_lower for word in ['lee', 'leer', 'read']):
            return 'read_question'
        elif any(word in text_lower for word in ['repite', 'repetir', 'repeat']):
            return 'repeat'
        elif any(word in text_lower for word in ['pausa', 'detén', 'stop']):
            return 'pause'
        
        return 'unknown'