// frontend/src/utils/audioRecorder.js

export function pickSupportedAudioMime() {
  if (typeof window === "undefined" || !window.MediaRecorder) return null;
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/ogg",
  ];
  for (const type of candidates) {
    if (window.MediaRecorder.isTypeSupported(type)) return type;
  }
  return null;
}

function extFromMime(mime) {
  if (!mime) return null;
  if (mime.includes("webm")) return "webm";
  if (mime.includes("ogg")) return "ogg";
  return null;
}

// --- Fallback WAV (16kHz, 16-bit PCM, mono) ---
async function recordWavFallback(seconds = 4) {
  if (!navigator.mediaDevices?.getUserMedia) throw new Error("No getUserMedia");
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
  const source = ctx.createMediaStreamSource(stream);

  const bufferSize = 4096;
  const recorder = ctx.createScriptProcessor(bufferSize, 1, 1);

  const samples = [];
  recorder.onaudioprocess = (e) => {
    const chData = e.inputBuffer.getChannelData(0);
    samples.push(new Float32Array(chData));
  };

  source.connect(recorder);
  recorder.connect(ctx.destination);

  await new Promise((res) => setTimeout(res, seconds * 1000));

  recorder.disconnect();
  source.disconnect();
  stream.getTracks().forEach((t) => t.stop());

  const flat = concatFloat32(samples);
  const wav = encodeWAV(flat, 16000);
  return new Blob([wav], { type: "audio/wav" });
}

function concatFloat32(chunks) {
  const length = chunks.reduce((acc, a) => acc + a.length, 0);
  const out = new Float32Array(length);
  let offset = 0;
  for (const a of chunks) { out.set(a, offset); offset += a.length; }
  return out;
}

function encodeWAV(float32Samples, sampleRate = 16000) {
  const buffer = new ArrayBuffer(44 + float32Samples.length * 2);
  const view = new DataView(buffer);

  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + float32Samples.length * 2, true);
  writeString(view, 8, "WAVE");

  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);

  writeString(view, 36, "data");
  view.setUint32(40, float32Samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < float32Samples.length; i++, offset += 2) {
    let s = Math.max(-1, Math.min(1, float32Samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return view;
}

function writeString(view, offset, str) {
  for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
}

export async function recordAudioWithFallback(seconds = 4) {
  const supportedMime = pickSupportedAudioMime();
  if (supportedMime) {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const rec = new MediaRecorder(stream, { mimeType: supportedMime });
    const chunks = [];
    return await new Promise((resolve, reject) => {
      rec.ondataavailable = (e) => e.data && e.data.size && chunks.push(e.data);
      rec.onerror = reject;
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const ext = extFromMime(supportedMime) || "webm";
        resolve({ blob: new Blob(chunks, { type: supportedMime }), fmt: ext });
      };
      rec.start();
      setTimeout(() => rec.stop(), seconds * 1000);
    });
  } else {
    const blob = await recordWavFallback(seconds);
    return { blob, fmt: "wav" };
  }
}
