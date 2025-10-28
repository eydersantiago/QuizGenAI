// components/ProactiveSuggestion.jsx
import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { sendFeedback } from '../services/suggestionService';
import './ProactiveSuggestion.css';

/**
 * Componente de sugerencia proactiva tipo toast notification.
 *
 * Muestra sugerencias contextuales al usuario en la esquina inferior derecha
 * con soporte para TTS, auto-dismiss, y feedback tracking.
 *
 * IMPORTANTE: Este componente usa ReactDOM.createPortal para renderizarse
 * directamente en document.body, evitando así afectar el scroll del documento
 * y asegurando que aparezca como un overlay flotante sin interferir con el
 * flujo del contenido de la página.
 *
 * @param {Object} props - Props del componente
 * @param {Object} props.suggestion - Objeto de sugerencia del backend
 * @param {string} props.suggestion.suggestion_text - Texto de la sugerencia
 * @param {string} props.suggestion.action_type - Tipo de acción sugerida
 * @param {Object} props.suggestion.action_params - Parámetros de la acción
 * @param {string} props.suggestion.priority - Prioridad: 'high', 'medium', 'low'
 * @param {string} props.suggestion.source - Fuente: 'rule_based', 'gemini', 'perplexity'
 * @param {Function} props.onAccept - Callback al aceptar (recibe actionType, params)
 * @param {Function} props.onDismiss - Callback al descartar
 * @param {string} [props.sessionId] - ID de sesión para tracking
 * @param {boolean} [props.ttsEnabled=false] - Si TTS está habilitado
 * @param {boolean} [props.isTTSSpeaking=false] - Si actualmente hay TTS reproduciéndose
 */
