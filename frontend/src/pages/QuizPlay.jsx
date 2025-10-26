// src/pages/QuizPlay.jsx
import React, { useEffect, useMemo, useState, useRef } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Save, BookOpen } from "lucide-react";
import jsPDF from "jspdf";
import Swal from "sweetalert2";
import "../estilos/QuizPlay.css";
import { useModelProvider, withProviderHeaders } from "../ModelProviderContext";
import { getSlot } from '../utils/voiceParsing';
import { useVoiceCommands } from "../hooks/useVoiceCommands";
import { recordAudioWithFallback } from "../utils/audioRecorder";
// import { startAzureSTT } from "../voice/azureClientSST";
// import { parseAnswerCommand } from "../utils/voiceParsing";




// Convierte un AudioBuffer a WAV PCM16
function audioBufferToWavPcm16(buffer, opt = {}) {
  const numOfChan = buffer.numberOfChannels;
  const length = buffer.length * numOfChan * 2 + 44;
  const sampleRate = buffer.sampleRate;
  const out = new ArrayBuffer(length);
  const view = new DataView(out);

  let offset = 0;
  const writeString = (s) => { for (let i = 0; i < s.length; i++) view.setUint8(offset++, s.charCodeAt(i)); };
  const write16 = (d) => { view.setUint16(offset, d, true); offset += 2; };
  const write32 = (d) => { view.setUint32(offset, d, true); offset += 4; };

  // WAV header
  writeString('RIFF');               // RIFF identifier
  write32(length - 8);               // file length minus RIFF and size
  writeString('WAVE');               // RIFF type
  writeString('fmt ');               // format chunk identifier
  write32(16);                       // format chunk length
  write16(1);                        // audio format (1 = PCM)
  write16(numOfChan);                // number of channels
  write32(sampleRate);               // sample rate
  write32(sampleRate * numOfChan * 2); // byte rate
  write16(numOfChan * 2);            // block align
  write16(16);                       // bits per sample
  writeString('data');               // data chunk identifier
  write32(length - offset - 4);      // data chunk length

  // Interleave + write samples as PCM16
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

// Convierte un Blob WebM/Opus a WAV usando WebAudio
async function webmToWav(blob) {
  const arrayBuf = await blob.arrayBuffer();
  const audioCtx = new (window.OfflineAudioContext || window.AudioContext)({ sampleRate: 48000, numberOfChannels: 2, length: 48000 }); // fallback params (no se usan si es AudioContext normal)
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const decoded = await ctx.decodeAudioData(arrayBuf.slice(0)); // decode
  const wavBlob = audioBufferToWavPcm16(decoded);
  try { ctx.close(); } catch {}
  return wavBlob;
}


const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:8000/api";

// Función para exportar a PDF
const exportToPDF = (questions, answers, submitted) => {
  const pdf = new jsPDF();
  const margin = 20;
  let yPosition = margin;
  const pageHeight = pdf.internal.pageSize.height;
  const lineHeight = 8;

  // Configurar fuente
  pdf.setFont("helvetica", "bold");
  pdf.setFontSize(18);
  pdf.text("Quiz - Resultados", margin, yPosition);
  yPosition += lineHeight * 2;

  pdf.setFont("helvetica", "normal");
  pdf.setFontSize(10);
  pdf.text(`Fecha: ${new Date().toLocaleDateString()}`, margin, yPosition);
  yPosition += lineHeight * 2;

  questions.forEach((question, index) => {
    // Verificar si necesitamos nueva página
    if (yPosition > pageHeight - 60) {
      pdf.addPage();
      yPosition = margin;
    }

    // Número y pregunta
    pdf.setFont("helvetica", "bold");
    pdf.setFontSize(12);
    const questionText = `${index + 1}. ${question.question}`;
    const questionLines = pdf.splitTextToSize(questionText, 170);
    pdf.text(questionLines, margin, yPosition);
    yPosition += questionLines.length * lineHeight;

    pdf.setFont("helvetica", "normal");
    pdf.setFontSize(10);

    // Mostrar opciones si es MCQ
    if (question.type === "mcq" && question.options) {
      yPosition += lineHeight * 0.5;
      question.options.forEach((option, optIndex) => {
        const letter = String.fromCharCode("A".charCodeAt(0) + optIndex);
        const optionText = `${letter}) ${option.replace(/^[A-D]\)\s*/i, "")}`;
        const optionLines = pdf.splitTextToSize(optionText, 160);
        pdf.text(optionLines, margin + 10, yPosition);
        yPosition += optionLines.length * lineHeight;
      });
    }

    yPosition += lineHeight * 0.5;

    // Respuesta del usuario
    pdf.setFont("helvetica", "bold");
    const userAnswer = answers[index];
    let userAnswerText = "Tu respuesta: ";

    if (question.type === "mcq") {
      userAnswerText += userAnswer || "Sin responder";
    } else if (question.type === "vf") {
      userAnswerText +=
        userAnswer === true
          ? "Verdadero"
          : userAnswer === false
          ? "Falso"
          : "Sin responder";
    } else {
      userAnswerText += userAnswer || "Sin responder";
    }

    pdf.text(userAnswerText, margin, yPosition);
    yPosition += lineHeight;

    // Respuesta correcta (solo si el quiz está enviado)
    if (submitted) {
      pdf.setFont("helvetica", "bold");
      pdf.setTextColor(0, 128, 0); // Verde
      let correctAnswerText = "Respuesta correcta: ";

      if (question.type === "vf") {
        correctAnswerText += question.answer;
      } else {
        correctAnswerText += question.answer || "No disponible";
      }

      pdf.text(correctAnswerText, margin, yPosition);
      yPosition += lineHeight;
      pdf.setTextColor(0, 0, 0); // Negro
    }

    // Explicación
    if (question.explanation && submitted) {
      pdf.setFont("helvetica", "normal");
      pdf.setTextColor(100, 100, 100); // Gris
      const explanationText = `Explicación: ${question.explanation}`;
      const explanationLines = pdf.splitTextToSize(explanationText, 170);
      pdf.text(explanationLines, margin, yPosition);
      yPosition += explanationLines.length * lineHeight;
      pdf.setTextColor(0, 0, 0); // Negro
    }

    yPosition += lineHeight * 1.5; // Espacio entre preguntas
  });

  // Guardar el PDF
  pdf.save(`quiz_${new Date().toISOString().split("T")[0]}.pdf`);
};

// Función para exportar a TXT
const exportToTXT = (questions, answers, submitted) => {
  let content = "QUIZ - RESULTADOS\n";
  content += "=".repeat(50) + "\n";
  content += `Fecha: ${new Date().toLocaleDateString()}\n\n`;

  questions.forEach((question, index) => {
    content += `${index + 1}. ${question.question}\n`;

    // Mostrar opciones si es MCQ
    if (question.type === "mcq" && question.options) {
      content += "\n";
      question.options.forEach((option, optIndex) => {
        const letter = String.fromCharCode("A".charCodeAt(0) + optIndex);
        content += `   ${letter}) ${option.replace(/^[A-D]\)\s*/i, "")}\n`;
      });
    }

    content += "\n";

    // Respuesta del usuario
    const userAnswer = answers[index];
    let userAnswerText = "Tu respuesta: ";

    if (question.type === "mcq") {
      userAnswerText += userAnswer || "Sin responder";
    } else if (question.type === "vf") {
      userAnswerText +=
        userAnswer === true
          ? "Verdadero"
          : userAnswer === false
          ? "Falso"
          : "Sin responder";
    } else {
      userAnswerText += userAnswer || "Sin responder";
    }

    content += userAnswerText + "\n";

    // Respuesta correcta (solo si el quiz está enviado)
    if (submitted) {
      let correctAnswerText = "Respuesta correcta: ";

      if (question.type === "vf") {
        correctAnswerText += question.answer;
      } else {
        correctAnswerText += question.answer || "No disponible";
      }

      content += correctAnswerText + "\n";
    }

    // Explicación
    if (question.explanation && submitted) {
      content += `Explicación: ${question.explanation}\n`;
    }

    content += "\n" + "-".repeat(40) + "\n\n";
  });

  // Crear y descargar el archivo
  const element = document.createElement("a");
  const file = new Blob([content], { type: "text/plain" });
  element.href = URL.createObjectURL(file);
  element.download = `quiz_${new Date().toISOString().split("T")[0]}.txt`;
  document.body.appendChild(element);
  element.click();
  document.body.removeChild(element);
};

// Normaliza: minúsculas + sin tildes
const norm = (s="") =>
  s.toLowerCase()
   .normalize("NFD")
   .replace(/\p{Diacritic}/gu, "")
   .trim();

// Mapea palabras/numero -> letra
const numToLetter = (w) => {
  const m = {
    "1":"A","uno":"A","primera":"A","la a":"A","a":"A",
    "2":"B","dos":"B","segunda":"B","la b":"B","b":"B",
    "3":"C","tres":"C","tercera":"C","la c":"C","c":"C",
    "4":"D","cuatro":"D","cuarta":"D","la d":"D","d":"D",
  };
  return m[w] || null;
};

// Intenta extraer una letra A-D de frases comunes en español
function extractLetter(text) {
  const t = norm(text);

  // Patrones típicos
  const patterns = [
    /respuesta\s*([abcd])/i,
    /op(c|s)ion\s*([abcd])/i,
    /alternativa\s*([abcd])/i,
    /\b(letra|la)\s*([abcd])\b/i,
    /respuesta\s*(numero|nro|#)?\s*(\d+)/i,
    /op(c|s)ion\s*(\d+)/i,
    /\b(\d+|uno|dos|tres|cuatro)\b/i,
    /\b([abcd])\b/i
  ];

  for (const re of patterns) {
    const m = t.match(re);
    if (!m) continue;

    // Captura puede estar en el 1 o 2 según el patrón
    const g = (m[2] || m[1] || "").toString();
    // ¿número/palabra o letra?
    const n = g.match(/^\d+$/) ? g : g;
    const maybe = numToLetter(n);
    if (maybe) return maybe;

    // Si ya es letra a-d
    if (/[abcd]/.test(g)) return g.toUpperCase();
  }
  return null;
}

// Verdadero/Falso
function extractVF(text) {
  const t = norm(text);
  if (/\b(verdadero|cierto|true|correcto|si|afirmativo)\b/.test(t)) return true;
  if (/\b(falso|false|incorrecto|no|negativo)\b/.test(t)) return false;
  return null;
}

/**
 * Dada la transcripción y la pregunta, devuelve {ok, value} para marcar.
 * - MCQ -> value = "A" | "B" | "C" | "D"
 * - VF  -> value = true | false
 * - short -> value = string transcrito
 */
function parseSpokenAnswer(text, question) {
  if (!text || !question) return { ok:false };

  if (question.type === "mcq") {
    const letter = extractLetter(text);
    if (letter) return { ok:true, value:letter };
    // fallback: si dijo "opcion primera/segunda", etc. ya lo cubre extractLetter
    return { ok:false };
  }

  if (question.type === "vf") {
    const v = extractVF(text);
    return v === null ? { ok:false } : { ok:true, value:v };
  }

  // short answer: usamos el texto completo
  return { ok:true, value:text.trim() };
}

function LoadingScreen({ approx = 90 }) {
  const [pct, setPct] = React.useState(0);

  React.useEffect(() => {
    let raf;
    let last = performance.now();

    const tick = (t) => {
      const dt = t - last;
      last = t;

      // Incrementos suaves con pequeñas variaciones, se detiene en ~approx%
      setPct((p) => {
        if (p >= approx) return p;
        const jitter = Math.random() * 1.1 + 0.6; // 0.6–1.7
        const inc = (dt / 1000) * 12 * jitter;   // velocidad base
        const next = Math.min(approx, p + inc);
        return next;
      });

      raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [approx]);

  // Texto de estado dinámico
  const status =
    pct < 25 ? "Inicializando motor de preguntas…" :
    pct < 50 ? "Consultando proveedor LLM y preparando sesión…" :
    pct < 75 ? "Cocinando ítems y opciones con explicaciones…" :
               "Puliendo formato y validaciones…";

  return (
    <main className="qp-loading-screen" role="alert" aria-busy="true" aria-live="polite">
      <section className="qp-loading-card" aria-label="Cargando quiz">
        <div className="qp-loading-head">
          <div className="qp-loading-badge">Q</div>
          <div className="qp-loading-title">Cargando tu quiz…</div>
        </div>

        <div className="qp-progress" aria-label="Progreso de carga">
          <div
            className="qp-progress__bar"
            style={{ width: `${Math.floor(pct)}%` }}
          />
        </div>

        <div className="qp-progress-row">
          <div className="qp-progress-percent">{Math.floor(pct)}%</div>
          <div className="qp-subtle">{status}</div>
        </div>

        <div className="qp-steps">
          <div className="qp-step">⚡ <b>Rápido</b> — generado en segundos</div>
          <div className="qp-step">🧠 <b>Inteligente</b> — con explicaciones</div>
          <div className="qp-step">🎯 <b>Preciso</b> — tipos MCQ/VF/Corta</div>
        </div>

        <div className="qp-skeleton" aria-hidden="true">
          <div className="qp-skel-line"></div>
          <div className="qp-skel-line"></div>
          <div className="qp-skel-line"></div>
        </div>
      </section>
    </main>
  );
}



export default function QuizPlay(props) {
  const { sessionId: routeSessionId } = useParams();
  const sessionId = props?.sessionId ?? routeSessionId;
  const { speak, transcribeBlob } = useVoiceCommands({ sessionId });
  const { provider, headerName } = useModelProvider();
  const navigate = useNavigate();
  const location = useLocation();

  // Panel "voz" desplegable por pregunta (idx => boolean)
  const [voiceOpen, setVoiceOpen] = useState({});
  const toggleVoice = (idx) =>
    setVoiceOpen((v) => ({ ...v, [idx]: !v[idx] }));
  const [loading, setLoading] = useState(true);
  const [warning, setWarning] = useState(null);
  const [error, setError] = useState(null);

  // Preguntas "vigentes" que se muestran
  const [questions, setQuestions] = useState([]);
  // Respuestas del usuario
  const [answers, setAnswers] = useState({});
  const [submitted, setSubmitted] = useState(false);

  // Funcionalidad de guardado
  const [saving, setSaving] = useState(false);
  const [savedQuizId, setSavedQuizId] = useState(null);
  const [isLoadedQuiz, setIsLoadedQuiz] = useState(false);
  const [quizTitle, setQuizTitle] = useState("");
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);

  // Referencias y estados necesarios por listeners/efectos (declarar antes de usarlos)
  // Referencia para timeout de auto-guardado
  const saveTimeoutRef = useRef(null);

  // Historial de versiones por índice: { [idx]: [v0(original), v1, ...] }
  const [history, setHistory] = useState({});
  // Borradores de regeneración pendientes de confirmar: { [idx]: question }
  const [regenDrafts, setRegenDrafts] = useState({});

  // Escuchar intents globales del widget de voz
  useEffect(() => {
    // use getSlot util to extract numbers/indices from the result/text

  const handler = async (e) => {
      const res = e.detail || {};
  const intent = (res.intent || '').toString();
  // Soporte para diferentes campos de transcripción (backend / Azure / streaming)
  const text = (res.text || res.transcript || res.result?.text || res.DisplayText || res.displayText || '').toString().toLowerCase();

      // normalizar intent para comparaciones robustas
      const intentNorm = intent.toLowerCase();
      const intentWords = intentNorm.replace(/[_-]/g, ' ');

      const matchesAny = (words) => {
        for (const w of words) {
          if (intentWords.includes(w) || text.includes(w)) return true;
        }
        return false;
      };

      console.log('[Voice Intent] received:', intent, res);

      // CONTEXTUAL: si estamos respondiendo preguntas, intentar mapear la voz a una respuesta
      try {
        // If user specified a question index ("pregunta 1, C"), prefer that index
        const specifiedIdx = (getSlot(res, 'index') || getSlot(res, 'count'));
        const targetIdx = specifiedIdx && Number(specifiedIdx) >= 1 && Number(specifiedIdx) <= questions.length
          ? Number(specifiedIdx) - 1
          : currentQuestionIndex;

        // If the transcript includes an explicit question marker, strip it before parsing the answer
        let answerText = (res.text || text || '').toString();
        if (specifiedIdx) {
          // Remove patterns like 'pregunta 1', 'pregunta 1,' or a leading '1,' that indicate the index
          answerText = answerText.replace(/pregunta[s]?\s*(?:numero|nro|n\.?|#)?\s*\d{1,3}/i, '');
          answerText = answerText.replace(/^\s*\d{1,3}\s*[,.:\-]?\s*/i, '');
        }

        const q = questions[targetIdx];
        if (q) {
          const parsedAnswer = parseSpokenAnswer(answerText, q);
          if (parsedAnswer && parsedAnswer.ok) {
            // aplicar respuesta según tipo
            if (q.type === 'mcq') {
              const letter = parsedAnswer.value; // 'A'..'D'
              const optIdx = letter.charCodeAt(0) - 'A'.charCodeAt(0);
              handleSelectMCQ(targetIdx, optIdx);
              return; // acción tomada
            } else if (q.type === 'vf') {
              handleToggleVF(targetIdx, parsedAnswer.value);
              return;
            } else {
              handleShortChange(targetIdx, parsedAnswer.value);
              return;
            }
          }
        }
      } catch (e) {
        console.error('Error applying spoken answer:', e);
      }

      // Navegación
      if (/navigate_next|siguiente|next|avanza|sigue/.test(intent) || /siguiente|adelante|avanza/.test(text)) {
        setCurrentQuestionIndex((i) => Math.min(questions.length - 1, i + 1));
        return;
      }
      if (/navigate_previous|anterior|back|volver/.test(intent) || /anterior|atrás|volver/.test(text)) {
        setCurrentQuestionIndex((i) => Math.max(0, i - 1));
        return;
      }

      // PRIORIDAD: acciones estructurales (duplicar, eliminar, regenerar, exportar)
      // Estas deben ejecutarse incluso si el backend devolvió otra intención (p.ej. read_question)
      if (matchesAny(['duplicate', 'duplicar', 'clonar', 'copiar', 'copia'])) {
        const idx = getSlot(res, 'index') || getSlot(res, 'count') || (text.match(/\b(\d{1,3})\b/)||[])[1];
        const target = (idx && Number(idx) >= 1 && Number(idx) <= questions.length) ? Number(idx) - 1 : currentQuestionIndex;
        handleDuplicateQuestion(target);
        try { await speak(`Duplicada la pregunta ${target + 1}`).catch(()=>{}); } catch(e){}
        return;
      }

      if (matchesAny(['delete', 'eliminar', 'borrar', 'quitar', 'suprimir', 'remover', 'sacar'])) {
        const idx = getSlot(res, 'index') || getSlot(res, 'count') || (text.match(/\b(\d{1,3})\b/)||[])[1];
        const target = (idx && Number(idx) >= 1 && Number(idx) <= questions.length) ? Number(idx) - 1 : currentQuestionIndex;
        try {
          handleDeleteQuestion(target);
          await speak(`Pregunta ${target + 1} eliminada`).catch(()=>{});
        } catch (e) {
          console.error('Error deleting question via voice intent', e);
        }
        return;
      }

      if (matchesAny(['regenerate', 'regenerar', 'regenera', 'vuelve a generar', 'renovar', 'volver a generar'])) {
        const idx = getSlot(res, 'index') || getSlot(res, 'count') || (text.match(/\b(\d{1,3})\b/)||[])[1];
        const target = (idx && Number(idx) >= 1 && Number(idx) <= questions.length) ? Number(idx) - 1 : currentQuestionIndex;
        handleStartRegenerate(target);
        return;
      }

      // Si ya existe una variante (regenDrafts[target]) permitir acciones por voz: reemplazar, cancelar, regenerar de nuevo
      // Reemplazar / Confirmar reemplazo
      if (matchesAny(['replace', 'reemplazar', 'confirmar reemplazo', 'aceptar', 'confirmar'])) {
        const idx = getSlot(res, 'index') || getSlot(res, 'count') || (text.match(/\b(\d{1,3})\b/)||[])[1];
        const target = (idx && Number(idx) >= 1 && Number(idx) <= questions.length) ? Number(idx) - 1 : currentQuestionIndex;
        if (regenDrafts && regenDrafts[target]) {
          try {
            await handleConfirmReplace(target);
            try { await speak(`Pregunta ${target + 1} reemplazada`).catch(()=>{}); } catch(e){}
          } catch (e) {
            console.error('Error replacing question via voice', e);
          }
        } else {
          try { await speak('No hay variante disponible para reemplazar en esa pregunta').catch(()=>{}); } catch(e){}
        }
        return;
      }

      // Cancelar variante (descartar draft)
      if (matchesAny(['cancel', 'cancelar', 'descartar', 'no reemplazar'])) {
        const idx = getSlot(res, 'index') || getSlot(res, 'count') || (text.match(/\b(\d{1,3})\b/)||[])[1];
        const target = (idx && Number(idx) >= 1 && Number(idx) <= questions.length) ? Number(idx) - 1 : currentQuestionIndex;
        if (regenDrafts && regenDrafts[target]) {
          try {
            handleCancelRegenerate(target);
            try { await speak(`Vista previa cancelada para la pregunta ${target + 1}`).catch(()=>{}); } catch(e){}
          } catch (e) {
            console.error('Error cancelling regenerate draft via voice', e);
          }
        } else {
          try { await speak('No hay ninguna variante para cancelar en esa pregunta').catch(()=>{}); } catch(e){}
        }
        return;
      }

      // Regenerar de nuevo (generar otra variante)
      if (matchesAny(['regenerate again', 'regenerar de nuevo', 'regenerar otra vez', 'regenerar de nuevo pregunta', 'regenerar otra'])) {
        const idx = getSlot(res, 'index') || getSlot(res, 'count') || (text.match(/\b(\d{1,3})\b/)||[])[1];
        const target = (idx && Number(idx) >= 1 && Number(idx) <= questions.length) ? Number(idx) - 1 : currentQuestionIndex;
        try {
          await handleRegenerateAgain(target);
          try { await speak(`Generando otra variante para la pregunta ${target + 1}`).catch(()=>{}); } catch(e){}
        } catch (e) {
          console.error('Error regenerating again via voice', e);
        }
        return;
      }

      if (matchesAny(['export', 'exportar', 'exporta', 'descargar', 'guardar', 'bajar'])) {
        if (text.includes('pdf')) exportToPDF(questions, answers, submitted);
        else if (text.includes('txt') || text.includes('texto')) exportToTXT(questions, answers, submitted);
        else exportToPDF(questions, answers, submitted);
        try { await speak('Exportado').catch(()=>{}); } catch(e){}
        return;
      }

      // Leer pregunta
      if (/read_question|leer|lee/.test(intent) || /lee|leer/.test(text)) {
        const idx = getSlot(res, 'index') || getSlot(res, 'count');
        if (idx && idx >= 1 && idx <= questions.length) {
          readQuestion(idx - 1);
        } else {
          readQuestion(currentQuestionIndex);
        }
        return;
      }

      // Mostrar respuestas (pop-up)
      if (/show_answers|mostrar|respuestas|muestra|ver respuestas/.test(intent) || /mostrar|respuestas|muestra|ver respuestas/.test(text)) {
        const content = questions.map((q, i) => {
          const ans = q.type === 'vf' ? String(q.answer) : String(q.answer || '');
          return `${i + 1}. ${q.question}\nRespuesta: ${ans}\n`;
        }).join('\n');
        try {
          Swal.fire({ title: 'Respuestas', html: `<pre style="text-align:left">${content}</pre>`, width: 700 });
        } catch (e) {
          alert(content);
        }
        return;
      }

      // Exportar: PDF o TXT
      if (/export_quiz|exportar|exporta|descargar|guarda?r?/.test(intent) || /exporta|exportar|pdf|txt|descargar/.test(text)) {
        const idx = getSlot(res, 'index') || getSlot(res, 'count');
        // Si especifica PDF/TXT en la frase, preferirlo
        if (/pdf/.test(text)) {
          exportToPDF(questions, answers, submitted);
          try { await speak('Exportado a PDF').catch(()=>{}); } catch(e){}
        } else if (/txt/.test(text) || /texto/.test(text)) {
          exportToTXT(questions, answers, submitted);
          try { await speak('Exportado a TXT').catch(()=>{}); } catch(e){}
        } else {
          // default PDF
          exportToPDF(questions, answers, submitted);
          try { await speak('Exportado a PDF').catch(()=>{}); } catch(e){}
        }
        return;
      }
    };

    window.addEventListener('voice:intent', handler);
    return () => window.removeEventListener('voice:intent', handler);
  }, [questions, currentQuestionIndex, answers, submitted, regenDrafts, speak]);

  const leerPreguntaActual = async () => {
    const q = questions[currentQuestionIndex];
    if (!q) return;
    const enunciado = q.text || q.question;
    const texto = Array.isArray(q.options) && q.options.length
      ? `${enunciado}. ${q.options.map((o, j) => `Opción ${j + 1}: ${o}`).join(". ")}`
      : enunciado;
    try { await speak(texto, { voice: "es-ES-AlvaroNeural" }); } catch {}
  };

  // Helpers para mapear STT -> respuesta
  const _mapChoiceFromText = (t) => {
    const s = (t || "").toLowerCase();
    if (/\b[a-d]\b/.test(s)) return s.match(/\b([a-d])\b/)[1].toUpperCase();
    if (/\b[1-4]\b/.test(s)) {
      const n = parseInt(s.match(/\b([1-4])\b/)[1], 10);
      return String.fromCharCode("A".charCodeAt(0) + (n - 1));
    }
    if (s.includes("primera")) return "A";
    if (s.includes("segunda")) return "B";
    if (s.includes("tercera")) return "C";
    if (s.includes("cuarta")) return "D";
    return null;
  };

  const _mapVF = (t) => {
    const s = (t || "").toLowerCase();
    if (/(verdadero|cierto|correcto|sí|si)/.test(s)) return true;
    if (/(falso|incorrecto|no)/.test(s)) return false;
    return null;
  };

  // const dictarRespuesta = async () => {
  //   try {
  //     const { blob, fmt } = await recordAudioWithFallback(4);
  //     const out = await transcribeBlob(blob, { language: "es-ES", fmt });
  //     const heard = out?.text || "";
  //     const q = questions[currentQuestionIndex];
  //     if (!q) return;

  //     if (q.type === "mcq") {
  //       const choice = _mapChoiceFromText(heard);
  //       setAnswers(prev => ({ ...prev, [currentQuestionIndex]: choice || heard }));
  //     } else if (q.type === "vf") {
  //       const bool = _mapVF(heard);
  //       if (bool !== null) setAnswers(prev => ({ ...prev, [currentQuestionIndex]: bool }));
  //     } else {
  //       setAnswers(prev => ({ ...prev, [currentQuestionIndex]: heard }));
  //     }
  //   } catch (e) {
  //     console.error("STT error", e);
  //     alert("No se pudo grabar audio en este navegador. Revisa permisos o prueba en Chrome/Edge.");
  //   }
  // };

  



  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        // Verificar si viene de un quiz guardado
        const savedQuizData = location.state?.savedQuizData;
        if (savedQuizData) {
          // Cargar datos del quiz guardado
          if (!alive) return;
          setIsLoadedQuiz(true);
          setSavedQuizId(savedQuizData.quiz_id);
          setQuizTitle(savedQuizData.title || "");
          setQuestions(savedQuizData.questions || []);
          setAnswers(savedQuizData.user_answers || {});
          setCurrentQuestionIndex(savedQuizData.current_question || 0);

          // Inicializar historial
          const initHistory = {};
          (savedQuizData.questions || []).forEach(
            (q, i) => (initHistory[i] = [q])
          );
          setHistory(initHistory);

          setLoading(false);
          return;
        }

        // Carga normal de sesión nueva
        const resp = await fetch(`${API_BASE}/preview/`, withProviderHeaders({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId }),
        }, provider, headerName));
        const data = await resp.json();
        // --- LOG de proveedor efectivo y fallback ---
        const usedHeader = resp.headers.get("x-llm-effective-provider");
        const fbHeader = resp.headers.get("x-llm-fallback");

        const used = usedHeader || data.source || "(desconocido)";
        const fallback = (fbHeader ?? (data.fallback_used ? "1" : "0")) === "1";

        console.log("[LLM][QuizPlay] requested:", provider, "used:", used, "fallback:", fallback);
        // --------------------------------------------

        if (!resp.ok)
          throw new Error(data?.error || "No se pudo cargar el quiz");
        if (!alive) return;

        const loaded = Array.isArray(data.preview) ? data.preview : [];
        setQuestions(loaded);
        // Inicializa historial con la versión original
        const initHistory = {};
        loaded.forEach((q, i) => (initHistory[i] = [q]));
        setHistory(initHistory);

        if (data.warning) setWarning(data.warning);
      } catch (e) {
        if (!alive) return;
        setError(e.message);
      } finally {
        if (!alive) return;
        setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [sessionId]);

  // Auto-guardar progreso cuando cambian las respuestas o el índice de pregunta actual
  useEffect(() => {
    // Solo auto-guardar si es un quiz cargado (no sesiones nuevas) y hay respuestas
    if (savedQuizId && Object.keys(answers).length > 0 && !submitted) {
      // Limpiar timeout anterior
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }

      // Guardar después de 2 segundos de inactividad
      saveTimeoutRef.current = setTimeout(() => {
        console.log("🔄 Auto-guardando progreso...");
        saveQuizProgress(false, answers); // false = no mostrar confirmación
      }, 2000);
    }

    // Cleanup al desmontar
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
    };
  }, [answers, currentQuestionIndex, savedQuizId, submitted]);

  // -------- Regenerar (HU-05) ----------
  const requestRemoteRegeneration = async (idx) => {
    try {
      const q = questions[idx];
      const resp = await fetch(`${API_BASE}/regenerate/`, withProviderHeaders({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          index: idx,
          type: q?.type, // mantiene tipo
        }),
      }, provider, headerName));

      const data = await resp.json();
      const usedHeader = resp.headers.get("x-llm-effective-provider");
      const fbHeader = resp.headers.get("x-llm-fallback");
      const used = usedHeader || data.source || "(desconocido)";
      const fallback = (fbHeader ?? (data.fallback_used ? "1" : "0")) === "1";
      console.log("[LLM][Regenerate] requested:", provider, "used:", used, "fallback:", fallback);

      if (!resp.ok) throw new Error(data?.error || "No se pudo regenerar");

      // El backend responde { question: {...}, source: "gemini|placeholder", debug? }
      if (data && data.question && typeof data.question === "object") {
        return data.question; // ← devuelve SOLO la pregunta
      }
      throw new Error("Respuesta inválida del servidor");
    } catch (e) {
      // Fallback local de prototipo (si no existe backend o falló)
      const base = questions[idx];
      const clone = JSON.parse(JSON.stringify(base || {}));
      clone.question =
        (clone.question || "Pregunta").replace(/\s*— variante.*/i, "") +
        " — variante";
      if (Array.isArray(clone.options)) {
        const shuffled = [...clone.options];
        for (let i = shuffled.length - 1; i > 0; i--) {
          const j = Math.floor(Math.random() * (i + 1));
          [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
        }
        clone.options = shuffled;
      }
      return clone;
    }
  };

  const handleRegenerateAgain = async (idx) => {
    const newer = await requestRemoteRegeneration(idx);
    setRegenDrafts((p) => ({ ...p, [idx]: newer }));
  };

  const handleStartRegenerate = async (idx) => {
    const newQ = await requestRemoteRegeneration(idx);
    setRegenDrafts((p) => ({ ...p, [idx]: newQ }));
  };

  const handleCancelRegenerate = (idx) => {
    setRegenDrafts((p) => {
      const copy = { ...p };
      delete copy[idx];
      return copy;
    });
  };

  const handleConfirmReplace = async (idx) => {
    const candidate = regenDrafts[idx];
    if (!candidate) return;

    // Empuja al historial y reemplaza visible (estado local)
    setHistory((h) => {
      const copy = { ...h };
      const prev = copy[idx] || [];
      copy[idx] = [...prev, candidate];
      return copy;
    });
    setQuestions((qs) => {
      const next = [...qs];
      next[idx] = candidate;
      return next;
    });
    setRegenDrafts((p) => {
      const copy = { ...p };
      delete copy[idx];
      return copy;
    });
    setAnswers((a) => {
      const copy = { ...a };
      delete copy[idx];
      return copy;
    });

    // Persistir en servidor para que futuras regeneraciones usen esta versión
    try {
      await fetch(`${API_BASE}/confirm-replace/`, withProviderHeaders({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          index: idx,
          question: candidate,
        }),
      }, provider, headerName));
      // Toast de éxito
      window.alert("¡Pregunta reemplazada exitosamente!");
    } catch (_) {
      // no romper la UX si falla; podrías mostrar un toast si quieres
      window.alert("¡Pregunta reemplazada con error!");
    }
  };

  // -------- Interacciones del quiz ----------
  const handleSelectMCQ = (idx, optIdx) => {
    const letter = String.fromCharCode("A".charCodeAt(0) + optIdx);
    setAnswers((p) => ({ ...p, [idx]: letter }));
  };

  // Leer una pregunta específica
