// frontend/src/hooks/useVoiceCommands.js

import { useState, useCallback, useEffect } from 'react';
import intentRouter from '../services/intentRouter';

/**
 * Hook para procesamiento de comandos de voz
 * Integra STT + Intent Router + Handlers
 */
export const useVoiceCommands = (handlers = {}) => {
  const [isProcessing, setIsProcessing] = useState(false);
  const [lastIntent, setLastIntent] = useState(null);
  const [error, setError] = useState(null);
  const [backendHealth, setBackendHealth] = useState(null);

  // Check health on mount
  useEffect(() => {
    checkBackendHealth();
  }, []);

  const checkBackendHealth = async () => {
    try {
      const health = await intentRouter.checkHealth();
      setBackendHealth(health);
    } catch (err) {
      console.error('Health check failed:', err);
    }
  };

  /**
   * Procesa un comando de voz transcrito
   */
  const processCommand = useCallback(async (transcribedText) => {
    if (!transcribedText || transcribedText.trim().length === 0) {
      setError('Texto vacío');
      return null;
    }

    setIsProcessing(true);
    setError(null);

    try {
      // 1. Parsear intención
      const result = await intentRouter.parseIntent(transcribedText);
      
      console.log('Intent parsed:', result);
      setLastIntent(result);

      // 2. Ejecutar handler si existe
      if (handlers[result.intent]) {
        await handlers[result.intent](result.slots, result);
      } else if (result.intent === 'unknown') {
        console.warn('Intent not recognized:', transcribedText);
        setError(`No entendí: "${transcribedText}"`);
      }

      return result;

    } catch (err) {
      console.error('Command processing error:', err);
      setError('Error al procesar comando');
      return null;

    } finally {
      setIsProcessing(false);
    }
  }, [handlers]);

  /**
   * Confirma una acción sensible (regenerar, exportar, etc.)
   */
  const confirmAction = useCallback(async (actionName, callback) => {
    const confirmed = window.confirm(
      `¿Estás seguro de ${actionName}? Esta acción no se puede deshacer.`
    );

    if (confirmed && callback) {
      await callback();
    }

    return confirmed;
  }, []);

  return {
    processCommand,
    confirmAction,
    isProcessing,
    lastIntent,
    error,
    backendHealth,
    checkBackendHealth
  };
};