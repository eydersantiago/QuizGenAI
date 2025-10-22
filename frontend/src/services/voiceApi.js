const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:8000/api";

export async function ttsSpeak({ text, voice="es-ES-AlvaroNeural", format="audio-16khz-32kbitrate-mono-mp3", sessionId }) {
  const res = await fetch(`${API_BASE}/voice/tts/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, voice, format, session_id: sessionId }),
  });
  if (!res.ok) throw new Error(`TTS failed: ${res.status}`);
  return await res.blob(); // audio
}

export async function sttRecognizeBlob({ blob, language="es-ES", fmt, sessionId }) {
  const fd = new FormData();
  fd.append("language", language);
  if (fmt) fd.append("fmt", fmt); // "ogg" si grabas con MediaRecorder
  if (sessionId) fd.append("session_id", sessionId);
  fd.append("audio", blob, fmt === "ogg" ? "audio.ogg" : "audio.wav");

  const res = await fetch(`${API_BASE}/voice/stt/`, { method: "POST", body: fd });
  const json = await res.json().catch(()=> ({}));
  if (!res.ok) throw new Error(json?.error || `STT failed: ${res.status}`);
  return json; // { text, confidence?, latency_ms }
}

export async function getBackendHealth() {
  const res = await fetch(`${API_BASE}/voice-metrics/summary/`);
  return res.ok ? { status: "healthy", backends: { azure:"ok" } } : { status: "warn", backends:{} };
}
