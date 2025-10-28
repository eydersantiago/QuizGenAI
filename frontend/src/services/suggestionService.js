// services/suggestionService.js
/**
 * Servicio frontend para gestionar sugerencias proactivas en QuizGenAI.
 *
 * Se comunica con el backend para solicitar sugerencias basadas en el contexto
 * del usuario y registrar feedback sobre las sugerencias mostradas.
 */

// Configuración de la API
const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:8000/api";

/**
 * Configuración global para el sistema de sugerencias.
 *
 * @constant {Object} SUGGESTION_CONFIG
 * @property {number} minTimeBetweenSuggestions - Tiempo mínimo entre sugerencias en ms (3 minutos)
 * @property {number} maxSuggestionsPerSession - Número máximo de sugerencias por sesión
 */
export const SUGGESTION_CONFIG = {
  minTimeBetweenSuggestions: 180000, // 3 minutos (180 segundos)
  maxSuggestionsPerSession: 10,
};

/**
 * Solicita una sugerencia proactiva al backend basada en el contexto del usuario.
 *
 * El backend analiza el contexto (inactividad, errores, progreso) y retorna una
 * sugerencia apropiada usando reglas predefinidas o LLM como fallback.
 *
 * Las métricas son registradas automáticamente por el backend, no es necesario
 * llamar a voiceMetricsService desde este servicio.
 *
 * @async
 * @param {Object} context - Contexto del usuario para generar la sugerencia
 * @param {number} context.idleSeconds - Segundos de inactividad
 * @param {number} context.consecutiveErrors - Errores consecutivos
 * @param {string} context.quizTopic - Tema del quiz actual
 * @param {Object} context.progress - Progreso del quiz
 * @param {number} context.progress.answered - Preguntas respondidas
 * @param {number} context.progress.total - Total de preguntas
 * @param {number} context.progress.percentage - Porcentaje de progreso
 * @param {string|null} context.lastAction - Última acción realizada
 * @param {number} context.lastActionTime - Timestamp de última acción
 * @param {boolean} context.isIdle - Si el usuario está inactivo
 * @param {string} [sessionId] - ID de sesión opcional para tracking
 *
 * @returns {Promise<Object|null>} Objeto con la sugerencia o null si no hay sugerencia o error
 * @returns {string} returns.suggestion_text - Texto de la sugerencia para TTS
 * @returns {string} returns.action_type - Tipo de acción sugerida
 * @returns {Object} returns.action_params - Parámetros de la acción
 * @returns {string} returns.priority - Prioridad: 'high', 'medium', 'low'
 * @returns {string} returns.reasoning - Explicación de por qué se generó
 * @returns {string} returns.source - Fuente: 'rule_based', 'gemini', 'perplexity'
 *
 * @example
 * const context = {
 *   idleSeconds: 20,
 *   consecutiveErrors: 0,
 *   quizTopic: "JavaScript Basics",
 *   progress: { answered: 0, total: 10, percentage: 0 },
 *   lastAction: null,
 *   lastActionTime: Date.now(),
 *   isIdle: true
 * };
 *
 * const suggestion = await requestSuggestion(context, 'session-123');
 * if (suggestion) {
 *   console.log(suggestion.suggestion_text);
 *   // "Parece que aún no has empezado. ¿Quieres que te lea la primera pregunta?"
 * }
 */