const readQuestion = async (idx) => {
  const q = questions[idx];
  if (!q) return;
  const texto = q.options?.length
    ? `${q.question}. ${q.options.map((o, j) => `Opción ${j + 1}: ${o}`).join(". ")}`
    : q.question;
  try { await speak(texto, { voice: "es-ES-AlvaroNeural" }); } catch {}
};

// Dentro de QuizPlay.jsx
const dictateForQuestion = async (idx) => {
  try {
    console.log("[dictateForQuestion] START idx=", idx);

    // 1) Graba 5s (webm/opus, ogg, etc. según navegador)
    const { blob } = await recordAudioWithFallback(5);
    console.log("[dictateForQuestion] raw blob:", blob?.type, blob?.size);

    if (!blob || blob.size < 2048) {
      console.warn("Audio vacío o muy pequeño", { size: blob?.size, type: blob?.type });
      Swal.fire("No se oyó nada", "Intenta hablar más cerca del micrófono.", "info");
      return;
    }

    // 2) Convierte SIEMPRE a WAV PCM16
    const wav = await webmToWav(blob);
    console.log("[dictateForQuestion] wav blob:", wav?.type, wav?.size);

    // 3) Transcribe WAV
    const out = await transcribeBlob(wav, { language: "es-ES", fmt: "wav" });
    console.log("[dictateForQuestion] STT response:", out);

    // 4) Extrae texto de posibles campos
    const said =
      (out && (out.text || out.transcript || out.result?.text || out.DisplayText || out.NBest?.[0]?.Lexical))?.trim() || "";

    console.log("[dictateForQuestion] said:", JSON.stringify(said));

    if (!said) {
      Swal.fire({
        icon: "info",
        title: "Sin texto reconocido",
        html: `
          <div style="text-align:left">
            • Verifica el volumen/micrófono.<br/>
            • Habla durante ~2–3 segundos.<br/>
            • Ejemplos: "respuesta A", "verdadero", "la tercera".<br/>
            • Enviado: WAV (${wav.size} bytes)
          </div>
        `,
      });
      return;
    }

    // 5) Parsear y marcar
    const q = questions[idx];
    const parsed = parseSpokenAnswer(said, q);
    console.debug("[dictateForQuestion] parsed:", parsed, "type=", q?.type);

    if (!parsed.ok) {
      Swal.fire("No entendido", `No pude interpretar: "${said}"`, "info");
      return;
    }

    if (q.type === "mcq") {
      const letter = parsed.value; // "A"..."D"
      const optIdx = letter.charCodeAt(0) - "A".charCodeAt(0);
      handleSelectMCQ(idx, optIdx);
    } else if (q.type === "vf") {
      handleToggleVF(idx, parsed.value); // true/false
    } else {
      handleShortChange(idx, parsed.value); // string
    }
  } catch (e) {
    console.error("Dictado/STT error", e);
    const msg = (e && e.message) || "";
    const name = e && (e.name || "");
    const perm = name === "NotAllowedError" || /permission/i.test(msg);
    const support = /MediaRecorder|getUserMedia|not supported/i.test(msg);
    Swal.fire(
      "No se pudo grabar",
      perm
        ? "Permite el uso del micrófono en tu navegador."
        : support
        ? "Prueba en Chrome/Edge, o actualiza tu navegador."
        : "Ocurrió un error al transcribir.",
      "warning"
    );
  }
};






