import { useEffect, useRef, useState, useCallback } from "react";

/**
 * Lee niveles del micrófono con WebAudio.
 * Devuelve { level (0..1), db (aprox), start(stream), stop() }.
 */
export default function useMicLevel() {
  const [level, setLevel] = useState(0);
  const [db, setDb] = useState(-Infinity);

  const ctxRef = useRef(null);
  const analyserRef = useRef(null);
  const srcRef = useRef(null);
  const rafRef = useRef(null);
  const dataRef = useRef(null);

  const tick = useCallback(() => {
    if (!analyserRef.current) return;
    analyserRef.current.getByteTimeDomainData(dataRef.current);

    // RMS -> nivel 0..1 y dB aprox
    let sum = 0;
    for (let i = 0; i < dataRef.current.length; i++) {
      const v = (dataRef.current[i] - 128) / 128; // -1..1
      sum += v * v;
    }
    const rms = Math.sqrt(sum / dataRef.current.length); // 0..1
    const clamped = Math.min(1, Math.max(0, rms));
    const dbVal = 20 * Math.log10(clamped || 0.000001); // evita -Infinity

    setLevel(clamped);
    setDb(dbVal);

    rafRef.current = requestAnimationFrame(tick);
  }, []);

  const start = useCallback(async (stream) => {
    // Reusar contexto si existe
    ctxRef.current = ctxRef.current || new (window.AudioContext || window.webkitAudioContext)();
    const ctx = ctxRef.current;

    // Nodos
    srcRef.current = ctx.createMediaStreamSource(stream);
    analyserRef.current = ctx.createAnalyser();
    analyserRef.current.fftSize = 1024;
    dataRef.current = new Uint8Array(analyserRef.current.fftSize);

    srcRef.current.connect(analyserRef.current);
    rafRef.current = requestAnimationFrame(tick);
  }, [tick]);

  const stop = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    if (srcRef.current) {
      try { srcRef.current.disconnect(); } catch {}
      srcRef.current = null;
    }
    if (analyserRef.current) analyserRef.current = null;
    // No cerramos el AudioContext para reusar (evita pops)
  }, []);

  useEffect(() => () => stop(), [stop]);

  return { level, db, start, stop };
}