export const requestSuggestion = async (context, sessionId = null) => {
  try {
    // Construir el body del request
    const body = {
      context: context,
    };

    // Agregar session_id si se proporciona
    if (sessionId) {
      body.session_id = sessionId;
    }

    // Hacer POST al endpoint de sugerencias
    const response = await fetch(`${API_BASE}/suggestions/next/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    // Si la respuesta no es exitosa, retornar null
    if (!response.ok) {
      console.error(
        `[SuggestionService] Error del servidor: ${response.status} ${response.statusText}`
      );
      return null;
    }

    // Parsear el JSON de respuesta
    const data = await response.json();

    // El backend retorna { suggestion: {...} } o { suggestion: null }
    // Retornar el objeto suggestion directamente, o null si no hay
    return data.suggestion || null;

  } catch (error) {
    // Log del error sin lanzar excepción (fail silently)
    console.error('[SuggestionService] Error solicitando sugerencia:', error);
    return null;
  }
};

/**
 * Envía feedback sobre una sugerencia mostrada al usuario.
 *
 * Registra si el usuario aceptó o descartó la sugerencia. El backend
 * crea automáticamente eventos de métricas (suggestion_accepted o
 * suggestion_dismissed) para análisis posterior.
 *
 * @async
 * @param {string} action - Acción realizada: "accepted" o "dismissed"
 * @param {string} suggestionText - Texto de la sugerencia que se mostró
 * @param {string} [sessionId] - ID de sesión opcional para tracking
 * @param {Object} [additionalData] - Datos adicionales opcionales
 * @param {string} [additionalData.action_type] - Tipo de acción de la sugerencia
 * @param {string} [additionalData.priority] - Prioridad de la sugerencia
 * @param {string} [additionalData.source] - Fuente de la sugerencia
 * @param {string} [additionalData.user_action] - Acción específica del usuario tras aceptar
 *
 * @returns {Promise<boolean>} true si el feedback se registró exitosamente, false si falló
 *
 * @example
 * // Usuario acepta la sugerencia
 * const success = await sendFeedback(
 *   'accepted',
 *   '¿Quieres que te lea la primera pregunta?',
 *   'session-123',
 *   { action_type: 'read_question', priority: 'high', source: 'rule_based' }
 * );
 *
 * // Usuario descarta la sugerencia
 * await sendFeedback('dismissed', 'Texto de sugerencia', 'session-123');
 */
export const sendFeedback = async (
  action,
  suggestionText,
  sessionId = null,
  additionalData = {}
) => {
  try {
    // Validar que action sea válido
    if (!['accepted', 'dismissed'].includes(action)) {
      console.error(
        `[SuggestionService] Acción inválida: ${action}. Debe ser 'accepted' o 'dismissed'`
      );
      return false;
    }

    // Construir el body del request
    const body = {
      action: action,
      suggestion_text: suggestionText,
    };

    // Agregar session_id si se proporciona
    if (sessionId) {
      body.session_id = sessionId;
    }

    // Agregar datos adicionales si se proporcionan
    if (additionalData.action_type) {
      body.action_type = additionalData.action_type;
    }
    if (additionalData.priority) {
      body.priority = additionalData.priority;
    }
    if (additionalData.source) {
      body.source = additionalData.source;
    }
    if (additionalData.user_action) {
      body.user_action = additionalData.user_action;
    }

    // Hacer POST al endpoint de feedback
    const response = await fetch(`${API_BASE}/suggestions/feedback/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    // Verificar si fue exitoso
    if (!response.ok) {
      console.error(
        `[SuggestionService] Error registrando feedback: ${response.status} ${response.statusText}`
      );
      return false;
    }

    // Parsear respuesta para confirmar
    const data = await response.json();

    if (data.status === 'logged') {
      return true;
    }

    return false;

  } catch (error) {
    // Log del error sin lanzar excepción
    console.error('[SuggestionService] Error enviando feedback:', error);
    return false;
  }
};

/**
 * Determina si se debe mostrar una nueva sugerencia basándose en el tiempo
 * transcurrido desde la última sugerencia.
 *
 * Implementa throttling para evitar mostrar demasiadas sugerencias al usuario
 * en poco tiempo. El tiempo mínimo está definido en SUGGESTION_CONFIG.
 *
 * @param {number|null|undefined} lastSuggestionTime - Timestamp de la última sugerencia mostrada
 * @returns {boolean} true si se puede mostrar una nueva sugerencia, false si debe esperar
 *
 * @example
 * // Primera sugerencia (sin lastSuggestionTime)
 * const canShow = shouldShowSuggestion(null);
 * // true
 *
 * // Intentar mostrar otra sugerencia 10 segundos después
 * const now = Date.now();
 * const canShowAgain = shouldShowSuggestion(now - 10000);
 * // false (debe esperar 30 segundos)
 *
 * // Intentar 35 segundos después
 * const canShowLater = shouldShowSuggestion(now - 35000);
 * // true (han pasado más de 30 segundos)
 */
export const shouldShowSuggestion = (lastSuggestionTime) => {
  // Si no hay timestamp previo, permitir mostrar sugerencia
  if (!lastSuggestionTime) {
    return true;
  }

  // Calcular tiempo transcurrido desde la última sugerencia
  const timeElapsed = Date.now() - lastSuggestionTime;

  // Retornar true si ha pasado el tiempo mínimo requerido
  return timeElapsed >= SUGGESTION_CONFIG.minTimeBetweenSuggestions;
};

/**
 * Exportación por defecto con todas las funciones y configuración.
 *
 * @example
 * import suggestionService from './services/suggestionService';
 *
 * const suggestion = await suggestionService.requestSuggestion(context);
 * await suggestionService.sendFeedback('accepted', suggestion.suggestion_text);
 *
 * if (suggestionService.shouldShowSuggestion(lastTime)) {
 *   // Mostrar sugerencia
 * }
 */
export default {
  requestSuggestion,
  sendFeedback,
  shouldShowSuggestion,
  SUGGESTION_CONFIG,
};
