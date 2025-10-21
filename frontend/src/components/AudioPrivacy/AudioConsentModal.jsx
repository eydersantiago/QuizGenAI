// frontend/src/components/AudioPrivacy/AudioConsentModal.jsx

import React from "react";
import "./AudioConsentModal.css";

export default function AudioConsentModal({ onAccept, onDecline }) {
  return (
    <div className="acm-overlay" role="dialog" aria-modal="true" aria-labelledby="acm-title">
      <div className="acm-modal">
        {/* Header */}
        <div className="acm-header">
          <h3 id="acm-title">Privacidad y uso de audio</h3>
        </div>

        {/* Body (scrollable) */}
        <div className="acm-body" tabIndex={0}>
          <p>
            Para habilitar comandos de voz, necesitamos tu consentimiento para procesar audio y
            (opcionalmente) guardar transcripciones. Puedes cambiar estas preferencias en cualquier momento
            en <strong>Configuración &gt; Privacidad de audio</strong>.
          </p>

          <h4>¿Qué se procesa?</h4>
          <ul>
            <li>Fragmentos de audio enviados desde tu micrófono mientras el panel de voz está activo.</li>
            <li>Transcripciones generadas automáticamente para interpretar tus comandos.</li>
          </ul>

          <h4>¿Qué se almacena?</h4>
          <ul>
            <li><strong>Grabaciones de audio</strong>: solo si lo permites en las preferencias.</li>
            <li><strong>Transcripciones</strong>: solo si lo permites en las preferencias.</li>
            <li>Los datos se eliminan automáticamente según la política de retención.</li>
          </ul>

          <h4>Seguridad</h4>
          <ul>
            <li>Cifrado en tránsito y en reposo.</li>
            <li>Redacción automática de información sensible cuando corresponde.</li>
          </ul>

          <h4>Tus controles</h4>
          <ul>
            <li>Desactivar/activar guardado de audio y transcripciones.</li>
            <li>Eliminar sesiones de audio de manera individual o todas a la vez.</li>
          </ul>

          <p>
            Al continuar, aceptas el procesamiento de audio para detectar comandos de voz. El guardado
            de audios/transcripciones es configurable y puedes modificarlo en cualquier momento.
          </p>

          {/* Texto de ejemplo largo para demostrar scroll */}
          <div className="acm-disclaimer">
            <p>
              Nota: si el texto de esta política es extenso, puedes desplazarte dentro de este cuadro
              sin perder de vista los botones de acción. Esta ventana incluye una barra de desplazamiento
              independiente para que puedas revisar todo el contenido antes de aceptar o rechazar.
            </p>
          </div>
        </div>

        {/* Footer (sticky) */}
        <div className="acm-footer">
          <button className="acm-btn acm-btn-secondary" onClick={onDecline}>
            No, gracias
          </button>
          <button
            className="acm-btn acm-btn-primary"
            onClick={() => onAccept?.({ save_audio: true, save_transcriptions: true })}
          >
            Continuar y aceptar
          </button>
        </div>
      </div>
    </div>
  );
}
