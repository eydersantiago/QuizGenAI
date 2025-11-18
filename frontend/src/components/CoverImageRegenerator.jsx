/**
 * CoverImageRegenerator - Componente para regenerar la imagen de portada del quiz
 * 
 * Características:
 * - Botón de regeneración con contador de intentos
 * - Estado de carga durante regeneración
 * - Manejo de errores
 * - Integración con historial de imágenes
 */

import React, { useState } from "react";
import { RefreshCw, Loader2, AlertCircle } from "lucide-react";
import Swal from "sweetalert2";
import "../estilos/CoverImageRegenerator.css";

const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:8000/api";

/**
 * Props del componente:
 * @param {String} sessionId - ID de la sesión
 * @param {String} currentImageUrl - URL de la imagen actual
 * @param {Number} regenerationCount - Número de regeneraciones realizadas
 * @param {Number} remainingAttempts - Intentos restantes
 * @param {Function} onRegenerate - Callback cuando se regenera exitosamente (imageUrl, count, remaining, history)
 * @param {String} topic - Tema del quiz (para mensajes)
 */
export default function CoverImageRegenerator({
  sessionId,
  currentImageUrl,
  regenerationCount = 0,
  remainingAttempts = 3,
  onRegenerate,
  topic = "Quiz"
}) {
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [error, setError] = useState(null);

  const handleRegenerate = async () => {
    if (remainingAttempts <= 0) {
      Swal.fire({
        icon: "warning",
        title: "Límite alcanzado",
        text: "Has alcanzado el límite de 3 regeneraciones por sesión.",
        confirmButtonText: "OK"
      });
      return;
    }

    if (!sessionId) {
      Swal.fire({
        icon: "error",
        title: "Error",
        text: "No se encontró la sesión del quiz.",
        confirmButtonText: "OK"
      });
      return;
    }

    setIsRegenerating(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/sessions/${sessionId}/regenerate-cover/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.message || data.error || "Error al regenerar la imagen");
      }

      if (data.success) {
        Swal.fire({
          icon: "success",
          title: "Imagen regenerada",
          text: `Nueva ilustración generada para "${topic}". ${data.remaining} intentos restantes.`,
          timer: 2000,
          showConfirmButton: false
        });

        // Llamar callback con los nuevos datos
        if (onRegenerate) {
          onRegenerate(data.image_url, data.count, data.remaining, data.history || []);
        }
      } else {
        throw new Error(data.message || "Error al regenerar la imagen");
      }
    } catch (error) {
      console.error("[CoverImageRegenerator] Error:", error);
      setError(error.message);
      
      Swal.fire({
        icon: "error",
        title: "Error al regenerar",
        text: error.message || "No se pudo generar la nueva imagen. Intenta de nuevo más tarde.",
        confirmButtonText: "OK"
      });
    } finally {
      setIsRegenerating(false);
    }
  };

  const isDisabled = isRegenerating || remainingAttempts <= 0;

  return (
    <div className="cover-regenerator-container">
      <button
        className={`cover-regenerate-btn ${isDisabled ? 'disabled' : ''} ${isRegenerating ? 'loading' : ''}`}
        onClick={handleRegenerate}
        disabled={isDisabled}
        aria-label={`Regenerar imagen de portada. ${remainingAttempts} intentos restantes.`}
        title={remainingAttempts <= 0 ? "Límite de regeneraciones alcanzado" : `Regenerar imagen (${remainingAttempts} intentos restantes)`}
      >
        {isRegenerating ? (
          <>
            <Loader2 className="spinning" size={18} />
            <span>Generando nueva ilustración...</span>
          </>
        ) : (
          <>
            <RefreshCw size={18} />
            <span>Regenerar Imagen</span>
          </>
        )}
      </button>

      <div className="regeneration-counter">
        <span className="counter-label">Intentos restantes:</span>
        <span className={`counter-value ${remainingAttempts === 0 ? 'zero' : ''}`}>
          {remainingAttempts} / 3
        </span>
      </div>

      {error && (
        <div className="regeneration-error" role="alert">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}

