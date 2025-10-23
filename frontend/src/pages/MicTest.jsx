import React, { useEffect, useRef, useState } from "react";

const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:8000/api";

/** Graba audio usando el mismo fallback que usas en el proyecto */
async function recordAudio(seconds = 4) {
  // 1) pide stream
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

  // 2) intenta usar webm (Chrome/Edge), si falla, prueba ogg, luego wav
  const tryTypes = [
    { mimeType: "audio/webm;codecs=opus", ext: "webm", fmt: "webm" },
    { mimeType: "audio/ogg;codecs=opus", ext: "ogg", fmt: "ogg" },
    { mimeType: "audio/wav", ext: "wav", fmt: "wav" },
  ];

  let picked = null;
  for (const t of tryTypes) {
    if (MediaRecorder.isTypeSupported(t.mimeType)) {
      picked = t; break;
    }
  }
  if (!picked) picked = tryTypes[2];

  const chunks = [];
  const rec = new MediaRecorder(stream, { mimeType: picked.mimeType });

  const done = new Promise((resolve, reject) => {
    rec.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
    rec.onerror = e => reject(e.error || e.message || e);
    rec.onstop = () => {
      const blob = new Blob(chunks, { type: picked.mimeType });
      resolve({ blob, fmt: picked.fmt });
    };
  });

  rec.start();
  await new Promise(r => setTimeout(r, seconds * 1000));
  rec.stop();

  // parar tracks
  try { stream.getTracks().forEach(t => t.stop()); } catch {}
  return done;
}

/** Envía a tu backend /api/voice/stt/ igual que hace el hook */
async function transcribeViaServer(blob, { language = "es-ES", fmt }) {
  const fd = new FormData();
  fd.append("audio", blob, `mic.${fmt || "webm"}`);
  fd.append("language", language);
  if (fmt) fd.append("fmt", fmt);

  const res = await fetch(`${API_BASE}/voice/stt/`, { method: "POST", body: fd });
  const j = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(j?.error || `HTTP ${res.status}`);
  return j; // { text, confidence, raw:{ingest...}, latency_ms }
}

export default function MicTest() {
  const [level, setLevel] = useState(0);        // 0..1
  const [db, setDb] = useState(null);           // dBFS del medidor local
  const [listening, setListening] = useState(false);
  const [blobUrl, setBlobUrl] = useState(null);
  const [resp, setResp] = useState(null);
  const [error, setError] = useState(null);
  const analyserRef = useRef(null);
  const rafRef = useRef(null);
  const streamRef = useRef(null);

  // medidor en vivo con WebAudio
  const startMeter = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;
    const ctx = new AudioContext();
    const src = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    src.connect(analyser);
    analyserRef.current = { ctx, analyser };

    const data = new Uint8Array(analyser.frequencyBinCount);
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      // peak simple
      let sum = 0;
      for (let i=0;i<data.length;i++){
        const v = (data[i]-128)/128;
        sum += v*v;
      }
      const rms = Math.sqrt(sum / data.length);
      setLevel(rms);                   // 0..1 aprox
      setDb(20 * Math.log10(rms + 1e-6));
      rafRef.current = requestAnimationFrame(tick);
    };
    tick();
  };

  const stopMeter = () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    const a = analyserRef.current;
    if (a) { try { a.ctx.close(); } catch {} }
    analyserRef.current = null;
    try { streamRef.current?.getTracks().forEach(t => t.stop()); } catch {}
    streamRef.current = null;
  };

  useEffect(() => () => stopMeter(), []); // cleanup al desmontar

  const handleTest = async () => {
    setError(null); setResp(null); setBlobUrl(null);
    try {
      // 1) arranca medidor
      setListening(true);
      await startMeter();

      // 2) graba 4s
      const { blob, fmt } = await recordAudio(4);

      // 3) para medidor antes de transcribir
      setListening(false);
      stopMeter();

      console.log("grabado:", blob.type, "bytes:", blob.size, "fmt:", fmt);
      setBlobUrl(URL.createObjectURL(blob));

      // tamaño ridículo => silencio
      if (blob.size < 1500) {
        setError(`Audio muy pequeño (${blob.size} bytes). Intenta hablar 2–3s cerca del micro.`);
        return;
      }

      // 4) envía al backend
      const out = await transcribeViaServer(blob, { language: "es-ES", fmt });
      console.log("STT resp:", out);
      setResp(out);
    } catch (e) {
      console.error(e);
      setError(e.message || String(e));
      setListening(false);
      stopMeter();
    }
  };

  return (
    <main style={{maxWidth: 760, margin: "24px auto", padding: 16}}>
      <h2>🔧 Diagnóstico de micrófono / STT</h2>

      <div style={{margin: "16px 0"}}>
        <button onClick={handleTest} disabled={listening} style={{padding:"8px 12px"}}>
          {listening ? "⏺️ Grabando 4s..." : "🎙️ Grabar y transcribir"}
        </button>
      </div>

      {/* Medidor simple */}
      <div style={{marginBottom: 12}}>
        <div>Mic level (rms): {(level*100).toFixed(0)}%</div>
        <div>dBFS aprox: {db === null ? "—" : db.toFixed(1)} dB</div>
        <div style={{
          height: 10, background: "#eee", borderRadius: 6, overflow:"hidden", marginTop: 4
        }}>
          <div style={{
            width: `${Math.min(100, level*120)}%`,
            height: "100%", background: listening ? "#22c55e" : "#9ca3af"
          }}/>
        </div>
      </div>

      {/* Audio grabado */}
      {blobUrl && (
        <div style={{margin: "12px 0"}}>
          <audio controls src={blobUrl}/>
          <div>
            <a href={blobUrl} download="mic-test.webm">⬇️ Descargar muestra</a>
          </div>
        </div>
      )}

      {/* Resultado backend */}
      {resp && (
        <div style={{marginTop: 16}}>
          <h3>Resultado</h3>
          <pre style={{whiteSpace:"pre-wrap", background:"#f8fafc", padding:12, borderRadius:8}}>
{JSON.stringify({
  text: resp.text,
  confidence: resp.confidence,
  latency_ms: resp.latency_ms,
  ingest: resp?.raw?.ingest,
  warning: resp?.raw?.warning
}, null, 2)}
          </pre>
        </div>
      )}

      {error && (
        <div style={{marginTop: 16, color: "#b91c1c"}}>
          <b>Error:</b> {error}
        </div>
      )}
    </main>
  );
}
