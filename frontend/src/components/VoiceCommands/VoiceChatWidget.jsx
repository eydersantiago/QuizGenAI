import React, { useState, useRef } from 'react';
import intentRouter from '../../services/intentRouter';
import { useVoiceCommands } from '../../hooks/useVoiceCommands';
import { recordAudioWithFallback, pickSupportedAudioMime } from '../../utils/audioRecorder';
import "../../estilos/VoiceCommandPanel.css";

// Copiado (ligeramente) de VoiceCommandPanel para conversión WAV
async function webmOrOggToWav(blob) {
  const arrayBuf = await blob.arrayBuffer();
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const decoded = await ctx.decodeAudioData(arrayBuf.slice(0));
  const wav = audioBufferToWavPcm16(decoded);
  try { ctx.close(); } catch {}
  return wav;
}

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

  writeString('RIFF'); write32(length - 8); writeString('WAVE'); writeString('fmt '); write32(16);
  write16(1); write16(numOfChan); write32(sampleRate); write32(sampleRate * numOfChan * 2); write16(numOfChan * 2); write16(16);
  writeString('data'); write32(length - offset - 4);

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

async function ensureWavBlob(inputBlob) {
  const type = (inputBlob?.type || '').toLowerCase();
  if (type.includes('wav')) return inputBlob;
  if (type.includes('webm') || type.includes('ogg') || type.includes('opus')) {
    return await webmOrOggToWav(inputBlob);
  }
  try { return await webmOrOggToWav(inputBlob); } catch { return inputBlob; }
}

