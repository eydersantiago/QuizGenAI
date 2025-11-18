/**
 * QuizCoverImage - Componente para mostrar la imagen de portada del quiz
 * 
 * Características:
 * - Lazy loading nativo para optimizar carga
 * - Fallback a placeholder SVG genérico si no existe imagen o falla la carga
 * - Caption con tema del quiz debajo de la imagen
 * - Layout responsive (mobile, tablet, desktop)
 * - Manejo de errores robusto
 * - Estados de loading y error
 */

import React, { useState, useMemo, useEffect, useRef } from "react";

const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:8000/api";

// SVG Placeholder genérico (data URI inline para evitar requests adicionales)
// Formato rectangular 16:9
const PLACEHOLDER_SVG = `data:image/svg+xml,${encodeURIComponent(`
<svg width="800" height="450" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#7c3aed;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#a855f7;stop-opacity:1" />
    </linearGradient>
  </defs>
  <rect width="800" height="450" fill="url(#grad)"/>
  <g transform="translate(400, 225)">
    <circle cx="0" cy="0" r="50" fill="rgba(255,255,255,0.2)" stroke="rgba(255,255,255,0.4)" stroke-width="2"/>
    <path d="M -25 -20 L 0 5 L 25 -20 M 0 5 L 0 30" stroke="rgba(255,255,255,0.8)" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  </g>
  <text x="400" y="380" font-family="Arial, sans-serif" font-size="18" fill="rgba(255,255,255,0.6)" text-anchor="middle">Ilustración del Quiz</text>
</svg>
`)}`;

/**
 * Props del componente:
 * @param {String} coverImage - Ruta de la imagen (puede ser URL completa o ruta relativa)
 * @param {String} topic - Tema del quiz para el caption
 * @param {String} loading - Tipo de loading ("lazy" | "eager"), por defecto "lazy"
 */
export default function QuizCoverImage({ coverImage, topic, loading = "lazy" }) {
  const [imageError, setImageError] = useState(false);
  const [imageLoading, setImageLoading] = useState(true);
  const imgRef = useRef(null);

  // Construir URL completa de la imagen
  const imageUrl = useMemo(() => {
    if (!coverImage) return null;
    
    // Si ya es una URL completa, usarla directamente
    if (coverImage.startsWith('http://') || coverImage.startsWith('https://')) {
      return coverImage;
    }
    
    // Si es una ruta relativa, construir URL completa
    try {
      const apiOrigin = new URL(API_BASE).origin;
      // Si la ruta ya incluye /media/, usarla directamente
      if (coverImage.startsWith('/media/')) {
        return `${apiOrigin}${coverImage}`;
      }
      // Si es una ruta relativa como "generated/image_123.png", construir URL
      return `${apiOrigin}/media/${coverImage}`;
    } catch (e) {
      console.warn('[QuizCoverImage] Error construyendo URL:', e);
      return coverImage;
    }
  }, [coverImage]);

  // Resetear estados cuando cambia la imagen
  useEffect(() => {
    setImageError(false);
    setImageLoading(true);
  }, [coverImage, imageUrl]);

  // Verificar si la imagen ya está en caché después del render
  useEffect(() => {
    if (imageUrl && imgRef.current) {
      if (imgRef.current.complete && imgRef.current.naturalHeight !== 0) {
        setImageLoading(false);
      }
    }
  }, [imageUrl]);

  const handleImageError = () => {
    console.warn('[QuizCoverImage] Error cargando imagen:', imageUrl);
    setImageError(true);
    setImageLoading(false);
  };

  const handleImageLoad = () => {
    setImageLoading(false);
  };

  return (
    <div className="quiz-cover-container">
      {imageUrl && !imageError ? (
        <>
          <img
            ref={imgRef}
            src={imageUrl}
            alt={`Ilustración del tema: ${topic || 'Quiz'}`}
            loading={loading}
            onError={handleImageError}
            onLoad={handleImageLoad}
            className={`quiz-cover-image ${imageLoading ? 'loading' : ''}`}
            aria-label={`Portada ilustrativa del quiz sobre ${topic || 'el tema'}`}
          />
          {!imageLoading && topic && (
            <p className="quiz-cover-caption">
              Tema: {topic}
            </p>
          )}
        </>
      ) : (
        <div className="quiz-cover-placeholder-container">
          <img
            src={PLACEHOLDER_SVG}
            alt="Placeholder de portada del quiz"
            className="quiz-cover-placeholder"
            aria-label="Imagen de portada no disponible"
          />
          {topic && (
            <p className="quiz-cover-caption">
              Tema: {topic}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

