// frontend/src/services/intentRouter.js

/**
 * Servicio para procesamiento de intenciones de voz
 * Implementa QGAI-107: Router de intenciones con fallback
 */

import { logIntentEvent } from "./voiceMetricsService";
const API_BASE = process.env.REACT_APP_API_BASE || "/api";


class IntentRouterService {
  constructor() {
    this.baseUrl = `${API_BASE}/intent-router`;
    this.cache = new Map();
    this.cacheTimeout = 5 * 60 * 1000; // 5 minutos
  }

  // Helper interno para llamadas fetch con JSON y manejo de errores
  async _fetch(path, { method = 'GET', data } = {}) {
    const init = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (data !== undefined) init.body = JSON.stringify(data);

    const resp = await fetch(`${this.baseUrl}${path}`, init);
    let json = null;
    try { json = await resp.json(); } catch {}
    if (!resp.ok) {
      const msg = (json && (json.detail || json.error || json.message)) || `HTTP ${resp.status}`;
      const err = new Error(msg);
      err.status = resp.status;
      err.payload = json;
      throw err;
    }
    return json ?? {};
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
      return cached.result;
    }

    try {
      const response = await this._fetch('/parse/', {
        method: 'POST',
        data: { text }
      });

      const result = {
        intent: response.intent,
        confidence: response.confidence,
        slots: response.slots || {},
        backendUsed: response.backend_used,
        latencyMs: response.latency_ms,
        warning: response.warning || null,
        timestamp: Date.now()
      };

      // log de métricas (no bloquea UX)
      logIntentEvent(
        result.intent,
        Number(result.confidence ?? 0),
        String(result.backendUsed || "grammar"),
        Number(result.latencyMs ?? 0),
        result.slots || {},
        { source: "frontend" }
      ).catch(()=>{});

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
      const response = await this._fetch('/batch_parse/', {
        method: 'POST',
        data: { texts }
      });

      return (response.results || []).map(r => ({
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
      const response = await this._fetch('/supported_intents/');
      return response;
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
      const response = await this._fetch('/health/');
      return response;
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

    // Patrones básicos locales (más sinónimos y variantes)
    // Nota: el orden prioriza patrones más específicos primero
    const patterns = {
      // Destructivas / estructurales
      delete_question: /\b(eliminar|borra?r?|borrar|quitar|suprimir|sacar|remover|quita)\b/,
      duplicate_question: /\b(duplicar|clonar|copiar|haz\s+una\s+copia|duplicame|duplicar\s+pregunta)\b/,

      // Export / descargar
      export_pdf: /\b(exportar|exporta|descargar|guardar|generar|imprimir|bajar)\b.*\b(pdf|como pdf|en pdf)\b/,
      export_txt: /\b(exportar|exporta|descargar|guardar|bajar)\b.*\b(txt|texto|txt|archivo de texto)\b/,
      export_quiz: /\b(exportar|exporta|descargar|guardar|bajar|export)\b/,

      // Regenerar / reemplazar
      regenerate_quiz: /\b(regenerar|regenera|vuelve?\s+a\s+generar|volver\s+a\s+crear|reemplazar|sustituir|renovar)\b/,

      // Navegación
      navigate_next: /\b(siguiente|próxima?|continua?r?|adelante|next|avanza|sigue|pasar|pasa)\b/,
      navigate_previous: /\b(anterior|atr[aá]s|volver|back|retrocede|regresa)\b/,

      // Interacción con pregunta
      read_question: /\b(lee?r?|leer|pregunta|leer\s+la\s+pregunta|leer\s+pregunta)\b/,
      show_answers: /\b(muestra?r?|mostrar|ver|respuestas?|opciones|ensena|enséñame)\b/,

      // Generación de quiz
      generate_quiz: /\b(genera?r?|crea?r?|arma?r?|haz|hazme|genera|crea|arma|quiz|cuestionario|test|preguntas)\b/,

      // Repetir / pausa / reanudar
      repeat: /\b(repite?|repetir|otra\s+vez|de\s+nuevo|otra)\b/,
      pause: /\b(pausa?|pausar|detener|detene?r?|stop|para)\b/,
      resume: /\b(continua?r?|reanuda?r?|resume|seguir)\b/,
      skip: /\b(salta?r?|omitir|skip|siguiente)\b/,
      finish: /\b(terminar|finalizar|salir|finish|acabar)\b/,
      slower: /\b(lento|despacio|slower|mas lento|más lento)\b/
    };

    for (const [intent, pattern] of Object.entries(patterns)) {
      if (pattern.test(textLower)) {
        // Extraído simple de slots: número y tema/dificultad para generación
        const slots = {};
        // número: "10 preguntas", "diez preguntas"
        const numMatch = textLower.match(/(\d+)|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez/);
        if (numMatch) {
          let n = numMatch[0];
          // convetir texto a número si es palabra (muy básico)
          const numWords = { uno:1,dos:2,tres:3,cuatro:4,cinco:5,seis:6,siete:7,ocho:8,nueve:9,diez:10 };
          if (isNaN(Number(n))) n = numWords[n] || null;
          slots.count = n ? Number(n) : undefined;
        }
        // tema: "sobre geografía", "de historia"
        const temaMatch = textLower.match(/(?:sobre|de|acerca de)\s+([a-záéíóúñ0-9\s]+)/);
        if (temaMatch) slots.topic = (temaMatch[1] || '').trim();
        // dificultad: normalizar a 'Fácil' | 'Media' | 'Difícil'
        const difMatch = textLower.match(/\b(f(a|á)cil|facil|sencillo|baja\s+dificultad|bajo)\b|\b(medi[oa]|intermedio|intermedia|normal|regular|moderad[oa]|nivel\s+medio)\b|\b(dif(i|í)cil|dificil|complicad[oa]|duro|avanzad[oa]|alta\s+dificultad|experto|profundo)\b/);
        if (difMatch) {
          const hit = difMatch[0];
          if (/\b(f(a|á)cil|facil|sencillo|baja\s+dificultad|bajo)\b/.test(hit)) slots.difficulty = 'Fácil';
          else if (/\b(medi[oa]|intermedio|intermedia|normal|regular|moderad[oa]|nivel\s+medio)\b/.test(hit)) slots.difficulty = 'Media';
          else slots.difficulty = 'Difícil';
        }

        return {
          intent,
          confidence: 0.6,
          slots,
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
