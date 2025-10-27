import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { logVoiceEvent } from '../services/voiceMetricsService';

/**
 * Custom React Hook para trackear el contexto del usuario en el sistema QuizGenAI.
 *
 * Detecta inactividad, errores consecutivos, acciones del usuario, progreso del quiz,
 * y genera métricas para sugerencias proactivas.
 *
 * @param {Object} options - Opciones de configuración del hook
 * @param {number} [options.idleThreshold=15000] - Umbral de inactividad en milisegundos (por defecto 15 segundos)
 * @param {number} [options.maxErrorsTracked=5] - Número máximo de errores a mantener en el historial
 * @param {string} [options.quizTopic] - Tema actual del quiz
 * @param {number} [options.totalQuestions] - Número total de preguntas en el quiz
 * @param {number} [options.currentQuestion] - Índice de la pregunta actual (0-based)
 *
 * @returns {Object} Objeto con el contexto y funciones de control
 * @returns {Object} returns.context - Contexto actual del usuario con toda la información de tracking
 * @returns {number} returns.context.idleSeconds - Segundos de inactividad del usuario
 * @returns {boolean} returns.context.isIdle - True si el usuario está inactivo (supera el threshold)
 * @returns {number} returns.context.consecutiveErrors - Número de errores consecutivos
 * @returns {string|null} returns.context.lastAction - Última acción realizada ('answer', 'navigate', 'read', etc.)
 * @returns {number} returns.context.lastActionTime - Timestamp de la última acción
 * @returns {string} returns.context.quizTopic - Tema del quiz actual
 * @returns {Object} returns.context.progress - Progreso del quiz
 * @returns {number} returns.context.progress.answered - Número de preguntas respondidas
 * @returns {number} returns.context.progress.total - Total de preguntas
 * @returns {number} returns.context.progress.percentage - Porcentaje de progreso (0-100)
 * @returns {Array} returns.context.errorHistory - Historial de los últimos errores con timestamps
 * @returns {number} returns.context.sessionStartTime - Timestamp de inicio de la sesión
 * @returns {Function} returns.resetIdle - Función para resetear el contador de inactividad
 * @returns {Function} returns.recordError - Función para registrar un error del usuario
 * @returns {Function} returns.recordSuccess - Función para registrar un acierto del usuario
 * @returns {Function} returns.recordAction - Función para registrar una acción genérica
 * @returns {boolean} returns.isIdle - Indicador booleano de si el usuario está inactivo
 * @returns {number} returns.consecutiveErrors - Número de errores consecutivos
 * @returns {Function} returns.clearContext - Función para resetear todo el contexto
 *
 * @example
 * const {
 *   context,
 *   resetIdle,
 *   recordError,
 *   recordSuccess,
 *   recordAction,
 *   isIdle,
 *   consecutiveErrors,
 *   clearContext
 * } = useContextTracker({
 *   idleThreshold: 15000,
 *   maxErrorsTracked: 5,
 *   quizTopic: 'Historia de Colombia',
 *   totalQuestions: 10,
 *   currentQuestion: 3
 * });
 */