// DEBUG: probar desde consola: window.dictateForQuestion(0)
 useEffect(() => {
   window.dictateForQuestion = dictateForQuestion;
 }, []);




  const handleToggleVF = (idx, val) => {
    setAnswers((p) => ({ ...p, [idx]: val }));
  };

  const handleShortChange = (idx, val) => {
    setAnswers((p) => ({ ...p, [idx]: val }));
  };

  // 🔽 NUEVAS FUNCIONES
  // Eliminar pregunta
  const handleDeleteQuestion = (idx) => {
    setQuestions((qs) => qs.filter((_, i) => i !== idx));
    setAnswers((a) => {
      const copy = { ...a };
      delete copy[idx];
      return copy;
    });
  };

  // Duplicar pregunta
  const handleDuplicateQuestion = (idx) => {
    setQuestions((qs) => {
      const copy = [...qs];
      copy.splice(idx + 1, 0, { ...qs[idx] }); // Insertar copia después
      return copy;
    });
  };

  const submitQuiz = async () => {
    setSubmitted(true);

    // Si es un quiz guardado, marcar como completado
    if (savedQuizId) {
      try {
        await fetch(`${API_BASE}/saved-quizzes/${savedQuizId}/`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            current_question: questions.length, // Última pregunta
            user_answers: answers,
            is_completed: true,
            score: {}, // Se puede calcular si es necesario
          }),
        });
        console.log("✅ Quiz marcado como completado");
      } catch (error) {
        console.error("❌ Error al marcar quiz como completado:", error);
      }
    }
  };
  const resetQuiz = () => {
    setAnswers({});
    setSubmitted(false);
    setCurrentQuestionIndex(0);
    // Desplazarse al top suavemente
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // Función específica para reintento completo
  const retryQuiz = async () => {
    const result = await Swal.fire({
      title: "🔄 Reintentar Quiz",
      text: "¿Deseas reintentar este cuestionario con la misma configuración?",
      icon: "question",
      showCancelButton: true,
      confirmButtonText: "Sí, reintentar",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#8b5cf6",
      cancelButtonColor: "#6b7280",
    });

    if (result.isConfirmed) {
      resetQuiz();
      Swal.fire({
        title: "¡Listo!",
        text: "Quiz reiniciado. ¡Buena suerte!",
        icon: "success",
        timer: 2000,
        showConfirmButton: false,
      });
    }
  };

  // -------- Funciones de guardado ----------
  const saveQuizProgress = async (
    showConfirmation = true,
    answersToSave = null
  ) => {
    if (saving || submitted) return;

    const currentAnswers = answersToSave || answers;

    try {
      setSaving(true);

      // Verificar conectividad con el backend primero
      console.log("🔍 Verificando conectividad con backend...");
      try {
        const healthCheck = await fetch(`${API_BASE}/health/`, {
          method: "GET",
          timeout: 5000,
        });
        console.log("✅ Backend respondió:", healthCheck.status);
      } catch (connectError) {
        console.error("❌ Backend no responde:", connectError);
        throw new Error(
          `No se puede conectar con el servidor. Verifica que esté funcionando en ${API_BASE}`
        );
      }

      let quizId = savedQuizId;
      let title = quizTitle;

      // Si no hay quiz guardado, preguntar por título
      if (!quizId) {
        const { value: inputTitle } = await Swal.fire({
          title: "Guardar progreso",
          text: "Ingresa un título para este cuestionario:",
          input: "text",
          inputPlaceholder: "Mi cuestionario...",
          showCancelButton: true,
          confirmButtonText: "Guardar",
          cancelButtonText: "Cancelar",
          inputValidator: (value) => {
            if (!value || value.trim().length < 3) {
              return "El título debe tener al menos 3 caracteres";
            }
          },
        });

        if (!inputTitle) {
          setSaving(false);
          return;
        }
        title = inputTitle.trim();
      }

      const payload = quizId
        ? // Actualizar quiz existente - solo enviar campos necesarios
          {
            current_question: currentQuestionIndex,
            user_answers: currentAnswers,
            is_completed: submitted,
          }
        : // Crear nuevo quiz guardado - enviar todos los datos
          {
            title,
            session_id: sessionId,
            questions,
            user_answers: currentAnswers,
            current_question: currentQuestionIndex,
            is_completed: false,
          };

      const endpoint = quizId
        ? `${API_BASE}/saved-quizzes/${quizId}/`
        : `${API_BASE}/saved-quizzes/`;

      const method = quizId ? "PUT" : "POST";

      console.log("=== DEBUG AUTOGUARDADO ===");
      console.log("Payload a enviar:", JSON.stringify(payload, null, 2));
      console.log("Quiz ID:", quizId, "Method:", method);
      console.log("Endpoint:", endpoint);
      console.log("CurrentAnswers:", currentAnswers);
      console.log("SessionId:", sessionId);
      console.log("Questions length:", questions?.length);

      const response = await fetch(endpoint, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      console.log("Response status:", response.status);
      console.log("Response ok:", response.ok);

      // Intentar leer la respuesta como texto primero
      const responseText = await response.text();
      console.log("Response text:", responseText);

      let result = {};
      try {
        result = JSON.parse(responseText);
        console.log("Respuesta del backend (parsed):", result);
      } catch (parseError) {
        console.error("Error parsing JSON response:", parseError);
        console.error("Raw response:", responseText);
        throw new Error(
          `Error parsing server response: ${responseText.substring(0, 200)}...`
        );
      }

      if (!response.ok) {
        console.error("=== ERROR DEL BACKEND ===");
        console.error("Status:", response.status);
        console.error("StatusText:", response.statusText);
        console.error("Response headers:", [...response.headers.entries()]);
        console.error("Result:", result);

        const errorMessage =
          result.error ||
          (result.errors
            ? JSON.stringify(result.errors)
            : `Error ${response.status}: ${response.statusText}`);
        throw new Error(errorMessage);
      }

      // Si es nuevo, guardar el ID
      if (!quizId) {
        setSavedQuizId(result.saved_quiz.id);
        setQuizTitle(title);
        setIsLoadedQuiz(true);
      }

      if (showConfirmation) {
        await Swal.fire({
          title: "Progreso guardado",
          text: "Tu progreso ha sido guardado exitosamente",
          icon: "success",
          timer: 1500,
          timerProgressBar: true,
          showConfirmButton: false,
        });
      }
    } catch (error) {
      console.error("=== ERROR EN SAVE QUIZ PROGRESS ===");
      console.error("Error type:", error.constructor.name);
      console.error("Error message:", error.message);
      console.error("Error stack:", error.stack);
      console.error("Current state:", {
        saving,
        submitted,
        savedQuizId,
        quizTitle,
        answersLength: Object.keys(answers).length,
        currentQuestionIndex,
        questionsLength: questions?.length,
        API_BASE,
      });

      if (showConfirmation) {
        const errorInfo = error.message.includes("Failed to fetch")
          ? 'El servidor backend no está funcionando. Por favor, inicia el servidor Django con "python manage.py runserver"'
          : error.message;

        Swal.fire({
          title: "Error al guardar",
          html: `
            <div style="text-align: left; font-family: monospace; font-size: 12px;">
              <strong>Error:</strong> ${errorInfo}<br>
              <strong>Tipo:</strong> ${error.constructor.name}<br>
              <strong>Estado:</strong> Quiz ID: ${savedQuizId || "nuevo"}<br>
              <strong>Respuestas:</strong> ${Object.keys(answers).length}<br>
              <strong>API Base:</strong> ${API_BASE}<br>
              <strong>Sugerencias:</strong><br>
              • Verifica que el servidor Django esté funcionando<br>
              • Revisa la consola del navegador para más detalles<br>
              • Asegúrate de que el backend esté en puerto 8000
            </div>
          `,
          icon: "error",
          width: 600,
        });
      }
    } finally {
      setSaving(false);
    }
  };

  // Auto-guardar cuando cambian las respuestas (solo si ya está guardado)
  useEffect(() => {
    // Solo auto-guardar si:
    // 1. Ya existe un quiz guardado (savedQuizId)
    // 2. Hay respuestas para guardar
    // 3. No está actualmente guardando
    // 4. El quiz no está enviado aún
    if (
      savedQuizId &&
      Object.keys(answers).length > 0 &&
      !saving &&
      !submitted
    ) {
      // Cancelar timeout anterior si existe
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }

      // Nuevo timeout para auto-guardado
      const timeoutId = setTimeout(() => {
        console.log("🔄 EJECUTANDO AUTO-GUARDADO...", {
          timestamp: new Date().toLocaleTimeString(),
          savedQuizId,
          answersCount: Object.keys(answers).length,
          saving,
          submitted,
        });
        saveQuizProgress(false); // Sin confirmación para auto-guardado
      }, 2000); // Guardar 2 segundos después del último cambio

      saveTimeoutRef.current = timeoutId;

      // Cleanup del timeout
      return () => {
        if (saveTimeoutRef.current) {
          clearTimeout(saveTimeoutRef.current);
          saveTimeoutRef.current = null;
        }
      };
    }
  }, [answers, savedQuizId, saving, submitted]);

  // Actualizar índice de pregunta actual cuando cambian las respuestas
  useEffect(() => {
    const answeredQuestions = Object.keys(answers).map(Number);
    const maxAnswered =
      answeredQuestions.length > 0 ? Math.max(...answeredQuestions) : -1;
    setCurrentQuestionIndex(Math.min(maxAnswered + 1, questions.length - 1));
  }, [answers, questions.length]);

  // -------- Sistema de puntaje avanzado ----------
  // Función para evaluar respuestas cortas de manera más inteligente
  const evaluateShortAnswer = (userAnswer, correctAnswer) => {
    if (!userAnswer || !correctAnswer) return false;

    const normalizeText = (text) => {
      return text
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "") // Remove accents
        .replace(/[^\w\s]/g, " ") // Replace punctuation with spaces
        .replace(/\s+/g, " ") // Normalize whitespace
        .trim();
    };

    const userNormalized = normalizeText(userAnswer);
    const correctNormalized = normalizeText(correctAnswer);

    // Exact match
    if (userNormalized === correctNormalized) return true;

    // Split into words for comparison
    const userWords = userNormalized.split(" ").filter((w) => w.length > 2);
    const correctWords = correctNormalized
      .split(" ")
      .filter((w) => w.length > 2);

    if (correctWords.length === 0) return false;

    // Calculate word overlap
    const matches = correctWords.filter((correctWord) =>
      userWords.some((userWord) => {
        // Exact word match
        if (userWord === correctWord) return true;

        // Partial match for longer words (contains or is contained)
        if (correctWord.length > 4 && userWord.length > 4) {
          return (
            userWord.includes(correctWord) || correctWord.includes(userWord)
          );
        }

        return false;
      })
    );

    // Consider correct if 60% of key words match
    const matchPercentage = matches.length / correctWords.length;
    return matchPercentage >= 0.6;
  };

  const detailedScoring = useMemo(() => {
    const results = {
      // Puntaje general
      total: questions.length,
      answered: Object.keys(answers).length,
      correct: 0,
      percentage: 0,

      // Por tipo de pregunta
      byType: {
        mcq: { total: 0, correct: 0, percentage: 0 },
        vf: { total: 0, correct: 0, percentage: 0 },
        short: { total: 0, correct: 0, percentage: 0 },
      },

      // Por dificultad (si está disponible)
      byDifficulty: {},

      // Detalles por pregunta
      questionDetails: [],
    };

    questions.forEach((q, idx) => {
      const userAnswer = answers[idx];
      const hasAnswer =
        userAnswer !== undefined && userAnswer !== null && userAnswer !== "";
      let isCorrect = false;

      // Determinar si es correcta
      if (hasAnswer) {
        if (q.type === "mcq") {
          const expected = String(q.answer ?? "")
            .trim()
            .toUpperCase()
            .charAt(0);
          const given = String(userAnswer ?? "")
            .trim()
            .toUpperCase()
            .charAt(0);
          isCorrect = expected && given && expected === given;
        } else if (q.type === "vf") {
          const expected = String(q.answer ?? "").toLowerCase();
          const given =
            typeof userAnswer === "boolean"
              ? userAnswer
                ? "verdadero"
                : "falso"
              : String(userAnswer ?? "").toLowerCase();
          isCorrect = expected && given && expected === given;
        } else if (q.type === "short") {
          // Usar la función de evaluación inteligente para respuestas cortas
          isCorrect = evaluateShortAnswer(userAnswer, q.answer);
        }
      }

      // Actualizar contadores por tipo
      if (results.byType[q.type]) {
        results.byType[q.type].total++;
        if (hasAnswer && isCorrect) {
          results.byType[q.type].correct++;
          results.correct++;
        }
      }

      // Guardar detalles de la pregunta
      results.questionDetails.push({
        index: idx,
        type: q.type,
        question: q.question,
        userAnswer,
        correctAnswer: q.answer,
        isCorrect,
        hasAnswer,
        explanation: q.explanation,
      });
    });

    // Calcular porcentajes
    results.percentage =
      results.total > 0
        ? Math.round((results.correct / results.total) * 100)
        : 0;

    Object.keys(results.byType).forEach((type) => {
      const typeData = results.byType[type];
      typeData.percentage =
        typeData.total > 0
          ? Math.round((typeData.correct / typeData.total) * 100)
          : 0;
    });

    return results;
  }, [questions, answers]);

  if (loading) {
    return <LoadingScreen approx={92} />;
  }

  if (error) {
    return (
      <main className="shell qp-root">
        <section className="card qp-error">
          <h2>Error</h2>
          <p>{error}</p>
          <div className="qp-actions" style={{ marginTop: 12 }}>
            <button className="btn btn-indigo" onClick={() => navigate(-1)}>
              Volver
            </button>
          </div>
        </section>
      </main>
    );
  }

