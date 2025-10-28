import { useEffect, useCallback } from 'react';

/**
 * Hook para manejar navegación por teclado en el editor de preguntas
 * Soporta:
 * - Ctrl/Cmd + Flecha Derecha/Izquierda: navegar páginas
 * - Ctrl/Cmd + S: guardar cambios
 * - Esc: cancelar operaciones
 *
 * @param {Object} options - Configuración del hook
 * @param {Function} options.onNextPage - Callback para página siguiente
 * @param {Function} options.onPrevPage - Callback para página anterior
 * @param {Function} options.onSave - Callback para guardar
 * @param {Function} options.onCancel - Callback para cancelar
 * @param {boolean} options.enabled - Si la navegación está habilitada
 * @returns {void}
 */
export function useKeyboardNav({
  onNextPage,
  onPrevPage,
  onSave,
  onCancel,
  enabled = true,
}) {
  const handleKeyDown = useCallback(
    (event) => {
      if (!enabled) return;

      const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
      const isCtrlOrCmd = isMac ? event.metaKey : event.ctrlKey;

      // Ctrl/Cmd + Flecha Derecha: Siguiente página
      if (isCtrlOrCmd && event.key === 'ArrowRight') {
        event.preventDefault();
        onNextPage?.();
        return;
      }

      // Ctrl/Cmd + Flecha Izquierda: Página anterior
      if (isCtrlOrCmd && event.key === 'ArrowLeft') {
        event.preventDefault();
        onPrevPage?.();
        return;
      }

      // Ctrl/Cmd + S: Guardar
      if (isCtrlOrCmd && event.key === 's') {
        event.preventDefault();
        onSave?.();
        return;
      }

      // Esc: Cancelar
      if (event.key === 'Escape') {
        event.preventDefault();
        onCancel?.();
        return;
      }
    },
    [enabled, onNextPage, onPrevPage, onSave, onCancel]
  );

  useEffect(() => {
    if (!enabled) return;

    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [enabled, handleKeyDown]);
}

/**
 * Hook para gestionar el foco en elementos específicos
 * Útil para accesibilidad y navegación por teclado
 *
 * @param {React.RefObject} ref - Referencia al elemento
 * @param {boolean} shouldFocus - Si debe enfocar el elemento
 */
export function useAutoFocus(ref, shouldFocus = false) {
  useEffect(() => {
    if (shouldFocus && ref.current) {
      // Pequeño delay para asegurar que el DOM esté listo
      const timer = setTimeout(() => {
        ref.current?.focus();
      }, 100);

      return () => clearTimeout(timer);
    }
  }, [shouldFocus, ref]);
}
