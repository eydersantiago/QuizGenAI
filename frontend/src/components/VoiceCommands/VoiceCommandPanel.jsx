// frontend/src/components/VoiceCommands/VoiceCommandPanel.jsx

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useVoiceCommands } from '../../hooks/useVoiceCommands';
import intentRouter from '../../services/intentRouter';
import AudioConsentModal from '../AudioPrivacy/AudioConsentModal';
import "../../estilos/VoiceCommandPanel.css";

const VoiceCommandPanel = ({ onCommand }) => {
  const navigate = useNavigate();

  // ✅ Mostrar modal SIEMPRE que accepted !== true (incluye null o false)
  const [showConsent, setShowConsent] = useState(() => {
    try {
      const stored = JSON.parse(localStorage.getItem('audio_consent') || 'null');
      return !(stored && stored.accepted === true);
    } catch {
      return true;
    }
  });

  const handleAcceptConsent = (prefs) => {
    try {
      localStorage.setItem('audio_consent', JSON.stringify({ accepted: true, ts: Date.now(), prefs }));
    } catch {}
    setShowConsent(false);
  };

  const handleDeclineConsent = () => {
    try {
      // Guardamos explicitamente false; con la lógica de arriba, seguirá mostrando el modal la próxima vez
      localStorage.setItem('audio_consent', JSON.stringify({ accepted: false, ts: Date.now() }));
    } catch {}
    setShowConsent(false);
    // Al declinar, redirigir al inicio
    navigate('/', { replace: true });
  };

  // Hook de voz (trae backendHealth y una función para refrescar)
  const { backendHealth, checkBackendHealth } = useVoiceCommands({});

  // Estados de UI
  const [showHelp, setShowHelp] = useState(false);
  const [testText, setTestText] = useState('');
  const [testResult, setTestResult] = useState(null);

  // Intents soportados (defensivo)
  const [supportedIntents, setSupportedIntents] = useState({
    total_intents: 0,
    intents: {}
  });

  // Cargar intents soportados y chequear salud al montar
  useEffect(() => {
    (async () => {
      try {
        const data = await intentRouter.getSupportedIntents();
        const intents = data?.intents ?? {};
        setSupportedIntents({
          total_intents: data?.total_intents ?? Object.keys(intents).length,
          intents
        });
      } catch (e) {
        console.error('Error loading supported intents:', e);
        setSupportedIntents({ total_intents: 0, intents: {} });
      }

      try {
        await checkBackendHealth?.();
      } catch (e) {
        console.error('Error checking backend health:', e);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Helper para probar un texto
  const testCommand = async () => {
    if (!testText) return;
    try {
      const result = await intentRouter.parseIntent(testText);
      setTestResult(result);
      onCommand?.(result);
    } catch (e) {
      console.error('Test command error:', e);
    }
  };

  // Helpers de color/icono para estado de backend
  const getBackendStatusColor = (status) => {
    if (status === 'ok' || status === 'healthy') return 'green';
    if (status === 'disabled') return 'gray';
    return 'red';
  };
  const getBackendStatusIcon = (status) => {
    if (status === 'ok' || status === 'healthy') return '✅';
    if (status === 'disabled') return '⚪';
    return '❌';
  };

  // Fallbacks defensivos para evitar Object.entries(null)
  const healthStatus = backendHealth?.status ?? 'unknown';
  const backends = backendHealth?.backends ?? {};

  return (
    <>
      {showConsent && (
        <AudioConsentModal onAccept={handleAcceptConsent} onDecline={handleDeclineConsent} />
      )}

      <div className="voice-command-panel">
        {/* Barra superior con botón Atrás */}
        <div className="panel-topbar" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <button
            className="btn-back"
            onClick={() => navigate('/')}
            title="Volver al inicio"
            aria-label="Volver al inicio"
            style={{
              border: '1px solid var(--vp-border, #e5e7eb)',
              background: 'transparent',
              borderRadius: 10,
              padding: '6px 10px',
              cursor: 'pointer'
            }}
          >
            ← Atrás
          </button>
        </div>

        <div className="panel-header">
          <h3>🎤 Comandos de Voz</h3>
          <button
            className="btn-help"
            onClick={() => setShowHelp(!showHelp)}
            aria-label="Mostrar ayuda de comandos"
          >
            {showHelp ? '✕' : '?'}
          </button>
        </div>

        {/* Backend Health Status */}
        <div className="backend-health">
          <div className="health-status">
            <span className={`status-badge status-${healthStatus}`}>
              {healthStatus === 'healthy' ? '🟢' : healthStatus === 'unknown' ? '⚪' : '🟡'} {healthStatus}
            </span>
            <button
              className="btn-refresh-health"
              onClick={checkBackendHealth}
              title="Refrescar estado"
            >
              🔄
            </button>
          </div>

          <div className="backend-list">
            {Object.keys(backends).length === 0 ? (
              <div className="backend-item">
                <span className="backend-name">—</span>
                <span className="backend-status" style={{ color: getBackendStatusColor('unknown') }}>
                  ⚪ unknown
                </span>
              </div>
            ) : (
              Object.entries(backends).map(([backend, status]) => (
                <div key={backend} className="backend-item">
                  <span className="backend-name">{backend}</span>
                  <span
                    className="backend-status"
                    style={{ color: getBackendStatusColor(status) }}
                  >
                    {getBackendStatusIcon(status)} {status}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Test Command Input */}
        <div className="test-command">
          <h4>Probar comando</h4>
          <div className="test-input-group">
            <input
              type="text"
              value={testText}
              onChange={(e) => setTestText(e.target.value)}
              placeholder="Escribe un comando para probar..."
              onKeyDown={(e) => e.key === 'Enter' && testCommand()}
            />
            <button
              className="btn-test"
              onClick={testCommand}
              disabled={!testText}
            >
              Probar
            </button>
          </div>

          {testResult && (
            <div className="test-result">
              <div className="result-row">
                <strong>Intent:</strong>
                <span className={`intent-badge intent-${testResult.intent}`}>
                  {testResult.intent}
                </span>
              </div>
              <div className="result-row">
                <strong>Confianza:</strong>
                <span className={`confidence confidence-${
                  testResult.confidence >= 0.8 ? 'high' :
                  testResult.confidence >= 0.6 ? 'medium' : 'low'
                }`}>
                  {(testResult.confidence * 100).toFixed(1)}%
                </span>
              </div>
              <div className="result-row">
                <strong>Backend:</strong>
                <span className="backend-badge">{testResult.backendUsed}</span>
              </div>
              <div className="result-row">
                <strong>Latencia:</strong>
                <span>{Number(testResult.latencyMs ?? 0).toFixed(0)}ms</span>
              </div>
              {testResult.slots && Object.keys(testResult.slots).length > 0 && (
                <div className="result-row">
                  <strong>Slots:</strong>
                  <pre>{JSON.stringify(testResult.slots, null, 2)}</pre>
                </div>
              )}
              {testResult.warning && (
                <div className="result-warning">
                  ⚠️ {testResult.warning}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Supported Intents Help */}
        {showHelp && (
          <div className="intents-help">
            <h4>Comandos disponibles ({supportedIntents.total_intents})</h4>
            <div className="intents-list">
              {Object.keys(supportedIntents.intents).length === 0 ? (
                <div className="intent-card">
                  <p className="intent-description">No hay intents disponibles.</p>
                </div>
              ) : (
                Object.entries(supportedIntents.intents).map(([intent, info]) => (
                  <div key={intent} className="intent-card">
                    <h5>{intent.replace(/_/g, ' ')}</h5>
                    {info?.description && (
                      <p className="intent-description">{info.description}</p>
                    )}

                    {Array.isArray(info?.slots) && info.slots.length > 0 && (
                      <div className="intent-slots">
                        <strong>Parámetros:</strong> {info.slots.join(', ')}
                      </div>
                    )}

                    {Array.isArray(info?.examples) && info.examples.length > 0 && (
                      <div className="intent-examples">
                        <strong>Ejemplos:</strong>
                        <ul>
                          {info.examples.slice(0, 3).map((example, i) => (
                            <li key={i}>
                              <code>{example}</code>
                              <button
                                className="btn-try-example"
                                onClick={() => {
                                  setTestText(example);
                                  setShowHelp(false);
                                }}
                                title="Probar este ejemplo"
                              >
                                ▶
                              </button>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* Quick Tips */}
        <div className="quick-tips">
          <h4>💡 Tips rápidos</h4>
          <ul>
            <li>Habla de forma natural, el sistema entiende sinónimos</li>
            <li>Para acciones sensibles se pedirá confirmación</li>
            <li>Si un backend falla, se usa automáticamente el siguiente</li>
            <li>Los comandos se cachean para responder más rápido</li>
          </ul>
        </div>
      </div>
    </>
  );
};

export default VoiceCommandPanel;
