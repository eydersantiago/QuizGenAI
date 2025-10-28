import { useEffect, useCallback, useRef } from 'react';

/**
 * Hook para sincronizar estado entre múltiples pestañas del navegador
 * Previene conflictos cuando el usuario edita el mismo quiz en varias pestañas
 *
 * @param {string} sessionId - ID de la sesión para identificar el quiz
 * @param {Array} questions - Array de preguntas actual
 * @param {Function} onSync - Callback cuando se reciben cambios de otra pestaña
 * @returns {Object} - Funciones para sincronizar y bloquear edición
 */
export function useMultiTabSync(sessionId, questions, onSync) {
  const channelRef = useRef(null);
  const lastSyncTimeRef = useRef(Date.now());
  const isThisTabActiveRef = useRef(true);

  // Inicializar BroadcastChannel
  useEffect(() => {
    if (!sessionId) return;

    const channel = new BroadcastChannel(`quiz-editor-${sessionId}`);
    channelRef.current = channel;

    // Escuchar mensajes de otras pestañas
    channel.onmessage = (event) => {
      const { type, data, timestamp, tabId } = event.data;

      // Ignorar mensajes de esta misma pestaña
      if (tabId === getTabId()) return;

      switch (type) {
        case 'QUESTIONS_UPDATED':
          // Solo sincronizar si el mensaje es más reciente
          if (timestamp > lastSyncTimeRef.current) {
            lastSyncTimeRef.current = timestamp;
            onSync?.(data.questions);
          }
          break;

        case 'TAB_ACTIVATED':
          // Otra pestaña tomó el control
          isThisTabActiveRef.current = false;
          break;

        case 'REQUEST_SYNC':
          // Otra pestaña solicita el estado actual
          broadcastQuestions(questions);
          break;

        default:
          break;
      }
    };

    // Solicitar sincronización al abrir
    channel.postMessage({
      type: 'REQUEST_SYNC',
      timestamp: Date.now(),
      tabId: getTabId(),
    });

    // Marcar esta pestaña como activa
    markTabActive();

    return () => {
      channel.close();
    };
  }, [sessionId, onSync]);

  // Sincronizar con localStorage como fallback
  useEffect(() => {
    if (!sessionId) return;

    const storageKey = `quiz-editor-${sessionId}`;

    const handleStorageChange = (e) => {
      if (e.key === storageKey && e.newValue) {
        try {
          const data = JSON.parse(e.newValue);
          if (data.timestamp > lastSyncTimeRef.current) {
            lastSyncTimeRef.current = data.timestamp;
            onSync?.(data.questions);
          }
        } catch (error) {
          console.error('Error parsing localStorage sync:', error);
        }
      }
    };

    window.addEventListener('storage', handleStorageChange);

    return () => {
      window.removeEventListener('storage', handleStorageChange);
    };
  }, [sessionId, onSync]);

  // Función para transmitir cambios a otras pestañas
  const broadcastQuestions = useCallback((updatedQuestions) => {
    if (!sessionId || !channelRef.current) return;

    const timestamp = Date.now();
    lastSyncTimeRef.current = timestamp;

    // BroadcastChannel
    channelRef.current.postMessage({
      type: 'QUESTIONS_UPDATED',
      data: { questions: updatedQuestions },
      timestamp,
      tabId: getTabId(),
    });

    // localStorage como fallback
    try {
      localStorage.setItem(
        `quiz-editor-${sessionId}`,
        JSON.stringify({
          questions: updatedQuestions,
          timestamp,
        })
      );
    } catch (error) {
      console.error('Error saving to localStorage:', error);
    }
  }, [sessionId]);

  // Función para marcar esta pestaña como activa
  const markTabActive = useCallback(() => {
    if (!channelRef.current) return;

    isThisTabActiveRef.current = true;
    channelRef.current.postMessage({
      type: 'TAB_ACTIVATED',
      timestamp: Date.now(),
      tabId: getTabId(),
    });
  }, []);

  // Verificar si esta pestaña es la activa
  const isActiveTab = useCallback(() => {
    return isThisTabActiveRef.current;
  }, []);

  return {
    broadcastQuestions,
    markTabActive,
    isActiveTab,
  };
}

/**
 * Genera un ID único para esta pestaña
 */
function getTabId() {
  if (!window.__quizEditorTabId) {
    window.__quizEditorTabId = `tab-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }
  return window.__quizEditorTabId;
}
