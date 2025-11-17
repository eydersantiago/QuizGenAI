/**
 * ImageHistoryGallery - Componente para mostrar el historial de imágenes de portada
 * 
 * Características:
 * - Galería horizontal de thumbnails (máximo 3 imágenes)
 * - Click en thumbnail para revertir a esa imagen
 * - Indicador visual de imagen actual
 * - Animaciones suaves
 */

import React from "react";
import { motion } from "framer-motion";
import { Check } from "lucide-react";
import "../estilos/ImageHistoryGallery.css";

/**
 * Props del componente:
 * @param {Array} history - Array de objetos {path, url} con las imágenes del historial
 * @param {String} currentImageUrl - URL de la imagen actualmente activa
 * @param {Function} onSelectImage - Callback cuando se selecciona una imagen del historial (url, path)
 */
export default function ImageHistoryGallery({
  history = [],
  currentImageUrl,
  onSelectImage
}) {
  if (!history || history.length === 0) {
    return null;
  }

  const handleImageClick = (imageData) => {
    if (onSelectImage) {
      onSelectImage(imageData.url, imageData.path);
    }
  };

  return (
    <div className="image-history-gallery">
      <div className="gallery-header">
        <span className="gallery-title">Historial de imágenes</span>
        <span className="gallery-subtitle">Haz clic para revertir a una imagen anterior</span>
      </div>
      
      <div className="gallery-thumbnails">
        {history.map((imageData, index) => {
          const isCurrent = imageData.url === currentImageUrl;
          
          return (
            <motion.div
              key={imageData.path || index}
              className={`thumbnail-container ${isCurrent ? 'current' : ''}`}
              onClick={() => !isCurrent && handleImageClick(imageData)}
              whileHover={!isCurrent ? { scale: 1.05 } : {}}
              whileTap={!isCurrent ? { scale: 0.95 } : {}}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1 }}
            >
              <div className="thumbnail-image-wrapper">
                <img
                  src={imageData.url}
                  alt={`Imagen anterior ${index + 1}`}
                  className="thumbnail-image"
                  loading="lazy"
                />
                {isCurrent && (
                  <div className="current-badge">
                    <Check size={16} />
                    <span>Actual</span>
                  </div>
                )}
                {!isCurrent && (
                  <div className="hover-overlay">
                    <span>Haz clic para usar esta imagen</span>
                  </div>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