return (
  <main className="shell qp-root">
    <header className="hero qp-header">
      <div className="qp-header-content">
        <div className="qp-title-section">
          <h1>{isLoadedQuiz && quizTitle ? quizTitle : "Tu Quiz"}</h1>
          <p>Responde las preguntas. Cuando termines, presiona "Calificar".</p>
          {warning && <p className="qp-warning">⚠️ {warning}</p>}
          {isLoadedQuiz && (
            <p className="qp-saved-info">💾 Quiz guardado - Se guarda automáticamente tu progreso</p>
          )}
        </div>

        {/* Botones de acción */}
        <div className="qp-action-buttons">
          <button
            className="btn btn-primary"
            onClick={() => navigate("/")}
            title="Volver al inicio"
          >
            🏠 Inicio
          </button>

          {!submitted && (
            <button
              className="btn btn-save"
              onClick={() => saveQuizProgress()}
              disabled={saving}
              title="Guardar progreso del quiz"
            >
              <Save size={16} />
              {saving ? "Guardando..." : isLoadedQuiz ? "Guardar" : "Guardar Quiz"}
            </button>
          )}

          <button
            className="btn btn-secondary"
            onClick={() => navigate("/saved-quizzes")}
            title="Ver cuestionarios guardados"
          >
            <BookOpen size={16} />
            Mis Quizzes
          </button>
        </div>
      </div>

      {/* Botones de exportación */}
      <div className="qp-export-buttons">
        <button
          className="btn btn-export btn-pdf"
          onClick={() => exportToPDF(questions, answers, submitted)}
          title="Exportar quiz a PDF"
        >
          📄 Exportar PDF
        </button>
        <button
          className="btn btn-export btn-txt"
          onClick={() => exportToTXT(questions, answers, submitted)}
          title="Exportar quiz a TXT"
        >
          📝 Exportar TXT
        </button>
      </div>
    </header>

    <section className="card">
      <div className="qp-body">
        <AnimatePresence>
          {questions.map((q, idx) => {
            const draft = regenDrafts[idx];
            const selectedLetter =
              (answers[idx] ?? "")
                .toString()
                .toUpperCase()
                .charAt(0);

            return (
              <motion.div
                key={idx}
                className="qp-question"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
              >
                <div className="qp-title">
                  {idx + 1}. {q.question}
                </div>

                {/* 🔊🎙️ Controles de voz por pregunta (colapsables) */}
                <div className="qp-voice-row">
                  <button
                    className="btn btn-ghost"
                    onClick={() => toggleVoice(idx)}
                    title="Controles de voz"
                  >
                    🎤 Voz {voiceOpen[idx] ? "▴" : "▾"}
                  </button>

                  {voiceOpen[idx] && (
                    <div className="qp-voice-panel">
                      <button className="btn btn-indigo" onClick={() => readQuestion(idx)}>
                        🔊 Leer
                      </button>
                      <button
                        className="btn btn-green-outline"
                        type="button"
                        onClick={() => {
                          console.log("[QuizPlay] click en Dictar idx=", idx);
                          dictateForQuestion(idx);
                        }}
                      >
                        🎙️ Dictar esta
                      </button>
                    </div>
                  )}
                </div>

                {/* MCQ */}
                {q.type === "mcq" && Array.isArray(q.options) && (
                  <div className="qp-options">
                    {q.options.map((opt, i) => {
                      const letter = String.fromCharCode("A".charCodeAt(0) + i);
                      const selected = selectedLetter === letter;
                      return (
                        <label
                          key={i}
                          className={`qp-option ${selected ? "is-selected" : ""}`}
                          onClick={() => handleSelectMCQ(idx, i)}
                        >
                          <span className="qp-badge">{letter}</span>
                          <span className="qp-text">
                            {opt.replace(/^[A-D]\)\s*/i, "")}
                          </span>
                          <input
                            type="radio"
                            name={`q${idx}`}
                            className="qp-radio"
                            checked={selected}
                            readOnly
                          />
                        </label>
                      );
                    })}
                  </div>
                )}

                {/* V/F */}
                {q.type === "vf" && (
                  <div className="qp-options" style={{ gridTemplateColumns: "1fr 1fr" }}>
                    <label
                      className={`qp-option ${answers[idx] === true ? "is-selected" : ""}`}
                      onClick={() => handleToggleVF(idx, true)}
                    >
                      <span className="qp-text">Verdadero</span>
                      <input
                        type="radio"
                        name={`q${idx}-vf`}
                        className="qp-radio"
                        checked={answers[idx] === true}
                        readOnly
                      />
                    </label>
                    <label
                      className={`qp-option ${answers[idx] === false ? "is-selected" : ""}`}
                      onClick={() => handleToggleVF(idx, false)}
                    >
                      <span className="qp-text">Falso</span>
                      <input
                        type="radio"
                        name={`q${idx}-vf`}
                        className="qp-radio"
                        checked={answers[idx] === false}
                        readOnly
                      />
                    </label>
                  </div>
                )}

                {/* Respuesta corta */}
                {q.type === "short" && (
                  <textarea
                    rows={3}
                    className="qp-short"
                    placeholder="Escribe tu respuesta..."
                    value={answers[idx] || ""}
                    onChange={(e) => handleShortChange(idx, e.target.value)}
                  />
                )}

                {/* Acciones por pregunta */}
                <div className="qp-actions">
                  <button
                    className="btn btn-yellow"
                    onClick={() => handleDuplicateQuestion(idx)}
                    title="Duplicar esta pregunta"
                  >
                    📄 Duplicar
                  </button>

                  <button
                    className="btn btn-red"
                    onClick={() => handleDeleteQuestion(idx)}
                    title="Eliminar esta pregunta"
                  >
                    🗑️ Eliminar
                  </button>

                  {!draft ? (
                    <button
                      className="btn btn-indigo"
                      onClick={() => handleStartRegenerate(idx)}
                      title="Regenerar esta pregunta"
                    >
                      🔄 Regenerar
                    </button>
                  ) : (
                    <>
                      <span className="qp-regen-note">Nueva variante lista</span>
                      <button
                        className="btn btn-black"
                        onClick={() => handleRegenerateAgain(idx)}
                      >
                        Regenerar de nuevo
                      </button>
                      <button
                        className="btn btn-green"
                        onClick={() => handleConfirmReplace(idx)}
                      >
                        Reemplazar
                      </button>
                      <button
                        className="btn btn-red"
                        onClick={() => handleCancelRegenerate(idx)}
                      >
                        Cancelar
                      </button>
                    </>
                  )}
                </div>

                {/* Panel de borrador (vista previa de la variante) */}
                {draft && (
                  <div className="qp-regen">
                    <div className="qp-regen__title">Vista previa de variante</div>
                    <div className="qp-regen__q">{draft.question}</div>
                    {Array.isArray(draft.options) && (
                      <ul className="qp-regen__list">
                        {draft.options.map((o, i) => (
                          <li key={i}>{o}</li>
                        ))}
                      </ul>
                    )}
                    {draft.explanation && (
                      <div className="qp-regen__expl">💡 {draft.explanation}</div>
                    )}
                  </div>
                )}

                {/* Solución al enviar */}
                {submitted && (
                  <div className="qp-solution">
                    <div className="qp-expected">
                      <b>Respuesta esperada:</b>{" "}
                      {q.type === "vf" ? q.answer : q.type === "mcq" ? q.answer : q.answer}
                    </div>
                    {q.explanation && <div className="qp-expl">💡 {q.explanation}</div>}
                  </div>
                )}

                {/* Historial */}
                {Array.isArray(history[idx]) && history[idx].length > 1 && (
                  <details className="qp-history">
                    <summary>Ver historial ({history[idx].length} versiones)</summary>
                    <ol>
                      {history[idx].map((v, vi) => (
                        <li key={vi}>
                          <b>v{vi}:</b> {v.question}
                        </li>
                      ))}
                    </ol>
                  </details>
                )}
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      <div className="qp-actions">
        {!submitted ? (
          <>
            <button className="btn btn-green" onClick={submitQuiz}>
              Calificar
            </button>
            <button className="btn btn-indigo" onClick={() => navigate("/")}>
              Volver al inicio
            </button>
          </>
        ) : (
          <>
            <button className="btn btn-indigo" onClick={resetQuiz}>
              Reintentar
            </button>
            <button className="btn btn-indigo" onClick={() => navigate("/")}>
              Volver al inicio
            </button>
          </>
        )}
      </div>

      {submitted && (
        <motion.div
          className="qp-detailed-results"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          {/* Resumen general */}
          <div className="results-header">
            <h3>🎉 ¡Quiz completado!</h3>
            <div className="overall-score">
              <span className="score-big">{detailedScoring.percentage}%</span>
              <span className="score-fraction">
                {detailedScoring.correct} de {detailedScoring.total} correctas
              </span>
            </div>
          </div>

          {/* Análisis por tipo */}
          <div className="results-by-type">
            <h4>📊 Análisis por tipo de pregunta</h4>
            <div className="type-grid">
              {Object.entries(detailedScoring.byType).map(([type, data]) => {
                if (data.total === 0) return null;
                return (
                  <div key={type} className="type-card">
                    <div className="type-name">
                      {type === "mcq"
                        ? "🔄 Opción múltiple"
                        : type === "vf"
                        ? "✅ Verdadero/Falso"
                        : "📝 Respuesta corta"}
                    </div>
                    <div className="type-score">{data.percentage}%</div>
                    <div className="type-details">
                      {data.correct}/{data.total}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Reintento */}
          <div className="results-actions">
            <button className="btn btn-retry" onClick={retryQuiz}>
              🔄 Reintentar Quiz
            </button>

            <button className="btn btn-new" onClick={() => navigate("/saved-quizzes")}>
              📚 Ver mis quizzes
            </button>
          </div>

          {/* Detalle por pregunta */}
          <details className="question-breakdown">
            <summary>🔍 Ver detalle por pregunta</summary>
            <div className="breakdown-list">
              {detailedScoring.questionDetails.map((detail, idx) => (
                <div
                  key={idx}
                  className={`breakdown-item ${
                    detail.isCorrect ? "correct" : detail.hasAnswer ? "incorrect" : "unanswered"
                  }`}
                >
                  <span className="q-number">#{idx + 1}</span>
                  <span className="q-type">
                    {detail.type === "mcq" ? "🔄" : detail.type === "vf" ? "✅" : "📝"}
                  </span>
                  <span className="q-status">
                    {!detail.hasAnswer
                      ? "⚪ Sin respuesta"
                      : detail.isCorrect
                      ? "✅ Correcto"
                      : "❌ Incorrecto"}
                  </span>
                  {detail.hasAnswer && !detail.isCorrect && (
                    <div className="q-correction">
                      <small>Tu respuesta: {String(detail.userAnswer)}</small>
                      <br />
                      <small>Correcta: {String(detail.correctAnswer)}</small>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </details>
        </motion.div>
      )}
    </section>
  </main>
);

}