const ProactiveSuggestion = ({
  suggestion,
  onAccept,
  onDismiss,
  sessionId = null,
  ttsEnabled = false,
  isTTSSpeaking = false,
}) => {
  // Estados internos
  const [isVisible, setIsVisible] = useState(false);
  const [isAnimating, setIsAnimating] = useState(false);
  const [hasSpokenTTS, setHasSpokenTTS] = useState(false);

  // Refs
  const timeoutIdRef = useRef(null);
  const utteranceRef = useRef(null);

  // Constantes
  const AUTO_DISMISS_DELAY = 30000; // 30 segundos

  /**
   * Obtiene el ícono apropiado según la prioridad
   */
  const getPriorityIcon = () => {
    switch (suggestion?.priority) {
      case 'high':
        return '🔥'; // Fuego para alta prioridad
      case 'medium':
        return '💡'; // Bombilla para media prioridad
      case 'low':
        return 'ℹ️'; // Info para baja prioridad
      default:
        return '💡';
    }
  };

  /**
   * Reproduce el texto de sugerencia usando Web Speech API
   */
  const speakSuggestion = () => {
    // Verificar si Web Speech API está disponible
    if (!('speechSynthesis' in window)) {
      console.warn('[ProactiveSuggestion] Web Speech API no disponible');
      return;
    }

    try {
      // Cancelar cualquier síntesis previa
      window.speechSynthesis.cancel();

      // Crear nueva utterance
      const utterance = new SpeechSynthesisUtterance(suggestion.suggestion_text);
      utteranceRef.current = utterance;

      // Configurar voz española de Colombia
      const voices = window.speechSynthesis.getVoices();
      const esVoice = voices.find(
        (voice) =>
          voice.lang.startsWith('es-CO') || // Preferir Colombia
          voice.lang.startsWith('es-') // Fallback a cualquier español
      );

      if (esVoice) {
        utterance.voice = esVoice;
      }

      // Configurar parámetros
      utterance.lang = 'es-CO';
      utterance.rate = 0.95; // Ligeramente más lento para claridad
      utterance.pitch = 1.0;
      utterance.volume = 0.9;

      // Handlers de eventos
      utterance.onstart = () => {
        console.log('[ProactiveSuggestion] TTS iniciado');
      };

      utterance.onend = () => {
        console.log('[ProactiveSuggestion] TTS finalizado');
        setHasSpokenTTS(true);
      };

      utterance.onerror = (event) => {
        console.error('[ProactiveSuggestion] Error en TTS:', event.error);
        setHasSpokenTTS(true); // Marcar como hablado incluso si falla
      };

      // Iniciar síntesis
      window.speechSynthesis.speak(utterance);
    } catch (error) {
      console.error('[ProactiveSuggestion] Error reproduciendo TTS:', error);
      setHasSpokenTTS(true); // Marcar como hablado para continuar con UI
    }
  };

  /**
   * Maneja la aceptación de la sugerencia
   */
  const handleAccept = async () => {
    try {
      // Cancelar TTS si está activo
      if (utteranceRef.current && window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }

      // Enviar feedback al backend
      await sendFeedback(
        'accepted',
        suggestion.suggestion_text,
        sessionId,
        {
          action_type: suggestion.action_type,
          priority: suggestion.priority,
          source: suggestion.source,
        }
      );

      // Iniciar animación de salida
      setIsAnimating(true);

      // Después de la animación, llamar al callback y ocultar
      setTimeout(() => {
        onAccept(suggestion.action_type, suggestion.action_params);
        setIsVisible(false);
      }, 300); // Duración de la animación de salida
    } catch (error) {
      console.error('[ProactiveSuggestion] Error al aceptar:', error);
      // Continuar con el flujo incluso si falla el feedback
      onAccept(suggestion.action_type, suggestion.action_params);
      setIsVisible(false);
    }
  };

  /**
   * Maneja el descarte/cierre de la sugerencia
   */
  const handleDismiss = async () => {
    try {
      // Cancelar TTS si está activo
      if (utteranceRef.current && window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }

      // Enviar feedback al backend
      await sendFeedback(
        'dismissed',
        suggestion.suggestion_text,
        sessionId,
        {
          action_type: suggestion.action_type,
          priority: suggestion.priority,
          source: suggestion.source,
        }
      );

      // Iniciar animación de salida
      setIsAnimating(true);

      // Después de la animación, llamar al callback y ocultar
      setTimeout(() => {
        onDismiss();
        setIsVisible(false);
      }, 300);
    } catch (error) {
      console.error('[ProactiveSuggestion] Error al descartar:', error);
      // Continuar con el flujo incluso si falla el feedback
      onDismiss();
      setIsVisible(false);
    }
  };

  /**
   * Maneja la tecla ESC para cerrar
   */
  const handleKeyDown = (event) => {
    if (event.key === 'Escape') {
      handleDismiss();
    }
  };

  // Effect: Esperar a que termine TTS antes de mostrar UI
  useEffect(() => {
    if (!suggestion) return;

    // Si TTS está hablando, no mostrar nada aún
    if (isTTSSpeaking) {
      setIsVisible(false);
      return;
    }

    // Si TTS está habilitado pero aún no hemos hablado
    if (ttsEnabled && !hasSpokenTTS) {
      // Pequeño delay para asegurar que las voces estén cargadas
      const voicesLoadedHandler = () => {
        speakSuggestion();
      };

      if (window.speechSynthesis.getVoices().length === 0) {
        // Las voces no están cargadas aún, esperar evento
        window.speechSynthesis.addEventListener('voiceschanged', voicesLoadedHandler, {
          once: true,
        });
      } else {
        // Las voces ya están disponibles
        speakSuggestion();
      }

      return () => {
        window.speechSynthesis.removeEventListener('voiceschanged', voicesLoadedHandler);
      };
    }

    // Si no hay TTS o ya terminó de hablar, mostrar UI
    if (!ttsEnabled || hasSpokenTTS) {
      setIsVisible(true);
    }
  }, [suggestion, ttsEnabled, isTTSSpeaking, hasSpokenTTS]);

  // Effect: Auto-dismiss después de 15 segundos
  useEffect(() => {
    if (!isVisible) return;

    // Configurar timeout para auto-dismiss
    timeoutIdRef.current = setTimeout(() => {
      console.log('[ProactiveSuggestion] Auto-dismiss triggered');
      handleDismiss();
    }, AUTO_DISMISS_DELAY);

    // Cleanup
    return () => {
      if (timeoutIdRef.current) {
        clearTimeout(timeoutIdRef.current);
      }
    };
  }, [isVisible]);

  // Effect: Listener para tecla ESC
  useEffect(() => {
    if (!isVisible) return;

    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isVisible]);

  // Effect: Cleanup al desmontar
  useEffect(() => {
    return () => {
      // Cancelar TTS
      if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }

      // Limpiar timeout
      if (timeoutIdRef.current) {
        clearTimeout(timeoutIdRef.current);
      }
    };
  }, []);

  // No renderizar nada si no hay sugerencia o no es visible
  if (!suggestion || !isVisible) {
    return null;
  }

  // Renderizar usando portal para evitar afectar el scroll del documento
  return createPortal(
    <div
      className={`proactive-suggestion priority-${suggestion.priority} ${isAnimating ? 'animating-out' : ''}`}
      role="alert"
      aria-live="polite"
      aria-atomic="true"
    >
      <div className="suggestion-content">
        {/* Ícono de prioridad */}
        <div className="suggestion-icon" aria-hidden="true">
          {getPriorityIcon()}
        </div>

        {/* Texto de sugerencia */}
        <div className="suggestion-text">
          <p>{suggestion.suggestion_text}</p>
        </div>

        {/* Botón de cerrar */}
        <button
          className="suggestion-close"
          onClick={handleDismiss}
          aria-label="Cerrar sugerencia"
          title="Cerrar (ESC)"
        >
          ✕
        </button>
      </div>

      {/* Botones de acción */}
      <div className="suggestion-actions">
        <button
          className="suggestion-btn suggestion-btn-accept"
          onClick={handleAccept}
        >
          Sí, hazlo
        </button>
        <button
          className="suggestion-btn suggestion-btn-dismiss"
          onClick={handleDismiss}
        >
          No, gracias
        </button>
      </div>

      {/* Indicador de fuente (opcional, solo desarrollo) */}
      {process.env.NODE_ENV === 'development' && (
        <div className="suggestion-debug">
          <small>
            {suggestion.source} • {suggestion.priority}
          </small>
        </div>
      )}
    </div>,
    document.body // Renderizar directamente en el body del documento
  );
};

export default ProactiveSuggestion;
