// src/voice/useVoiceHint.js
import { useState, useRef } from "react";
import { startAzureSTT } from "./azureClientSST";

/**
 * Props:
 * - apiBase: string
 * - getCurrentQuestion: () => { question, type, options, answer }
 * - speakFn: (texto, opciones?) => Promise<void>
 */
export function useVoiceHint({ apiBase, getCurrentQuestion, speakFn }) {
  const [hint, setHint] = useState("");
  const [listening, setListening] = useState(false);
  const stopRef = useRef(null); // para cortar si el usuario vuelve a pulsar

  // Limpia posibles tags/think/SSML y recorta a micro-pista
  function sanitizeHint(raw) {
    let s = String(raw || "");
    s = s.replace(/<think>[\s\S]*?<\/think>/gi, "");
    s = s.replace(/<\/?[^>]+>/g, "");
    s = s.replace(
      /(^|\n)\s*(la pregunta es:|instrucciones?:|meta:|objetivo:).*$/gim,
      ""
    );
    s = s.replace(/\s{2,}/g, " ").trim();
    if (s.length > 140) {
      const cut = s.slice(0, 140);
      s = cut.replace(/[,;:.!?]\s*\S*$/, "") + "…";
    }
    return s;
  }

  // Construye pista tipo "entre A y B" si es MCQ y conocemos la respuesta
  function bandHintForMCQ(q) {
    try {
      if (!q || q.type !== "mcq" || !Array.isArray(q.options) || !q.answer) return null;
      let ans = String(q.answer).trim().toUpperCase();
      if (!/^[A-D]$/.test(ans)) {
        const idx = q.options.findIndex(o =>
          String(o).trim().toLowerCase().replace(/^[a-d]\)\s*/i, "") ===
          ans.toLowerCase().replace(/^[a-d]\)\s*/i, "")
        );
        if (idx >= 0) ans = String.fromCharCode("A".charCodeAt(0) + idx);
      }
      if (!/^[A-D]$/.test(ans)) return null;

      if (ans === "A") return "Está entre A y B.";
      if (ans === "D") return "Está entre C y D.";

      const code = ans.charCodeAt(0);
      const prev = String.fromCharCode(code - 1);
      const next = String.fromCharCode(code + 1);
      return `Está entre ${prev} y ${next}.`;
    } catch {
      return null;
    }
  }

  async function startListening() {
    // Si ya está escuchando, corta la sesión previa
    if (listening && typeof stopRef.current === "function") {
      try { await stopRef.current(); } catch {}
    }
    setListening(true);

    const { stop } = await startAzureSTT({
      apiBase,
      onFinal: async (text) => {
        try {
          const cleaned = (text || "").toLowerCase().trim();
          const hot = ["dame una pista", "pista", "una pista", "give me a hint"];
          if (!hot.some(h => cleaned.includes(h))) return;

          const qObj = typeof getCurrentQuestion === "function" ? getCurrentQuestion() : null;
          const qText = qObj?.question || "";
          if (!qText) {
            console.warn("[useVoiceHint] No question available for hint");
            return;
          }

          const r = await fetch(`${apiBase}/hint/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question: qText, meta: qObj }),
          });
          const data = await r.json().catch(() => ({}));
          const serverHint = data?.hint || "No se pudo generar la pista.";

          const clean = sanitizeHint(serverHint);
          const band = bandHintForMCQ(qObj);
          const finalHint = (clean + (band ? ` ${band}` : "")).trim();

          setHint(finalHint);

          // ⚠️ No pasamos { voice } para evitar 500 en /voice/tts/
          if (finalHint) {
            try { await speakFn?.(`Pista: ${finalHint}`); } catch {}
          }
        } catch (e) {
          console.error("Hint error:", e);
        } finally {
          try { await stop(); } catch {}
          setListening(false);
        }
      },
      onError: (e) => {
        console.error("Error STT:", e);
        setListening(false);
      },
    });

    // Guarda stop para poder cortar desde fuera
    stopRef.current = async () => {
      try { await stop(); } catch {}
    };

    // Failsafe: cortar a los 10s si nadie dijo el trigger
    setTimeout(async () => {
      try { await stop(); } catch {}
      setListening(false);
    }, 10000);
  }

  return { hint, listening, startListening };
}
