# api/services/suggestion_engine.py
"""
Motor de sugerencias proactivas para QuizGenAI.

Genera sugerencias basadas en reglas predefinidas del contexto del usuario
(inactividad, errores, progreso) con fallback a LLM cuando sea necesario.
"""

import logging
import time
from typing import Dict, Optional, Any
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# Intentar importar clase NLU para fallback a LLM
try:
    import os
    import requests
    from openai import OpenAI

    from api.utils.gemini_keys import get_next_gemini_key

    class GeminiNLU:
        """Wrapper para Gemini API para generar texto de sugerencias."""

        def __init__(self):
            self.api_key = get_next_gemini_key()
            self.model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
            self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

        def generate_text(self, prompt: str, max_words: int = 20) -> Optional[str]:
            """Genera texto usando Gemini API."""
            try:
                headers = {"Content-Type": "application/json"}
                payload = {
                    "contents": [{
                        "parts": [{"text": prompt}]
                    }],
                    "generationConfig": {
                        "temperature": 0.7,
                        "maxOutputTokens": max_words * 2,
                        "topP": 0.9,
                    }
                }

                response = requests.post(
                    f"{self.api_url}?key={self.api_key}",
                    headers=headers,
                    json=payload,
                    timeout=10
                )

                if response.status_code != 200:
                    logger.warning(f"Gemini API error: {response.status_code}")
                    return None

                data = response.json()
                text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                return text if text else None

            except Exception as e:
                logger.error(f"Error generando texto con Gemini: {e}")
                return None

    class OpenAINLU:
        """Wrapper para OpenAI API como fallback de sugerencias."""

        def __init__(self):
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY not configured")
            self.client = OpenAI(api_key=api_key)
            self.model = os.getenv("OPENAI_SUGGESTION_MODEL", "gpt-4o-mini")

        def generate_text(self, prompt: str, max_words: int = 20) -> Optional[str]:
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=max_words * 2,
                )
                text = (resp.choices[0].message.content or "").strip()
                return text if text else None
            except Exception as e:
                logger.error(f"Error generando texto con OpenAI: {e}")
                return None

    GEMINI_AVAILABLE = True
    OPENAI_AVAILABLE = True

except ImportError as e:
    logger.warning(f"NLU classes no disponibles: {e}")
    GEMINI_AVAILABLE = False
    OPENAI_AVAILABLE = False
    GeminiNLU = None
    OpenAINLU = None


