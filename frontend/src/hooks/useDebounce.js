import { useState, useEffect } from 'react';

/**
 * Hook de debounce para optimizar actualizaciones frecuentes
 * Retrasa la actualización del valor hasta que el usuario deje de escribir
 *
 * @param {any} value - Valor a hacer debounce
 * @param {number} delay - Retraso en milisegundos (default: 500)
 * @returns {any} - Valor con debounce aplicado
 *
 * @example
 * const [text, setText] = useState('');
 * const debouncedText = useDebounce(text, 500);
 *
 * useEffect(() => {
 *   // Este efecto solo se ejecuta 500ms después de que el usuario deje de escribir
 *   saveToBackend(debouncedText);
 * }, [debouncedText]);
 */
export function useDebounce(value, delay = 500) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    // Configura un temporizador para actualizar el valor después del delay
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    // Limpia el temporizador si el valor cambia antes de que expire
    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
}
