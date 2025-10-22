import { useState, useCallback } from "react";
import { getBackendHealth, ttsSpeak, sttRecognizeBlob } from "../services/voiceApi";
import { logSTTEvent, logTTSEvent } from "../services/voiceMetricsService";

export function useVoiceCommands({ sessionId } = {}) {
  const [backendHealth, setBackendHealth] = useState({ status: "unknown", backends: {} });

  const checkBackendHealth = useCallback(async () => {
    try {
      const status = await getBackendHealth();
      setBackendHealth(status);
      return status;
    } catch {
      const fallback = { status: "warn", backends: {} };
      setBackendHealth(fallback);
      return fallback;
    }
  }, []);

  const speak = useCallback(async (text, { voice, format } = {}) => {
    const t0 = performance.now();
    try {
      logTTSEvent("start", null, text?.length || 0, null, { voice, format }).catch(()=>{});
      const blob = await ttsSpeak({ text, voice, format, sessionId });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.play().catch(()=>{});
      const latency = Math.round(performance.now() - t0);
      logTTSEvent("complete", latency, text?.length || 0, null, { voice, format }).catch(()=>{});
      return { blob, url, latency_ms: latency };
    } catch (e) {
      const latency = Math.round(performance.now() - t0);
      logTTSEvent("error", latency, text?.length || 0, null, { voice, format, error: String(e) }).catch(()=>{});
      throw e;
    }
  }, [sessionId]);

  // ✅ ÚNICA implementación de transcribeBlob (no hay otra más abajo)
  const transcribeBlob = useCallback(async (blob, { language = "es-ES", fmt = "ogg" } = {}) => {
    const t0 = performance.now();
    try {
      logSTTEvent("start", null, null, null, { language, fmt }).catch(()=>{});
      const out = await sttRecognizeBlob({ blob, language, fmt, sessionId });
      const latency = Math.round(performance.now() - t0);
      logSTTEvent("final", latency, (out?.text || "").length, out?.confidence ?? null, { language, fmt }).catch(()=>{});
      return out; // { text, confidence, latency_ms, raw }
    } catch (e) {
      const latency = Math.round(performance.now() - t0);
      logSTTEvent("error", latency, null, null, { language, fmt, error: String(e) }).catch(()=>{});
      throw e;
    }
  }, [sessionId]);

  return { backendHealth, checkBackendHealth, speak, transcribeBlob };
}
