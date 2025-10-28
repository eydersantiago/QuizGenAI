import * as sdk from "microsoft-cognitiveservices-speech-sdk";

/**
 * Inicia reconocimiento continuo con Azure Speech SDK desde el micrófono.
 * Devuelve { stop } y emite onPartial/onFinal/onError/onLevel.
 */
export async function startAzureSTT({
  apiBase,
  language = "es-ES",
  onPartial,
  onFinal,
  onError,
  onLevel,
} = {}) {
  try {
    // 1) Token
    const r = await fetch(`${apiBase}/voice/token/`);
    if (!r.ok) {
      const txt = await r.text().catch(() => "");
      throw new Error(`Token HTTP ${r.status} ${txt ? "- " + txt : ""}`);
    }
    let payload = {};
    try { payload = await r.json(); } catch {}
    const { token, region, error } = payload || {};
    if (error || !token || !region) {
      throw new Error(error || "Missing token/region from /voice/token/");
    }

    // 2) SDK config
    const speechConfig = sdk.SpeechConfig.fromAuthorizationToken(token, region);
    speechConfig.speechRecognitionLanguage = language;
    const audioConfig = sdk.AudioConfig.fromDefaultMicrophoneInput();
    const recognizer = new sdk.SpeechRecognizer(speechConfig, audioConfig);

    // 3) Eventos
    recognizer.recognizing = (_, e) => onPartial?.(e.result.text || "");
    recognizer.recognized  = (_, e) => {
      if (e.result.reason === sdk.ResultReason.RecognizedSpeech) {
        onFinal?.(e.result.text || "");
      } else if (e.result.reason === sdk.ResultReason.NoMatch) {
        onFinal?.("");
      }
    };
    recognizer.canceled = (_, e) => onError?.(new Error(`canceled: ${e.errorDetails || e.reason || "unknown"}`));
    recognizer.sessionStopped = () => {/* noop */};

    // 4) Arranca
    await new Promise((res, rej) => recognizer.startContinuousRecognitionAsync(res, rej));

    // 5) VU meter
    const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const src = ctx.createMediaStreamSource(mic);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    src.connect(analyser);
    const data = new Uint8Array(analyser.fftSize);

    let running = true;
    let stopped = false;
    (function loop() {
      if (!running) return;
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) {
        const v = (data[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / data.length);
      onLevel?.(rms);
      requestAnimationFrame(loop);
    })();

    const stop = async () => {
      if (stopped) return;
      stopped = true;
      running = false;
      try {
        await new Promise((res, rej) => recognizer.stopContinuousRecognitionAsync(res, rej));
      } catch {}
      try { recognizer.close(); } catch {}
      try { mic.getTracks().forEach(t => { try { t.stop(); } catch {} }); } catch {}
      try {
        if (ctx && typeof ctx.state === "string" && ctx.state !== "closed") {
          await ctx.close();
        }
      } catch {}
    };

    return { stop };
  } catch (e) {
    onError?.(e);
    throw e;
  }
}
