// frontend/src/components/AudioPrivacy/AudioConsentModal.jsx

import React, { useState } from 'react';
import './AudioConsentModal.css';

const AudioConsentModal = ({ onAccept, onDecline }) => {
  const [saveAudio, setSaveAudio] = useState(true);
  const [saveTranscriptions, setSaveTranscriptions] = useState(true);

  const handleAccept = () => {
    onAccept({ saveAudio, saveTranscriptions });
  };

  return (
    <div className="audio-consent-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="consent-title">
      <div className="audio-consent-modal">
        <h2 id="consent-title">Privacidad y uso de audio</h2>
        
        <div className="consent-content">
          <p className="consent-intro">
            QuizGenAI utiliza funciones de voz para mejorar tu experiencia de aprendizaje. 
            Te explicamos cómo manejamos tu información de audio:
          </p>

          <div className="consent-section">
            <h3>¿Qué recolectamos?</h3>
            <ul>
              <li>Grabaciones de audio cuando usas comandos de voz</li>
              <li>Transcripciones de texto de tus comandos</li>
              <li>Metadatos básicos (duración, fecha, precisión)</li>
            </ul>
          </div>

          <div className="consent-section">
            <h3>¿Cómo lo usamos?</h3>
            <ul>
              <li>Procesar tus comandos de voz y peticiones</li>
              <li>Mejorar la precisión del reconocimiento</li>
              <li>Generar sugerencias personalizadas</li>
            </ul>
          </div>

          <div className="consent-section">
            <h3>Retención y seguridad</h3>
            <ul>
              <li><strong>Almacenamiento cifrado</strong> de todos los datos de audio</li>
              <li><strong>TTL de 24 horas:</strong> Los datos se eliminan automáticamente después de 24 horas</li>
              <li><strong>Control total:</strong> Puedes eliminar tus datos en cualquier momento</li>
              <li>Redacción automática de información personal identificable (PII)</li>
            </ul>
          </div>

          <div className="consent-options">
            <label className="consent-checkbox">
              <input
                type="checkbox"
                checked={saveAudio}
                onChange={(e) => setSaveAudio(e.target.checked)}
                aria-describedby="save-audio-desc"
              />
              <span>
                <strong>Guardar audio</strong>
                <span id="save-audio-desc" className="option-desc">
                  Permite guardar grabaciones para mejorar la experiencia
                </span>
              </span>
            </label>

            <label className="consent-checkbox">
              <input
                type="checkbox"
                checked={saveTranscriptions}
                onChange={(e) => setSaveTranscriptions(e.target.checked)}
                aria-describedby="save-trans-desc"
              />
              <span>
                <strong>Guardar transcripciones</strong>
                <span id="save-trans-desc" className="option-desc">
                  Permite guardar el texto transcrito de tus comandos
                </span>
              </span>
            </label>
          </div>

          <p className="consent-note">
            ℹ️ Puedes cambiar estas preferencias en cualquier momento desde Configuración.
          </p>
        </div>

        <div className="consent-actions">
          <button 
            className="btn btn-secondary" 
            onClick={onDecline}
            aria-label="Rechazar y no usar funciones de voz"
          >
            No usar voz
          </button>
          <button 
            className="btn btn-primary" 
            onClick={handleAccept}
            aria-label="Aceptar y continuar"
          >
            Aceptar y continuar
          </button>
        </div>

        <a href="/privacy-policy" className="privacy-link" target="_blank" rel="noopener noreferrer">
          Ver política de privacidad completa
        </a>
      </div>
    </div>
  );
};

export default AudioConsentModal;