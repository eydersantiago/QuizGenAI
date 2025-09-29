// src/pages/QuizPlay.jsx
import React, { useEffect, useMemo, useState, useRef } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Save, BookOpen } from "lucide-react";
import jsPDF from "jspdf";
import Swal from "sweetalert2";
import "../estilos/QuizPlay.css";

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

export default function QuizPlay() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();

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

  // Referencia para timeout de auto-guardado
  const saveTimeoutRef = useRef(null);

  // Historial de versiones por índice: { [idx]: [v0(original), v1, ...] }
  const [history, setHistory] = useState({});
  // Borradores de regeneración pendientes de confirmar: { [idx]: question }
  const [regenDrafts, setRegenDrafts] = useState({});

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
        const resp = await fetch(`${API_BASE}/preview/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId }),
        });
        const data = await resp.json();
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
      const resp = await fetch(`${API_BASE}/regenerate/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          index: idx,
          type: q?.type, // mantiene tipo
        }),
      });

      const data = await resp.json();
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
      await fetch(`${API_BASE}/confirm-replace/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          index: idx,
          question: candidate,
        }),
      });
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
    return (
      <main className="shell qp-root">
        <section className="card qp-loading">Cargando quiz...</section>
      </main>
    );
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
            <p>
              Responde las preguntas. Cuando termines, presiona "Calificar".
            </p>
            {warning && <p className="qp-warning">⚠️ {warning}</p>}
            {isLoadedQuiz && (
              <p className="qp-saved-info">
                💾 Quiz guardado - Se guarda automáticamente tu progreso
              </p>
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
                {saving
                  ? "Guardando..."
                  : isLoadedQuiz
                  ? "Guardar"
                  : "Guardar Quiz"}
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

                  {/* MCQ */}
                  {q.type === "mcq" && Array.isArray(q.options) && (
                    <div className="qp-options">
                      {q.options.map((opt, i) => {
                        const letter = String.fromCharCode(
                          "A".charCodeAt(0) + i
                        );
                        const selected =
                          (answers[idx] ?? "")
                            .toString()
                            .toUpperCase()
                            .charAt(0) === letter;
                        return (
                          <label
                            key={i}
                            className={`qp-option ${
                              selected ? "is-selected" : ""
                            }`}
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
                    <div
                      className="qp-options"
                      style={{ gridTemplateColumns: "1fr 1fr" }}
                    >
                      <label
                        className={`qp-option ${
                          answers[idx] === true ? "is-selected" : ""
                        }`}
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
                        className={`qp-option ${
                          answers[idx] === false ? "is-selected" : ""
                        }`}
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
                    {/* 🔵 Botón duplicar */}
                    <button
                      className="btn btn-yellow"
                      onClick={() => handleDuplicateQuestion(idx)}
                      title="Duplicar esta pregunta"
                    >
                      📄 Duplicar
                    </button>

                    {/* 🔴 Botón eliminar */}
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
                        Regenerar
                      </button>
                    ) : (
                      <>
                        <span className="qp-regen-note">
                          Nueva variante lista
                        </span>
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
                      <div className="qp-regen__title">
                        Vista previa de variante
                      </div>
                      <div className="qp-regen__q">{draft.question}</div>
                      {Array.isArray(draft.options) && (
                        <ul className="qp-regen__list">
                          {draft.options.map((o, i) => (
                            <li key={i}>{o}</li>
                          ))}
                        </ul>
                      )}
                      {draft.explanation && (
                        <div className="qp-regen__expl">
                          💡 {draft.explanation}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Solución al enviar */}
                  {submitted && (
                    <div className="qp-solution">
                      <div className="qp-expected">
                        <b>Respuesta esperada:</b>{" "}
                        {q.type === "vf"
                          ? q.answer
                          : q.type === "mcq"
                          ? q.answer
                          : q.answer}
                      </div>
                      {q.explanation && (
                        <div className="qp-expl">💡 {q.explanation}</div>
                      )}
                    </div>
                  )}

                  {/* Historial opcional (colapsado simple) */}
                  {Array.isArray(history[idx]) && history[idx].length > 1 && (
                    <details className="qp-history">
                      <summary>
                        Ver historial ({history[idx].length} versiones)
                      </summary>
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

              <button
                className="btn btn-new"
                onClick={() => navigate("/saved-quizzes")}
              >
                📚 Ver mis quizzes
              </button>
            </div>

            {/* Detalle pregunta por pregunta (opcional, colapsable) */}
            <details className="question-breakdown">
              <summary>🔍 Ver detalle por pregunta</summary>
              <div className="breakdown-list">
                {detailedScoring.questionDetails.map((detail, idx) => (
                  <div
                    key={idx}
                    className={`breakdown-item ${
                      detail.isCorrect
                        ? "correct"
                        : detail.hasAnswer
                        ? "incorrect"
                        : "unanswered"
                    }`}
                  >
                    <span className="q-number">#{idx + 1}</span>
                    <span className="q-type">
                      {detail.type === "mcq"
                        ? "🔄"
                        : detail.type === "vf"
                        ? "✅"
                        : "📝"}
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