export default function VoiceChatWidget({ sessionId, onCommand }) {
  const { speak, transcribeBlob } = useVoiceCommands({ sessionId });
  const [open, setOpen] = useState(false);
  const [listening, setListening] = useState(false);
  const [lastText, setLastText] = useState('');
  const [lastIntent, setLastIntent] = useState(null);
  const togglingRef = useRef(false);
  const mediaRecorderRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const recorderTimeoutRef = useRef(null);
  const chunksRef = useRef([]);

  // cleanup on unmount
  React.useEffect(() => {
    return () => {
      try { if (recorderTimeoutRef.current) clearTimeout(recorderTimeoutRef.current); } catch {}
      try { if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') mediaRecorderRef.current.stop(); } catch {}
      try { if (mediaStreamRef.current) mediaStreamRef.current.getTracks().forEach(t => t.stop()); } catch {}
    };
  }, []);

  const processRecordedBlob = async (blob) => {
    try {
      console.debug('[VoiceChatWidget] processRecordedBlob: blob', { type: blob?.type, size: blob?.size });
      const wav = await ensureWavBlob(blob);
      console.debug('[VoiceChatWidget] WAV blob ready', { type: wav?.type, size: wav?.size });
      const out = await transcribeBlob(wav, { language: 'es-ES', fmt: 'wav' });
      console.debug('[VoiceChatWidget] transcribeBlob output', out);
      const said = (out && (out.text || out.transcript || out.result?.text))?.trim() || '';
      setLastText(said);
      if (!said) {
        await speak('No se reconoció texto. Intenta de nuevo.');
        return;
      }
      const result = await intentRouter.parseIntent(said);
      console.debug('[VoiceChatWidget] intentRouter.parseIntent result', result);
      const fullResult = { ...result, text: said };
      setLastIntent(fullResult);
      try { await speak(`He entendido: ${fullResult.intent}`); } catch (e) {}
      try {
        window.dispatchEvent(new CustomEvent('voice:intent', { detail: fullResult }));
        console.debug('[VoiceChatWidget] dispatched voice:intent', fullResult);
      } catch (e) { console.error('[VoiceChatWidget] dispatch error', e); }
      onCommand?.(fullResult);
    } catch (e) {
      console.error('VoiceChatWidget STT error', e);
      try { await speak('Ocurrió un error al escuchar.'); } catch (e) {}
    }
  };

  const stopRecorder = () => {
    try {
      if (recorderTimeoutRef.current) { clearTimeout(recorderTimeoutRef.current); recorderTimeoutRef.current = null; }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
    } catch (e) { console.warn('stopRecorder err', e); }
  };

  const handleListen = async () => {
    if (!listening) {
      // start recording (stoppable)
      const mime = pickSupportedAudioMime();
      if (mime && navigator.mediaDevices?.getUserMedia) {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          console.debug('[VoiceChatWidget] getUserMedia OK, stream tracks=', stream.getTracks().map(t=>t.kind + ':' + t.label));
          mediaStreamRef.current = stream;
          const rec = new MediaRecorder(stream, { mimeType: mime });
          chunksRef.current = [];
          rec.ondataavailable = (e) => { if (e.data && e.data.size) { chunksRef.current.push(e.data); console.debug('[VoiceChatWidget] dataavailable chunk size', e.data.size); } };
          rec.onerror = (e) => console.error('MediaRecorder error', e);
          rec.onstop = async () => {
            console.debug('[VoiceChatWidget] MediaRecorder stopped, chunks:', chunksRef.current.length);
            const blob = new Blob(chunksRef.current, { type: mime });
            console.debug('[VoiceChatWidget] created blob from chunks', { type: blob.type, size: blob.size });
            try { mediaStreamRef.current.getTracks().forEach(t => t.stop()); } catch (e) {}
            mediaRecorderRef.current = null;
            mediaStreamRef.current = null;
            setListening(false);
            await processRecordedBlob(blob);
          };
          mediaRecorderRef.current = rec;
          rec.start();
          console.debug('[VoiceChatWidget] MediaRecorder started', { mime });
          setListening(true);
          // auto stop after 4s
          recorderTimeoutRef.current = setTimeout(() => {
            stopRecorder();
          }, 4000);
        } catch (e) {
          console.error('Could not start MediaRecorder', e);
          // fallback to simple recorder that can't be stopped early
          setListening(true);
          try {
            const { blob } = await recordAudioWithFallback(4);
            console.debug('[VoiceChatWidget] fallback recordAudioWithFallback returned blob', { type: blob?.type, size: blob?.size });
            await processRecordedBlob(blob);
          } catch (f) {
            console.error('Fallback recording failed', f);
            try { await speak('No se pudo acceder al micrófono.'); } catch (e) {}
          } finally { setListening(false); }
        }
      } else {
        // no MediaRecorder support: fallback (not stoppable)
        setListening(true);
        try {
          const { blob } = await recordAudioWithFallback(20);
          console.debug('[VoiceChatWidget] no MediaRecorder support, fallback blob', { type: blob?.type, size: blob?.size });
          await processRecordedBlob(blob);
        } catch (e) {
          console.error('Fallback recording failed', e);
          try { await speak('No se pudo acceder al micrófono.'); } catch (e) {}
        } finally { setListening(false); }
      }
    } else {
      // stop early
      stopRecorder();
    }
  };

  return (
    <div style={{ position: 'fixed', right: 16, bottom: 16, zIndex: 4000 }}>
      {!open ? (
        <button
          onClick={() => setOpen(true)}
          title="Abrir escuchador"
          style={{
            background: 'var(--vp-accent, #4f46e5)', color: '#fff', borderRadius: 999, width: 56, height: 56, border: 'none', cursor: 'pointer'
          }}
        >
          🎧
        </button>
      ) : (
        <div className="voice-chat-widget card" style={{ width: 320, boxShadow: '0 8px 24px rgba(97, 70, 70, 0.2)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 10px' }}>
            <strong>Escuchar</strong>
            <div>
              <button className="btn-test" onClick={() => setOpen(false)} aria-label="Cerrar">✕</button>
            </div>
          </div>
          <div style={{ padding: 10 }}>
            <div style={{ minHeight: 54, background: '#f8fafc', borderRadius: 6, padding: 8, fontSize: 13 }}>
              {lastText || <em>Presiona grabar y di tu comando...</em>}
            </div>
            <div style={{ marginTop: 8, display: 'flex', gap: 8, alignItems: 'center' }}>
              <button className="btn btn-indigo" onClick={handleListen}>
                {listening ? 'Detener' : 'Grabar'}
              </button>
              {/* <button className="btn" onClick={() => { setLastText(''); setLastIntent(null); }}>
                Limpiar
              </button> */}
            </div>
            {/* {lastIntent && (
              <div style={{ marginTop: 10, padding: 8, background: '#fff', border: '1px solid var(--vp-border)', borderRadius: 6 }}>
                <div><strong>Intención:</strong> {lastIntent.intent}</div>
                <div style={{ marginTop: 6 }}><small>Confianza: {(lastIntent.confidence ?? 0).toFixed(2)}</small></div>
                {lastIntent.slots && Object.keys(lastIntent.slots).length > 0 && (
                  <pre style={{ marginTop: 6, fontSize: 12 }}>{JSON.stringify(lastIntent.slots, null, 2)}</pre>
                )}
              </div>
            )} */}
          </div>
        </div>
      )}
    </div>
  );
}
