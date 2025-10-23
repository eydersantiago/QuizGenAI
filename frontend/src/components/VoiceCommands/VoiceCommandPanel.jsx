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


// --- Helpers para convertir a WAV PCM16 (copiados de QuizPlay y simplificados) ---
function audioBufferToWavPcm16(buffer) {
  const numOfChan = buffer.numberOfChannels;
  const length = buffer.length * numOfChan * 2 + 44;
  const sampleRate = buffer.sampleRate;
  const out = new ArrayBuffer(length);
  const view = new DataView(out);

  let offset = 0;
  const writeString = (s) => { for (let i = 0; i < s.length; i++) view.setUint8(offset++, s.charCodeAt(i)); };
  const write16 = (d) => { view.setUint16(offset, d, true); offset += 2; };
  const write32 = (d) => { view.setUint32(offset, d, true); offset += 4; };

  // Header WAV
  writeString('RIFF');
  write32(length - 8);
  writeString('WAVE');
  writeString('fmt ');
  write32(16);
  write16(1); // PCM
  write16(numOfChan);
  write32(sampleRate);
  write32(sampleRate * numOfChan * 2);
  write16(numOfChan * 2);
  write16(16); // 16-bit
  writeString('data');
  write32(length - offset - 4);

  // Interleave + PCM16
  const channels = [];
  for (let i = 0; i < numOfChan; i++) channels.push(buffer.getChannelData(i));

  const interleaved = new Float32Array(buffer.length * numOfChan);
  for (let i = 0; i < buffer.length; i++) {
    for (let ch = 0; ch < numOfChan; ch++) {
      interleaved[i * numOfChan + ch] = channels[ch][i];
    }
  }
  for (let i = 0; i < interleaved.length; i++, offset += 2) {
    let s = Math.max(-1, Math.min(1, interleaved[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }

  return new Blob([view], { type: 'audio/wav' });
}

async function webmOrOggToWav(blob) {
  const arrayBuf = await blob.arrayBuffer();
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const decoded = await ctx.decodeAudioData(arrayBuf.slice(0));
  const wavBlob = audioBufferToWavPcm16(decoded);
  try { ctx.close(); } catch {}
  return wavBlob;
}

// Garantiza WAV: si ya es WAV lo devuelve igual, si es webm/ogg lo convierte
async function ensureWavBlob(inputBlob) {
  const type = (inputBlob?.type || '').toLowerCase();
  if (type.includes('wav')) return inputBlob;
  if (type.includes('webm') || type.includes('ogg') || type.includes('opus')) {
    return await webmOrOggToWav(inputBlob);
  }
  // último recurso: intenta decodificar y convertir
  try { return await webmOrOggToWav(inputBlob); } catch { return inputBlob; }
}


export default function VoiceCommandPanel({ sessionId, onCommand }) {
  const navigate = useNavigate();
  const apiBase = process.env.REACT_APP_API_BASE || "http://localhost:8000/api";

  // Hook de voz
  const { backendHealth, checkBackendHealth, speak, transcribeBlob } =
    useVoiceCommands({ sessionId });

  // Hook de mic level / VU meter
  const micRef = useRef(null); // ← ref local, no dependas del hook
  const {
    level,
    db,
    // normaliza nombres del hook: si no existen, usa no-ops
    startMeter: _startMeter,
    stopMeter: _stopMeter,
    setLevel: _setLevel,
  } = useMicLevel() || {};
    const startVU = typeof _startMeter === 'function' ? _startMeter : async () => {};
    const stopVU  = typeof _stopMeter  === 'function' ? _stopMeter  : () => {};
    const setVU   = typeof _setLevel   === 'function' ? _setLevel   : () => {};
    const sttStopRef = useRef(null);

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
    setPartial(""); setFinalText(""); setVU(0); setListening(true);
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
        onLevel: setVU,               // <-- aquí el fix
        onError: (e) => console.error("Azure STT error", e),
      });
      sttStopRef.current = ctl.stop;
    } catch (e) {
      console.warn("Falling back to server STT:", e.message);
      try {
        const { blob, fmt } = await recordAudioWithFallback(5);
        // 4) Convertir a WAV siempre y transcribir
        const wav = await ensureWavBlob(blob);
        const out = await transcribeBlob(wav, { language: "es-ES", fmt: "wav" });
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
      try { stopVU(); } catch {}
      try { micRef.current?.getTracks().forEach(t => t.stop()); } catch {}
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
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micRef.current = stream;        // <-- usamos el ref local
      await startVU(stream);          // <-- y el start seguro
      setListening(true);

      const { blob, fmt } = await recordAudioWithFallback(5, { stream });

      setListening(false);
      try { stopVU(); } catch {}
      try { stream.getTracks().forEach(t => t.stop()); } catch {}

      const wav = await ensureWavBlob(blob);
      const out = await transcribeBlob(wav, { language: "es-ES", fmt: "wav" });
      const said = (out && (out.text || out.transcript || out.result?.text))?.trim() || "";
      if (!said) {
        alert(`No se reconoció texto. Tamaño audio: ${blob.size} bytes · formato: ${fmt}`);
        return;
      }
      console.log("STT out:", out);
    } catch (e) {
      console.error("STT error", e);
      setListening(false);
      try { stopVU(); } catch {}
      try { micRef.current?.getTracks().forEach(t => t.stop()); } catch {}
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


