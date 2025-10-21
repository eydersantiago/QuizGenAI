// frontend/src/components/VoiceCommands/VoiceCommandPanel.jsx

import React, { useState, useEffect } from 'react';
import { useVoiceCommands } from '../../hooks/useVoiceCommands';
import intentRouter from '../../services/intentRouter';
import './VoiceCommandPanel.css';

const VoiceCommandPanel = ({ onCommand }) => {
  const [supportedIntents, setSupportedIntents] = useState(null);
  const [showHelp, setShowHelp] = useState(false);
  const [testText, setTestText] = useState('');
  const [testResult, setTestResult] = useState(null);

  const { backendHealth, checkBackendHealth } = useVoiceCommands({});

  useEffect(() => {
    loadSupportedIntents();
  }, []);

  const loadSupportedIntents = async () => {
    const intents = await intentRouter.getSupportedIntents();
    setSupportedIntents(intents);
  };

  const testCommand = async () => {
    if (!testText) return;
    
    const result = await intentRouter.parseIntent(testText);
    setTestResult(result);
    
    if (onCommand) {
      onCommand(result);
    }
  };

  const getBackendStatusColor = (status) => {
    if (status === 'ok') return 'green';
    if (status === 'disabled') return 'gray';
    return 'red';
  };

  const getBackendStatusIcon = (status) => {
    if (status === 'ok') return '✅';
    if (status === 'disabled') return '⚪';
    return '❌';
  };

  return (
    <div className="voice-command-panel">
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
      {backendHealth && (
        <div className="backend-health">
          <div className="health-status">
            <span className={`status-badge status-${backendHealth.status}`}>
              {backendHealth.status === 'healthy' ? '🟢' : '🟡'} {backendHealth.status}
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
            {Object.entries(backendHealth.backends).map(([backend, status]) => (
              <div key={backend} className="backend-item">
                <span className="backend-name">{backend}</span>
                <span 
                  className="backend-status"
                  style={{ color: getBackendStatusColor(status) }}
                >
                  {getBackendStatusIcon(status)} {status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Test Command Input */}
      <div className="test-command">
        <h4>Probar comando</h4>
        <div className="test-input-group">
          <input
            type="text"
            value={testText}
            onChange={(e) => setTestText(e.target.value)}
            placeholder="Escribe un comando para probar..."
            onKeyPress={(e) => e.key === 'Enter' && testCommand()}
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
              <span className={`confidence confidence-${testResult.confidence >= 0.8 ? 'high' : testResult.confidence >= 0.6 ? 'medium' : 'low'}`}>
                {(testResult.confidence * 100).toFixed(1)}%
              </span>
            </div>
            <div className="result-row">
              <strong>Backend:</strong> 
              <span className="backend-badge">{testResult.backendUsed}</span>
            </div>
            <div className="result-row">
              <strong>Latencia:</strong> 
              <span>{testResult.latencyMs.toFixed(0)}ms</span>
            </div>
            {Object.keys(testResult.slots).length > 0 && (
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
      {showHelp && supportedIntents && (
        <div className="intents-help">
          <h4>Comandos disponibles ({supportedIntents.total_intents})</h4>
          <div className="intents-list">
            {Object.entries(supportedIntents.intents).map(([intent, info]) => (
              <div key={intent} className="intent-card">
                <h5>{intent.replace(/_/g, ' ')}</h5>
                <p className="intent-description">{info.description}</p>
                
                {info.slots && info.slots.length > 0 && (
                  <div className="intent-slots">
                    <strong>Parámetros:</strong> {info.slots.join(', ')}
                  </div>
                )}
                
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
              </div>
            ))}
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
  );
};

export default VoiceCommandPanel;