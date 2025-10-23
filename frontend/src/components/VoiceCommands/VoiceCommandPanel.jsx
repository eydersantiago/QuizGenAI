// frontend/src/components/VoiceCommands/VoiceCommandPanel.jsx
import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useVoiceCommands } from '../../hooks/useVoiceCommands';
import { logFallbackEvent } from '../../services/voiceMetricsService';
import intentRouter from '../../services/intentRouter';
import AudioConsentModal from '../AudioPrivacy/AudioConsentModal';
import "../../estilos/VoiceCommandPanel.css";
import useMicLevel from '../../hooks/useMicLevel';
import MicMeter from './MicMeter';
import { recordAudioWithFallback } from '../../utils/audioRecorder';
import { startAzureSTT } from '../../voice/azureClientSST';

export default function VoiceCommandPanel({ sessionId, onCommand }) {
  const navigate = useNavigate();
  const apiBase = process.env.REACT_APP_API_BASE || "http://localhost:8000/api";

  // Hook de voz
  const { backendHealth, checkBackendHealth, speak, transcribeBlob } =
    useVoiceCommands({ sessionId });

  // Hook de mic level / VU meter
  const { micStreamRef, level, db, startMeter, stopMeter, setLevel } = useMicLevel(); // ✅ viene del hook
  const sttStopRef = useRef(null); // ✅ ref para parar el SDK

  // CONSENTIMIENTO
  const [showConsent, setShowConsent] = useState(() => {
    try {
      const stored = JSON.parse(localStorage.getItem('audio_consent') || 'null');
      return !(stored && stored.accepted === true);
    } catch {
      return true;
    }
  });

  const [listening, setListening] = useState(false);
  const [partial, setPartial] = useState("");
  const [finalText, setFinalText] = useState("");

  
  const startSTT = async () => {
    if (listening) return;
    setPartial(""); setFinalText(""); setLevel(0); setListening(true);
    try {
      const ctl = await startAzureSTT({
        apiBase,
        language: "es-ES",
        onPartial: setPartial,
        onFinal: (text) => {
          setFinalText(text);
          // opcional: rutear intención aquí
          // intentRouter.parseIntent(text).then(res => { setTestResult(res); onCommand?.(res); });
        },
        onLevel: setLevel,
        onError: (e) => console.error("Azure STT error", e),
      });
      sttStopRef.current = ctl.stop;
    } catch (e) {
      // Fallback a tu backend si el SDK falla
      console.warn("Falling back to server STT:", e.message);
      try {
        const { blob, fmt } = await recordAudioWithFallback(5);
        const out = await transcribeBlob(blob, { language: "es-ES", fmt }); // <- tu hook existente
        setFinalText(out?.text || "");
      } catch (e2) {
        console.error("Fallback STT error:", e2);
        alert("No se pudo usar reconocimiento de voz.");
      } finally {
        setListening(false);
      }
    }
  };


  const stopSTT = async () => {
    if (sttStopRef.current) {
      await sttStopRef.current();
      sttStopRef.current = null;
    }
    setListening(false);
  };


  const handleAcceptConsent = (prefs) => {
    try { localStorage.setItem('audio_consent', JSON.stringify({ accepted: true, ts: Date.now(), prefs })); } catch {}
    setShowConsent(false);
  };

  const handleDeclineConsent = () => {
    try { localStorage.setItem('audio_consent', JSON.stringify({ accepted: false, ts: Date.now() })); } catch {}
    setShowConsent(false);
    navigate('/', { replace: true });
  };

  // Estados UI
  const [showHelp, setShowHelp] = useState(false);
  const [testText, setTestText] = useState('');
  const [testResult, setTestResult] = useState(null);
  const [supportedIntents, setSupportedIntents] = useState({ total_intents: 0, intents: {} });

  // Cargar intents + health al montar
  useEffect(() => {
    (async () => {
      try {
        const data = await intentRouter.getSupportedIntents();
        const intents = data?.intents ?? {};
        setSupportedIntents({ total_intents: data?.total_intents ?? Object.keys(intents).length, intents });
      } catch (e) {
        console.error('Error loading supported intents:', e);
        setSupportedIntents({ total_intents: 0, intents: {} });
      }

      try { await checkBackendHealth?.(); }
      catch (e) { console.error('Error checking backend health:', e); }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // TTS
  const handleTTS = async (text) => {
    if (!text) return;
    try { await speak(text, { voice: "es-ES-AlvaroNeural" }); }
    catch(e){ console.error("TTS error", e); }
  };

  // STT grabando 5s en OGG/Opus
  // STT con detección automática de formato + fallback a WAV
const handleSTTRecord = async () => {
  try {
    // 1) Pide el stream una sola vez para alimentar medidor + grabación
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    micStreamRef.current = stream;
    await startMeter(stream);
    setListening(true);

    // 2) Graba con fallback usando ese stream (5s)
    const { blob, fmt } = await recordAudioWithFallback(5, { stream });

    // 3) Parar medidor y stream ANTES de llamar al backend (UX)
    setListening(false);
    stopMeter();
    try { stream.getTracks().forEach(t => t.stop()); } catch {}

    // 4) Transcribir
    const out = await transcribeBlob(blob, { language: "es-ES", fmt });
    const said = (out && (out.text || out.transcript || out.result?.text))?.trim() || "";

    if (!said) {
      // Mostrar info útil si vuelve vacío
      alert(`No se reconoció texto. Tamaño audio: ${blob.size} bytes · formato: ${fmt}`);
      return;
    }

    // 👇 LOG diagnóstico visible en consola
    console.log("STT out:", out);
    console.log("STT raw.ingest:", out?.raw?.ingest, "warning:", out?.raw?.warning);
    // Puedes mostrar un toast si viene vacío pero con duración muy baja:
    const dur = out?.raw?.ingest?.duration_ms ?? 0;
    if (!out?.text) {
      console.warn(`Texto vacío. dur≈${dur}ms, fmt=${fmt}`);
    }

    // (Opcional) Enrutar intención:
    // const result = await intentRouter.parseIntent(said);
    // setTestResult(result); onCommand?.(result);
  } catch (e) {
    console.error("STT error", e);
    setListening(false);
    stopMeter();
    try { micStreamRef.current?.getTracks().forEach(t => t.stop()); } catch {}
    logFallbackEvent("azure", "local", "stt_error", { where:"VoiceCommandPanel" }).catch(()=>{});

    const msg = (e && e.message) || "";
    const name = e && (e.name || "");
    const isPerm = name === "NotAllowedError" || /permission/i.test(msg);
    const isSupport = /MediaRecorder|getUserMedia|not supported/i.test(msg);
    if (isPerm || isSupport) {
      alert("No se pudo grabar audio en este navegador. Revisa permisos o prueba en Chrome/Edge.");
    }
  }
};


  // Probar texto -> intent
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

  // Helpers de estado
  const healthStatus = backendHealth?.status ?? 'unknown';
  const backends = backendHealth?.backends ?? {};
  const getBackendStatusColor = (status) => (status === 'ok' || status === 'healthy') ? 'green' : (status === 'disabled' ? 'gray' : 'red');
  const getBackendStatusIcon  = (status) => (status === 'ok' || status === 'healthy') ? '✅'   : (status === 'disabled' ? '⚪'  : '❌');

  return (
    <>
      {showConsent && (
        <AudioConsentModal onAccept={handleAcceptConsent} onDecline={handleDeclineConsent} />
      )}

      <div className="voice-command-panel">
        {/* Topbar */}
        <div className="panel-topbar" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <button
            className="btn-back"
            onClick={() => navigate('/')}
            title="Volver al inicio"
            aria-label="Volver al inicio"
            style={{ border: '1px solid var(--vp-border, #e5e7eb)', background: 'transparent', borderRadius: 10, padding: '6px 10px', cursor: 'pointer' }}
          >
            ← Atrás
          </button>
        </div>

      <div className="panel-header">
        <h3>🎤 Comandos de Voz</h3>
        <div className="actions">
          <button className="btn-help" onClick={() => setShowHelp(!showHelp)} aria-label="Mostrar ayuda de comandos">
            {showHelp ? '✕' : '?'}
          </button>
          <button className="btn-test" onClick={() => handleTTS(testText)} disabled={!testText} title="Leer texto con TTS">🔊</button>
          <button className="btn-test" onClick={handleSTTRecord} title="Grabar 5s y transcribir">
            {listening ? "⏺️ Grabando..." : "🎙️ Grabar"}
          </button>
        </div>
      </div>

      <div style={{ margin: "8px 0 16px" }}>
        <MicMeter level={level} db={db} listening={listening} />
      </div>

        {/* Backend Health */}
        <div className="backend-health">
          <div className="health-status">
            <span className={`status-badge status-${healthStatus}`}>
              {healthStatus === 'healthy' ? '🟢' : healthStatus === 'unknown' ? '⚪' : '🟡'} {healthStatus}
            </span>
            <button className="btn-refresh-health" onClick={checkBackendHealth} title="Refrescar estado">🔄</button>
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
                  <span className="backend-status" style={{ color: getBackendStatusColor(status) }}>
                    {getBackendStatusIcon(status)} {status}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Probar comando (texto -> intent) */}
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
            <button className="btn-test" onClick={testCommand} disabled={!testText}>Probar</button>
          </div>

          {testResult && (
            <div className="test-result">
              <div className="result-row"><strong>Intent:</strong><span className={`intent-badge intent-${testResult.intent}`}>{testResult.intent}</span></div>
              <div className="result-row">
                <strong>Confianza:</strong>
                <span className={`confidence confidence-${
                  testResult.confidence >= 0.8 ? 'high' :
                  testResult.confidence >= 0.6 ? 'medium' : 'low'
                }`}>
                  {(testResult.confidence * 100).toFixed(1)}%
                </span>
              </div>
              <div className="result-row"><strong>Backend:</strong><span className="backend-badge">{testResult.backendUsed}</span></div>
              <div className="result-row"><strong>Latencia:</strong><span>{Number(testResult.latencyMs ?? 0).toFixed(0)}ms</span></div>
              {testResult.slots && Object.keys(testResult.slots).length > 0 && (
                <div className="result-row"><strong>Slots:</strong><pre>{JSON.stringify(testResult.slots, null, 2)}</pre></div>
              )}
              {testResult.warning && (<div className="result-warning">⚠️ {testResult.warning}</div>)}
            </div>
          )}
        </div>

        {/* Ayuda de intents */}
        {showHelp && (
          <div className="intents-help">
            <h4>Comandos disponibles ({supportedIntents.total_intents})</h4>
            <div className="intents-list">
              {Object.keys(supportedIntents.intents).length === 0 ? (
                <div className="intent-card"><p className="intent-description">No hay intents disponibles.</p></div>
              ) : (
                Object.entries(supportedIntents.intents).map(([intent, info]) => (
                  <div key={intent} className="intent-card">
                    <h5>{intent.replace(/_/g, ' ')}</h5>
                    {info?.description && (<p className="intent-description">{info.description}</p>)}
                    {Array.isArray(info?.slots) && info.slots.length > 0 && (
                      <div className="intent-slots"><strong>Parámetros:</strong> {info.slots.join(', ')}</div>
                    )}
                    {Array.isArray(info?.examples) && info.examples.length > 0 && (
                      <div className="intent-examples">
                        <strong>Ejemplos:</strong>
                        <ul>
                          {info.examples.slice(0, 3).map((example, i) => (
                            <li key={i}>
                              <code>{example}</code>
                              <button className="btn-try-example" onClick={() => { setTestText(example); setShowHelp(false); }} title="Probar este ejemplo">▶</button>
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
}
