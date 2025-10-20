// frontend/src/services/intentRouter.js

import axios from 'axios';

/**
 * Servicio para procesamiento de intenciones de voz
 * Implementa QGAI-107: Router de intenciones con fallback
 */
class IntentRouterService {
  constructor() {
    this.baseUrl = '/api/intent-router';
    this.cache = new Map();
    this.cacheTimeout = 5 * 60 * 1000; // 5 minutos
  }

  /**
   * Parsea un comando de voz y retorna la intención
   * @param {string} text - Texto transcrito del comando
   * @returns {Promise<IntentResult>}
   */
  async parseIntent(text) {
    if (!text || text.trim().length === 0) {
      return this._createErrorResult('Texto vacío');
    }

    // Check cache primero
    const cacheKey = text.toLowerCase().trim();
    const cached = this.cache.get(cacheKey);
    if (cached && Date.now() - cached.timestamp < this.cacheTimeout) {
      console.log('Intent cache hit:', cacheKey);
      return cached.result;
    }

    try {
      const response = await axios.post(`${this.baseUrl}/parse/`, {
        text: text
      });

      const result = {
        intent: response.data.intent,
        confidence: response.data.confidence,
        slots: response.data.slots || {},
        backendUsed: response.data.backend_used,
        latencyMs: response.data.latency_ms,
        warning: response.data.warning || null,
        timestamp: Date.now()
      };

      // Cache result
      this.cache.set(cacheKey, {
        result,
        timestamp: Date.now()
      });

      // Analytics event
      this._trackIntent(result);

      return result;

    } catch (error) {
      console.error('Intent parsing error:', error);
      
      // Fallback local básico
      return this._localFallback(text);
    }
  }

  /**
   * Parsea múltiples comandos en batch
   * @param {string[]} texts - Array de textos
   * @returns {Promise<IntentResult[]>}
   */
  async parseBatch(texts) {
    if (!Array.isArray(texts) || texts.length === 0) {
      return [];
    }

    try {
      const response = await axios.post(`${this.baseUrl}/batch_parse/`, {
        texts: texts
      });

      return response.data.results.map(r => ({
        text: r.text,
        intent: r.intent,
        confidence: r.confidence,
        slots: r.slots || {},
        backendUsed: r.backend_used,
        latencyMs: r.latency_ms
      }));

    } catch (error) {
      console.error('Batch parsing error:', error);
      
      // Fallback: parsear uno por uno localmente
      return texts.map(text => this._localFallback(text));
    }
  }

  /**
   * Obtiene lista de intents soportados
   * @returns {Promise<Object>}
   */
  async getSupportedIntents() {
    try {
      const response = await axios.get(`${this.baseUrl}/supported_intents/`);
      return response.data;
    } catch (error) {
      console.error('Error fetching supported intents:', error);
      return { intents: {} };
    }
  }

  /**
   * Verifica salud de los backends
   * @returns {Promise<Object>}
   */
  async checkHealth() {
    try {
      const response = await axios.get(`${this.baseUrl}/health/`);
      return response.data;
    } catch (error) {
      console.error('Health check error:', error);
      return {
        status: 'error',
        backends: {
          grammar: 'unknown',
          gemini: 'unknown',
          perplexity: 'unknown'
        }
      };
    }
  }

  /**
   * Fallback local usando patrones simples
   * @private
   */
  _localFallback(text) {
    const textLower = text.toLowerCase().trim();
    
    // Patrones básicos locales
    const patterns = {
      navigate_next: /siguiente|próxima?|continua?r?|adelante|next|avanza|sigue/,
      navigate_previous: /anterior|atrás|volver|back/,
      generate_quiz: /genera?|crea?|arma|haz|hazme|quiz|cuestionario|test/,
      read_question: /lee?|leer|pregunta/,
      show_answers: /muestra?|mostrar|ver|respuestas?|opciones/,
      repeat: /repite?|repetir|otra\s+vez|de\s+nuevo/,
      pause: /pausa?|pausar|detene?r?|stop/,
      resume: /continua?r?|reanuda?r?|resume/,
      skip: /salta?r?|omitir|skip/,
      finish: /terminar|finalizar|salir|finish/,
      slower: /lento|despacio|slower/
    };

    for (const [intent, pattern] of Object.entries(patterns)) {
      if (pattern.test(textLower)) {
        return {
          intent,
          confidence: 0.6,
          slots: {},
          backendUsed: 'local_fallback',
          latencyMs: 0,
          warning: 'Using local fallback'
        };
      }
    }

    return {
      intent: 'unknown',
      confidence: 0.0,
      slots: {},
      backendUsed: 'local_fallback',
      latencyMs: 0,
      warning: 'Intent not recognized'
    };
  }

  /**
   * Crea un resultado de error
   * @private
   */
  _createErrorResult(message) {
    return {
      intent: 'unknown',
      confidence: 0.0,
      slots: {},
      backendUsed: 'error',
      latencyMs: 0,
      warning: message
    };
  }

  /**
   * Trackea evento de intención en analytics
   * @private
   */
  _trackIntent(result) {
    // Integración con analytics (PostHog, GA4, etc.)
    if (window.analytics) {
      window.analytics.track('Intent Recognized', {
        intent: result.intent,
        confidence: result.confidence,
        backend: result.backendUsed,
        latency_ms: result.latencyMs,
        has_warning: !!result.warning
      });
    }
  }

  /**
   * Limpia la caché
   */
  clearCache() {
    this.cache.clear();
  }
}

// Singleton instance
const intentRouter = new IntentRouterService();

export default intentRouter;