class SuggestionEngine:
    """
    Motor de sugerencias proactivas basado en reglas y fallback a LLM.

    Analiza el contexto del usuario (inactividad, errores, progreso) y genera
    sugerencias apropiadas usando reglas predefinidas o LLM cuando sea necesario.

    Attributes:
        idle_threshold (int): Umbral de inactividad en segundos (default: 15)
        error_threshold (int): Número de errores consecutivos para sugerencias (default: 2)
        use_llm_fallback (bool): Si usar LLM cuando no hay reglas aplicables (default: True)
        gemini (GeminiNLU): Instancia de Gemini para fallback
    """

    def __init__(
        self,
        idle_threshold: int = 15,
        error_threshold: int = 2,
        use_llm_fallback: bool = True
    ):
        """
        Inicializa el motor de sugerencias.

        Args:
            idle_threshold: Segundos de inactividad antes de sugerencia
            error_threshold: Errores consecutivos antes de sugerencia
            use_llm_fallback: Si usar LLM cuando no hay reglas aplicables
        """
        self.idle_threshold = idle_threshold
        self.error_threshold = error_threshold
        self.use_llm_fallback = use_llm_fallback

        # Inicializar instancias de LLM si están disponibles
        self.gemini = None
        self.openai = None

        if use_llm_fallback:
            try:
                if GEMINI_AVAILABLE and GeminiNLU:
                    self.gemini = GeminiNLU()
                    logger.info("Gemini NLU inicializado correctamente")
            except Exception as e:
                logger.warning(f"No se pudo inicializar Gemini: {e}")

            try:
                if OPENAI_AVAILABLE and OpenAINLU:
                    self.openai = OpenAINLU()
                    logger.info("OpenAI NLU inicializado correctamente")
            except Exception as e:
                logger.warning(f"No se pudo inicializar OpenAI: {e}")

    def _check_rate_limit(self, user_id: Optional[str]) -> bool:
        """
        Verifica si el usuario está dentro del límite de rate limiting.

        Rate limit: 1 sugerencia cada 3 minutos (180 segundos) por usuario.

        Args:
            user_id: ID del usuario (opcional)

        Returns:
            True si está rate limited (debe ser rechazado), False si puede continuar
        """
        if not user_id:
            # Sin user_id, no aplicar rate limiting
            return False

        cache_key = f"sugg_rl_{user_id}"
        last_suggestion_time = cache.get(cache_key)

        if last_suggestion_time:
            # Usuario está rate limited
            logger.debug(f"Usuario {user_id} rate limited")
            return True

        # Registrar timestamp actual y setear expiración de 3 minutos (180 segundos)
        cache.set(cache_key, time.time(), timeout=180)
        return False

    def _check_rule_1(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Regla 1: Inactividad sin empezar (idle >= 15s, answered = 0).

        Sugiere leer la primera pregunta.

        Args:
            context: Contexto del usuario

        Returns:
            Sugerencia o None si la regla no aplica
        """
        idle_seconds = context.get("idleSeconds", 0)
        progress = context.get("progress", {})
        answered = progress.get("answered", 0)

        if idle_seconds >= self.idle_threshold and answered == 0:
            logger.info("Regla 1 aplicada: inactividad sin empezar")
            return {
                "suggestion_text": "Parece que aún no has empezado. ¿Quieres que te lea la primera pregunta?",
                "action_type": "read_question",
                "action_params": {"question_index": 0},
                "priority": "high",
                "reasoning": "Usuario inactivo sin comenzar el quiz",
                "source": "rule_based"
            }

        return None

    def _check_rule_2(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Regla 2: Inactividad en medio del quiz (idle >= 15s, progreso parcial).

        Sugiere continuar leyendo.

        Args:
            context: Contexto del usuario

        Returns:
            Sugerencia o None si la regla no aplica
        """
        idle_seconds = context.get("idleSeconds", 0)
        progress = context.get("progress", {})
        answered = progress.get("answered", 0)
        total = progress.get("total", 0)

        # Tiene progreso parcial pero no ha terminado
        if idle_seconds >= self.idle_threshold and 0 < answered < total:
            current_question = answered  # Siguiente pregunta sin responder
            logger.info("Regla 2 aplicada: inactividad con progreso parcial")
            return {
                "suggestion_text": "¿Continuamos? Puedo leerte la siguiente pregunta.",
                "action_type": "read_question",
                "action_params": {"question_index": current_question},
                "priority": "medium",
                "reasoning": "Usuario inactivo con progreso parcial en el quiz",
                "source": "rule_based"
            }

        return None

    def _check_rule_3(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        UPDATED: Regla 3: Error rate >= 70% con muestra significativa.

        Detecta un patrón real de dificultad en lugar de errores aislados.
        Sugiere generar un quiz más fácil del mismo tema.

        Args:
            context: Contexto del usuario

        Returns:
            Sugerencia o None si la regla no aplica
        """
        error_rate = context.get("errorRate", 0)
        total_answered = context.get("totalAnswered", 0)
        total_errors = context.get("totalErrors", 0)
        quiz_topic = context.get("quizTopic", "")

        # Verificar: al menos 3 preguntas respondidas Y error rate >= 70%
        if total_answered >= 3 and error_rate >= 0.7:
            error_percentage = int(error_rate * 100)
            logger.info(
                f"Regla 3 aplicada: {error_percentage}% de error rate "
                f"({total_errors}/{total_answered} incorrectas)"
            )

            # Sugerencia personalizada con estadísticas
            suggestion_text = (
                f"Veo que {quiz_topic if quiz_topic else 'este tema'} puede ser retador. "
                f"Llevas {error_percentage}% de errores. "
                f"¿Te gustaría probar 5 preguntas más fáciles de {quiz_topic if quiz_topic else 'este tema'} para practicar?"
            )

            action_params = {
                "difficulty": "Fácil",
                "count": 5  # Sugerir 5 preguntas para práctica
            }

            if quiz_topic:
                action_params["topic"] = quiz_topic

            return {
                "suggestion_text": suggestion_text,
                "action_type": "generate_quiz",
                "action_params": action_params,
                "priority": "high",
                "reasoning": f"Usuario con {error_percentage}% de error rate en {total_answered} preguntas",
                "source": "rule_based"
            }

        return None

    def _check_rule_4(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Regla 4: Progreso >= 80%.

        Sugiere continuar para completar.

        Args:
            context: Contexto del usuario

        Returns:
            Sugerencia o None si la regla no aplica
        """
        progress = context.get("progress", {})
        percentage = progress.get("percentage", 0)
        answered = progress.get("answered", 0)
        total = progress.get("total", 0)

        # Progreso alto pero no terminado
        if percentage >= 80 and answered < total:
            logger.info("Regla 4 aplicada: progreso >= 80%")
            return {
                "suggestion_text": "¡Casi terminas! ¿Continuamos con las últimas preguntas?",
                "action_type": "read_question",
                "action_params": {"question_index": answered},
                "priority": "low",
                "reasoning": "Usuario cerca de completar el quiz",
                "source": "rule_based"
            }

        return None

    def _check_rule_5(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Regla 5: Idle >= 30s con al menos 3 preguntas respondidas.

        Sugiere revisar respuestas.

        Args:
            context: Contexto del usuario

        Returns:
            Sugerencia o None si la regla no aplica
        """
        idle_seconds = context.get("idleSeconds", 0)
        progress = context.get("progress", {})
        answered = progress.get("answered", 0)

        if idle_seconds >= 30 and answered >= 3:
            logger.info("Regla 5 aplicada: idle >= 30s con progreso significativo")
            return {
                "suggestion_text": "Llevas un rato sin interactuar. ¿Quieres revisar tus respuestas?",
                "action_type": "navigate",
                "action_params": {"action": "review_answers"},
                "priority": "medium",
                "reasoning": "Usuario inactivo por largo tiempo con respuestas registradas",
                "source": "rule_based"
            }

        return None

    def _generate_llm_suggestion(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Genera sugerencia usando LLM (solo Gemini) como fallback.

        Args:
            context: Contexto del usuario

        Returns:
            Sugerencia generada por LLM o None si falla
        """
        if not self.use_llm_fallback:
            return None

        # Construir prompt descriptivo del contexto
        idle_seconds = context.get("idleSeconds", 0)
        consecutive_errors = context.get("consecutiveErrors", 0)
        progress = context.get("progress", {})
        percentage = progress.get("percentage", 0)
        answered = progress.get("answered", 0)
        total = progress.get("total", 0)
        last_action = context.get("lastAction", "ninguna")
        quiz_topic = context.get("quizTopic", "general")

        prompt = f"""Genera una sugerencia amigable y breve (máximo 20 palabras) para un estudiante en QuizGenAI.

Contexto del usuario:
- Tiempo inactivo: {idle_seconds} segundos
- Errores consecutivos: {consecutive_errors}
- Progreso: {answered}/{total} preguntas ({percentage:.0f}%)
- Última acción: {last_action}
- Tema del quiz: {quiz_topic}

La sugerencia debe ser motivadora y específica. Responde SOLO con el texto de la sugerencia, sin formato adicional ni explicaciones."""

        suggestion_text = None
        source = None

        providers = []
        if self.gemini:
            providers.append(("gemini", self.gemini))
        if self.openai:
            providers.append(("openai", self.openai))

        for name, engine in providers:
            logger.info(f"Intentando generar sugerencia con {name}")
            try:
                suggestion_text = engine.generate_text(prompt, max_words=20)
                if suggestion_text:
                    source = name
                    logger.info(f"Sugerencia generada exitosamente con {name}")
                    break
            except Exception as e:
                logger.error(f"Error usando {name} para sugerencia: {e}")

        if not suggestion_text:
            logger.warning("Fallback a LLM falló: ningún proveedor disponible para sugerencias")
            return None

        # Determinar acción basada en el contexto
        action_type = "read_question"
        action_params = {}
        priority = "medium"

        if consecutive_errors >= 3:
            action_type = "generate_quiz"
            action_params = {"difficulty": "Fácil"}
            priority = "high"
        elif answered < total:
            action_type = "read_question"
            action_params = {"question_index": answered}

        return {
            "suggestion_text": suggestion_text,
            "action_type": action_type,
            "action_params": action_params,
            "priority": priority,
            "reasoning": f"Sugerencia generada por LLM basada en contexto del usuario",
            "source": source
        }

    def generate_suggestion(
        self,
        context: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Genera una sugerencia proactiva basada en el contexto del usuario.

        Aplica reglas en orden de prioridad. Si ninguna regla aplica pero el contexto
        sugiere necesidad de ayuda (muchos errores o mucha inactividad), usa LLM fallback.

        Args:
            context: Diccionario con el contexto del usuario. Debe incluir:
                - idleSeconds (int): Segundos de inactividad
                - consecutiveErrors (int): Errores consecutivos
                - progress (dict): {answered, total, percentage}
                - lastAction (str|None): Última acción realizada
                - quizTopic (str): Tema del quiz
                - isIdle (bool): Si el usuario está inactivo
            user_id: ID del usuario para rate limiting (opcional)

        Returns:
            Diccionario con la sugerencia:
                - suggestion_text (str): Texto para TTS
                - action_type (str): Tipo de acción sugerida
                - action_params (dict): Parámetros de la acción
                - priority (str): 'high', 'medium', 'low'
                - reasoning (str): Explicación de por qué se generó
                - source (str): 'rule_based', 'gemini'

            Retorna None si no hay sugerencia o si está rate limited.

        Example:
            >>> engine = SuggestionEngine()
            >>> context = {
            ...     "idleSeconds": 20,
            ...     "consecutiveErrors": 0,
            ...     "progress": {"answered": 0, "total": 10, "percentage": 0},
            ...     "lastAction": None,
            ...     "quizTopic": "Python",
            ...     "isIdle": True
            ... }
            >>> suggestion = engine.generate_suggestion(context, user_id="user123")
            >>> print(suggestion["suggestion_text"])
            "Parece que aún no has empezado. ¿Quieres que te lea la primera pregunta?"
        """
        # Verificar rate limiting
        if self._check_rate_limit(user_id):
            logger.debug(f"Sugerencia bloqueada por rate limit para usuario {user_id}")
            return None

        # Aplicar reglas en orden de prioridad
        rules = [
            self._check_rule_1,
            self._check_rule_3,  # Errores tienen prioridad alta
            self._check_rule_2,
            self._check_rule_5,
            self._check_rule_4,
        ]

        for rule in rules:
            try:
                suggestion = rule(context)
                if suggestion:
                    logger.info(f"Sugerencia generada: {suggestion['reasoning']}")
                    return suggestion
            except Exception as e:
                logger.error(f"Error aplicando regla {rule.__name__}: {e}")
                continue

        # Si no hay regla aplicable pero hay condiciones que sugieren necesidad de ayuda
        error_rate = context.get("errorRate", 0)
        total_answered = context.get("totalAnswered", 0)
        idle_seconds = context.get("idleSeconds", 0)

        # UPDATED: Usar error_rate en lugar de consecutive_errors
        should_use_llm = (
            ((error_rate >= 0.5 and total_answered >= 3) or idle_seconds > 45)
            and self.use_llm_fallback
        )

        if should_use_llm:
            logger.info("Ninguna regla aplicó, intentando fallback a LLM")
            try:
                suggestion = self._generate_llm_suggestion(context)
                if suggestion:
                    logger.info(f"Sugerencia LLM generada: {suggestion['source']}")
                    return suggestion
            except Exception as e:
                logger.error(f"Error en fallback a LLM: {e}")

        logger.debug("No se generó sugerencia para el contexto actual")
        return None
