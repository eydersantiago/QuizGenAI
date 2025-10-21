// services/voiceMetricsService.js
// Servicio para registrar eventos de métricas de voz (STT/TTS) en el backend

const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:8000/api";

let currentSessionId = null;

/**
 * Establece el ID de sesión actual para todos los eventos de métricas.
 * @param {string|null} sessionId - UUID de la sesión de audio
 */
export const setVoiceMetricsSession = (sessionId) => {
  currentSessionId = sessionId;
};

/**
 * Registra un evento de métricas de voz en el backend.
 * Falla silenciosamente para no interrumpir la experiencia del usuario.
 *
 * @param {string} eventType - Tipo de evento (e.g., 'stt_final', 'tts_complete')
 * @param {Object} data - Datos adicionales del evento
 * @param {string} [data.session_id] - UUID de la sesión
 * @param {number} [data.latency_ms] - Latencia en milisegundos
 * @param {number} [data.confidence] - Score de confianza (0-1)
 * @param {string} [data.intent] - Intención detectada
 * @param {string} [data.backend_used] - Backend utilizado
 * @param {number} [data.text_length] - Longitud del texto procesado
 * @param {Object} [data.metadata] - Metadatos adicionales
 * @returns {Promise<boolean>} true si el evento se registró exitosamente, false si falló
 */
export const logVoiceEvent = async (eventType, data = {}) => {
  try {
    const payload = {
      event_type: eventType,
      session_id: data.session_id || currentSessionId,
      latency_ms: data.latency_ms,
      confidence: data.confidence,
      intent: data.intent,
      backend_used: data.backend_used,
      text_length: data.text_length,
      metadata: {
        timestamp: Date.now(),
        ...data.metadata,
      },
    };

    // Eliminar campos undefined/null para no enviarlos
    Object.keys(payload).forEach((key) => {
      if (payload[key] === undefined || payload[key] === null) {
        delete payload[key];
      }
    });

    const response = await fetch(`${API_BASE}/voice-metrics/log/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return true;
  } catch (error) {
    // Fail silently en producción, pero logear en desarrollo
    if (process.env.NODE_ENV === 'development') {
      console.error('[VoiceMetrics] Error logging event:', eventType, error);
    }
    return false;
  }
};

/**
 * Registra un evento de Speech-to-Text (STT).
 *
 * @param {string} eventSubtype - Subtipo de evento: 'start', 'partial', 'final', 'error'
 * @param {number} [latencyMs] - Latencia en milisegundos
 * @param {number} [textLength] - Longitud del texto transcrito
 * @param {number} [confidence] - Confianza de la transcripción (0-1)
 * @param {Object} [metadata] - Metadatos adicionales
 * @returns {Promise<boolean>}
 */
export const logSTTEvent = async (
  eventSubtype,
  latencyMs = null,
  textLength = null,
  confidence = null,
  metadata = {}
) => {
  const eventType = `stt_${eventSubtype}`;

  return logVoiceEvent(eventType, {
    latency_ms: latencyMs,
    text_length: textLength,
    confidence: confidence,
    metadata: {
      subtype: eventSubtype,
      ...metadata,
    },
  });
};

/**
 * Registra un evento de Text-to-Speech (TTS).
 *
 * @param {string} eventSubtype - Subtipo de evento: 'start', 'complete', 'error'
 * @param {number} [latencyMs] - Latencia en milisegundos
 * @param {number} [textLength] - Longitud del texto a sintetizar
 * @param {number} [duration] - Duración del audio generado (ms)
 * @param {Object} [metadata] - Metadatos adicionales
 * @returns {Promise<boolean>}
 */
export const logTTSEvent = async (
  eventSubtype,
  latencyMs = null,
  textLength = null,
  duration = null,
  metadata = {}
) => {
  const eventType = `tts_${eventSubtype}`;

  return logVoiceEvent(eventType, {
    latency_ms: latencyMs,
    text_length: textLength,
    metadata: {
      subtype: eventSubtype,
      duration_ms: duration,
      ...metadata,
    },
  });
};

/**
 * Registra un evento de reconocimiento de intención.
 *
 * @param {string} intent - Nombre de la intención reconocida
 * @param {number} confidence - Confianza del reconocimiento (0-1)
 * @param {string} backendUsed - Backend que procesó la intención ('grammar', 'gemini', 'perplexity')
 * @param {number} [latencyMs] - Latencia del procesamiento
 * @param {Object} [slots] - Slots/parámetros extraídos de la intención
 * @param {Object} [metadata] - Metadatos adicionales
 * @returns {Promise<boolean>}
 */
export const logIntentEvent = async (
  intent,
  confidence,
  backendUsed,
  latencyMs = null,
  slots = {},
  metadata = {}
) => {
  return logVoiceEvent('intent_recognized', {
    intent: intent,
    confidence: confidence,
    backend_used: backendUsed,
    latency_ms: latencyMs,
    metadata: {
      slots: slots,
      ...metadata,
    },
  });
};

/**
 * Registra un evento de barge-in (interrupción del usuario durante TTS).
 *
 * @param {number} [ttsInterruptedAt] - Timestamp cuando se interrumpió el TTS
 * @param {Object} [metadata] - Metadatos adicionales
 * @returns {Promise<boolean>}
 */
export const logBargeIn = async (ttsInterruptedAt = null, metadata = {}) => {
  return logVoiceEvent('barge_in', {
    metadata: {
      tts_interrupted_at: ttsInterruptedAt || Date.now(),
      ...metadata,
    },
  });
};

/**
 * Registra un evento de sugerencia proactiva.
 *
 * @param {string} action - Acción: 'shown' o 'accepted'
 * @param {string} [suggestionText] - Texto de la sugerencia
 * @param {Object} [metadata] - Metadatos adicionales (e.g., trigger, context)
 * @returns {Promise<boolean>}
 */
export const logSuggestionEvent = async (
  action,
  suggestionText = null,
  metadata = {}
) => {
  const eventType = `suggestion_${action}`;

  return logVoiceEvent(eventType, {
    text_length: suggestionText ? suggestionText.length : null,
    metadata: {
      suggestion_text: suggestionText,
      action: action,
      ...metadata,
    },
  });
};

/**
 * Registra un evento de fallback (cambio de backend por error o baja confianza).
 *
 * @param {string} fromBackend - Backend original que falló
 * @param {string} toBackend - Backend al que se hizo fallback
 * @param {string} [reason] - Razón del fallback
 * @param {Object} [metadata] - Metadatos adicionales
 * @returns {Promise<boolean>}
 */
export const logFallbackEvent = async (
  fromBackend,
  toBackend,
  reason = null,
  metadata = {}
) => {
  return logVoiceEvent('fallback_triggered', {
    backend_used: toBackend,
    metadata: {
      from_backend: fromBackend,
      to_backend: toBackend,
      reason: reason,
      ...metadata,
    },
  });
};

// Export default con todas las funciones
export default {
  setVoiceMetricsSession,
  logVoiceEvent,
  logSTTEvent,
  logTTSEvent,
  logIntentEvent,
  logBargeIn,
  logSuggestionEvent,
  logFallbackEvent,
};