const useContextTracker = ({
  idleThreshold = 15000,
  maxErrorsTracked = 5,
  quizTopic = '',
  totalQuestions = 0,
  currentQuestion = 0,
} = {}) => {
  // Generar un sessionId único para esta instancia del hook
  const sessionId = useRef(`ctx_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`);
  const sessionStorageKey = `context_tracker_${sessionId.current}`;

  // Ref para trackear si ya se ha logueado el evento de idle
  const idleEventLogged = useRef(false);

  // Ref para el interval de idle tracking
  const idleIntervalRef = useRef(null);

  /**
   * Carga el contexto inicial desde sessionStorage o crea uno nuevo
   */
  const loadInitialContext = useCallback(() => {
    try {
      const stored = sessionStorage.getItem(sessionStorageKey);
      if (stored) {
        const parsed = JSON.parse(stored);
        // Validar que el contexto almacenado tenga la estructura correcta
        if (parsed && typeof parsed === 'object' && parsed.sessionStartTime) {
          return {
            ...parsed,
            // Asegurar que los campos críticos existan
            idleSeconds: parsed.idleSeconds || 0,
            consecutiveErrors: parsed.consecutiveErrors || 0,
            errorHistory: Array.isArray(parsed.errorHistory) ? parsed.errorHistory : [],
            lastAction: parsed.lastAction || null,
          };
        }
      }
    } catch (error) {
      console.warn('[useContextTracker] Error loading context from sessionStorage:', error);
    }

    // Contexto por defecto
    return {
      idleSeconds: 0,
      isIdle: false,
      consecutiveErrors: 0,
      totalAnswered: 0, // UPDATED: Track total answers
      totalErrors: 0, // UPDATED: Track total errors (not just consecutive)
      errorRate: 0, // UPDATED: Error rate (0-1 decimal)
      lastAction: null,
      lastActionTime: Date.now(),
      quizTopic: quizTopic || '',
      progress: {
        answered: currentQuestion || 0,
        total: totalQuestions || 0,
        percentage: 0,
      },
      errorHistory: [],
      sessionStartTime: Date.now(),
    };
  }, [sessionStorageKey, quizTopic, totalQuestions, currentQuestion]);

  // Estado principal del contexto
  const [context, setContext] = useState(loadInitialContext);

  /**
   * Calcula el porcentaje de progreso, manejando edge cases
   */
  const calculateProgress = useCallback((answered, total) => {
    if (!total || total <= 0) return 0;
    if (!answered || answered < 0) return 0;

    const percentage = (answered / total) * 100;
    return Math.min(Math.max(percentage, 0), 100); // Clamp entre 0 y 100
  }, []);

  /**
   * Resetea el contador de inactividad a cero.
   * Debe llamarse cada vez que el usuario interactúa con la aplicación.
   *
   * @example
   * resetIdle(); // Resetea el contador cuando el usuario hace click
   */
  const resetIdle = useCallback(() => {
    setContext((prev) => ({
      ...prev,
      idleSeconds: 0,
      isIdle: false,
    }));
    idleEventLogged.current = false;
  }, []);

  /**
   * Registra un error del usuario e incrementa el contador de errores consecutivos.
   * Mantiene un historial de los últimos N errores según maxErrorsTracked.
   *
   * @param {Object} errorDetails - Detalles adicionales del error (opcional)
   * @param {string} [errorDetails.questionId] - ID de la pregunta donde ocurrió el error
   * @param {string} [errorDetails.userAnswer] - Respuesta incorrecta del usuario
   * @param {string} [errorDetails.correctAnswer] - Respuesta correcta
   *
   * @example
   * recordError({ questionId: 'q1', userAnswer: 'B', correctAnswer: 'A' });
   */
  const recordError = useCallback((errorDetails = {}) => {
    const timestamp = Date.now();

    setContext((prev) => {
      const newErrorHistory = [
        { timestamp, ...errorDetails },
        ...prev.errorHistory,
      ].slice(0, maxErrorsTracked);

      return {
        ...prev,
        consecutiveErrors: prev.consecutiveErrors + 1,
        errorHistory: newErrorHistory,
        lastAction: 'answer',
        lastActionTime: timestamp,
        idleSeconds: 0,
        isIdle: false,
      };
    });

    idleEventLogged.current = false;
  }, [maxErrorsTracked]);

  /**
   * Registra un acierto del usuario y resetea el contador de errores consecutivos.
   *
   * @param {Object} successDetails - Detalles adicionales del acierto (opcional)
   * @param {string} [successDetails.questionId] - ID de la pregunta respondida correctamente
   * @param {string} [successDetails.userAnswer] - Respuesta correcta del usuario
   *
   * @example
   * recordSuccess({ questionId: 'q1', userAnswer: 'A' });
   */
  const recordSuccess = useCallback((successDetails = {}) => {
    const timestamp = Date.now();

    setContext((prev) => ({
      ...prev,
      consecutiveErrors: 0,
      lastAction: 'answer',
      lastActionTime: timestamp,
      idleSeconds: 0,
      isIdle: false,
    }));

    idleEventLogged.current = false;
  }, []);

  /**
   * UPDATED: Registra una respuesta del usuario y actualiza estadísticas de error.
   *
   * Esta función es más inteligente que recordError/recordSuccess porque mantiene
   * estadísticas completas de error rate para detección de patrones de dificultad.
   *
   * @param {boolean} isCorrect - Si la respuesta fue correcta o no
   * @param {Object} answerDetails - Detalles adicionales de la respuesta (opcional)
   * @param {string} [answerDetails.questionId] - ID de la pregunta respondida
   * @param {string} [answerDetails.userAnswer] - Respuesta del usuario
   * @param {string} [answerDetails.correctAnswer] - Respuesta correcta
   *
   * @example
   * recordAnswer(true, { questionId: 'q1', userAnswer: 'A' });
   * recordAnswer(false, { questionId: 'q2', userAnswer: 'B', correctAnswer: 'A' });
   */
  const recordAnswer = useCallback((isCorrect, answerDetails = {}) => {
    const timestamp = Date.now();

    setContext((prev) => {
      // Calcular nuevos totales
      const newTotalAnswered = prev.totalAnswered + 1;
      const newTotalErrors = isCorrect ? prev.totalErrors : prev.totalErrors + 1;
      const newConsecutiveErrors = isCorrect ? 0 : prev.consecutiveErrors + 1;

      // Calcular error rate (evitar división por cero)
      const newErrorRate = newTotalAnswered > 0
        ? newTotalErrors / newTotalAnswered
        : 0;

      // Actualizar historial de errores si es incorrecto
      let newErrorHistory = prev.errorHistory;
      if (!isCorrect) {
        newErrorHistory = [
          { timestamp, ...answerDetails },
          ...prev.errorHistory,
        ].slice(0, maxErrorsTracked);
      }

      return {
        ...prev,
        totalAnswered: newTotalAnswered,
        totalErrors: newTotalErrors,
        errorRate: newErrorRate,
        consecutiveErrors: newConsecutiveErrors,
        errorHistory: newErrorHistory,
        lastAction: 'answer',
        lastActionTime: timestamp,
        idleSeconds: 0,
        isIdle: false,
      };
    });

    idleEventLogged.current = false;
  }, [maxErrorsTracked]);

  /**
   * Registra una acción genérica del usuario.
   *
   * @param {string} actionType - Tipo de acción ('navigate', 'read', 'export', 'help', etc.)
   * @param {Object} actionDetails - Detalles adicionales de la acción (opcional)
   *
   * @example
   * recordAction('navigate', { to: 'next-question' });
   * recordAction('read', { questionId: 'q2' });
   * recordAction('export', { format: 'pdf' });
   */
  const recordAction = useCallback((actionType, actionDetails = {}) => {
    const timestamp = Date.now();

    setContext((prev) => ({
      ...prev,
      lastAction: actionType || null,
      lastActionTime: timestamp,
      idleSeconds: 0,
      isIdle: false,
    }));

    idleEventLogged.current = false;
  }, []);

  /**
   * Resetea todo el contexto a su estado inicial.
   * Limpia el sessionStorage y reinicia todos los contadores.
   *
   * @example
   * clearContext(); // Limpia todo al finalizar el quiz
   */
  const clearContext = useCallback(() => {
    try {
      sessionStorage.removeItem(sessionStorageKey);
    } catch (error) {
      console.warn('[useContextTracker] Error clearing sessionStorage:', error);
    }

    setContext({
      idleSeconds: 0,
      isIdle: false,
      consecutiveErrors: 0,
      totalAnswered: 0, // UPDATED: Reset answer stats
      totalErrors: 0, // UPDATED: Reset error stats
      errorRate: 0, // UPDATED: Reset error rate
      lastAction: null,
      lastActionTime: Date.now(),
      quizTopic: quizTopic || '',
      progress: {
        answered: 0,
        total: totalQuestions || 0,
        percentage: 0,
      },
      errorHistory: [],
      sessionStartTime: Date.now(),
    });

    idleEventLogged.current = false;
  }, [sessionStorageKey, quizTopic, totalQuestions]);

  // Actualizar el progreso cuando cambien las props
  useEffect(() => {
    setContext((prev) => {
      const answered = currentQuestion || 0;
      const total = totalQuestions || 0;
      const percentage = calculateProgress(answered, total);

      return {
        ...prev,
        quizTopic: quizTopic || prev.quizTopic,
        progress: {
          answered,
          total,
          percentage,
        },
      };
    });
  }, [currentQuestion, totalQuestions, quizTopic, calculateProgress]);

  // Lógica de tracking de inactividad con setInterval
  useEffect(() => {
    // Iniciar el interval que incrementa el contador cada segundo
    idleIntervalRef.current = setInterval(() => {
      setContext((prev) => {
        const newIdleSeconds = prev.idleSeconds + 1;
        const newIsIdle = newIdleSeconds * 1000 >= idleThreshold;

        // Si acabamos de superar el threshold y no hemos logueado aún
        if (newIsIdle && !idleEventLogged.current) {
          idleEventLogged.current = true;

          // Log del evento de idle (fire and forget)
          logVoiceEvent('user_idle_detected', {
            metadata: {
              idle_seconds: newIdleSeconds,
              idle_threshold_ms: idleThreshold,
              quiz_topic: prev.quizTopic,
              consecutive_errors: prev.consecutiveErrors,
              last_action: prev.lastAction,
              progress_percentage: prev.progress.percentage,
              session_id: sessionId.current,
            },
          }).catch((error) => {
            if (process.env.NODE_ENV === 'development') {
              console.warn('[useContextTracker] Error logging idle event:', error);
            }
          });
        }

        return {
          ...prev,
          idleSeconds: newIdleSeconds,
          isIdle: newIsIdle,
        };
      });
    }, 1000); // Cada segundo

    // Cleanup: detener el interval al desmontar
    return () => {
      if (idleIntervalRef.current) {
        clearInterval(idleIntervalRef.current);
        idleIntervalRef.current = null;
      }
    };
  }, [idleThreshold]);

  // Persistir el contexto en sessionStorage cada vez que cambie
  useEffect(() => {
    try {
      sessionStorage.setItem(sessionStorageKey, JSON.stringify(context));
    } catch (error) {
      console.warn('[useContextTracker] Error saving context to sessionStorage:', error);
    }
  }, [context, sessionStorageKey]);

  // Valores derivados memorizados
  const isIdle = useMemo(() => context.isIdle, [context.isIdle]);
  const consecutiveErrors = useMemo(() => context.consecutiveErrors, [context.consecutiveErrors]);
  const errorRate = useMemo(() => context.errorRate, [context.errorRate]); // UPDATED: Expose error rate
  const totalAnswered = useMemo(() => context.totalAnswered, [context.totalAnswered]); // UPDATED: Expose total answered

  // Retornar el objeto con el contexto y las funciones de control
  return {
    context,
    resetIdle,
    recordError, // Mantener para compatibilidad
    recordSuccess, // Mantener para compatibilidad
    recordAnswer, // UPDATED: Nueva función recomendada
    recordAction,
    isIdle,
    consecutiveErrors,
    errorRate, // UPDATED: Exponer error rate directamente
    totalAnswered, // UPDATED: Exponer total answered directamente
    clearContext,
  };
};

export default useContextTracker;
