import React, { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";

/**
 * Si usas Vite, define VITE_API_BASE en .env (ej: http://localhost:8000/api)
 * Si usas CRA, cambia la línea a process.env.REACT_APP_API_BASE
 */
const API_BASE =
  import.meta?.env?.VITE_API_BASE || "http://localhost:8000/api";

export default function QuizPlay() {
  const { sessionId } = useParams();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [warning, setWarning] = useState(null);
  const [error, setError] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [meta, setMeta] = useState({ topic: "", difficulty: "" });

  // estado de respuestas del usuario
  const [answers, setAnswers] = useState({}); // {idx: "A"|"B"|...|true|false|string}
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        // 1) Trae el preview de preguntas usando session_id
        const resp = await fetch(`${API_BASE}/preview/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data?.error || "No se pudo cargar el quiz");
        if (!alive) return;
        setQuestions(data.preview || []);
        if (data.warning) setWarning(data.warning);

        // 2) Trae (opcional) metadatos de la sesión (si no tienes endpoint, salta esto)
        // Como no tenemos GET de sesión, inferimos del contenido del enunciado si viene.
        // Alternativa: agrega endpoint GET /api/sessions/<id> y rellena meta.
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

  // cálculo de puntaje (auto-corrección básica: MCQ y VF)
  const scoring = useMemo(() => {
    if (!submitted) return null;
    let total = 0;
    let correct = 0;
    questions.forEach((q, idx) => {
      const user = answers[idx];
      total += 1;

      if (q.type === "mcq") {
        // answer esperado: "A" | "B" | "C" | "D" o "A) ...", normalizamos
        const expected = String(q.answer).trim().toUpperCase().charAt(0);
        const given = (user ?? "").toString().trim().toUpperCase().charAt(0);
        if (expected && given && expected === given) correct += 1;
      } else if (q.type === "vf") {
        // "Verdadero" / "Falso"
        const expected = (String(q.answer || "")).toLowerCase();
        const given = typeof user === "boolean" ? (user ? "verdadero" : "falso") : String(user || "").toLowerCase();
        if (expected && given && expected === given) correct += 1;
      } else {
        // short: no auto-corrige (podrías hacer comparación difusa)
        total -= 1; // no cuenta para el puntaje automático
      }
    });
    return { correct, total };
  }, [submitted, answers, questions]);

  const handleSelectMCQ = (idx, optIdx) => {
    // map A,B,C,D
    const letter = String.fromCharCode("A".charCodeAt(0) + optIdx);
    setAnswers((p) => ({ ...p, [idx]: letter }));
  };

  const handleToggleVF = (idx, val) => {
    setAnswers((p) => ({ ...p, [idx]: val }));
  };

  const handleShortChange = (idx, val) => {
    setAnswers((p) => ({ ...p, [idx]: val }));
  };

  const submitQuiz = () => {
    setSubmitted(true);
    // aquí podrías POSTear answers al backend si quieres guardarlas
  };

  const resetQuiz = () => {
    setAnswers({});
    setSubmitted(false);
  };

  if (loading) {
    return (
      <main className="shell">
        <section className="card" style={{ textAlign: "center" }}>
          <p>Cargando quiz...</p>
        </section>
      </main>
    );
  }
  if (error) {
    return (
      <main className="shell">
        <section className="card" style={{ color: "#b91c1c" }}>
          <h2>Error</h2>
          <p>{error}</p>
          <button className="btn btn-indigo" onClick={() => navigate(-1)} style={{ marginTop: 12 }}>
            Volver
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="shell">
      <header className="hero">
        <h1>Tu Quiz</h1>
        <p>Responde las preguntas. Cuando termines, presiona “Calificar”.</p>
        {warning && <p style={{ opacity: 0.8 }}>⚠️ {warning}</p>}
      </header>

      <section className="card">
        <div className="space-y-4">
          <AnimatePresence>
            {questions.map((q, idx) => (
              <motion.div
                key={idx}
                className="preview-card"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
              >
                <div className="font-semibold mb-2">
                  {idx + 1}. {q.question}
                </div>

                {/* MCQ */}
                {q.type === "mcq" && Array.isArray(q.options) && (
                  <div className="flex flex-col gap-2">
                    {q.options.map((opt, i) => {
                      const letter = String.fromCharCode("A".charCodeAt(0) + i);
                      const selected = (answers[idx] ?? "").toString().toUpperCase().charAt(0) === letter;
                      return (
                        <label
                          key={i}
                          className={`toggle ${selected ? "is-on" : ""}`}
                          onClick={() => handleSelectMCQ(idx, i)}
                          style={{ cursor: "pointer" }}
                        >
                          <input type="radio" name={`q${idx}`} className="hidden" />
                          <span><b>{letter})</b> {opt.replace(/^[A-D]\)\s*/i, "")}</span>
                        </label>
                      );
                    })}
                  </div>
                )}

                {/* V/F */}
                {q.type === "vf" && (
                  <div className="flex gap-2">
                    <label
                      className={`toggle ${answers[idx] === true ? "is-on" : ""}`}
                      onClick={() => handleToggleVF(idx, true)}
                    >
                      <input type="radio" name={`q${idx}-vf`} className="hidden" />
                      <span>Verdadero</span>
                    </label>
                    <label
                      className={`toggle ${answers[idx] === false ? "is-on" : ""}`}
                      onClick={() => handleToggleVF(idx, false)}
                    >
                      <input type="radio" name={`q${idx}-vf`} className="hidden" />
                      <span>Falso</span>
                    </label>
                  </div>
                )}

                {/* Respuesta corta */}
                {q.type === "short" && (
                  <textarea
                    rows={3}
                    className="w-full border-2 border-indigo-200 rounded-xl p-3 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    placeholder="Escribe tu respuesta..."
                    value={answers[idx] || ""}
                    onChange={(e) => handleShortChange(idx, e.target.value)}
                  />
                )}

                {/* Mostrar solución al enviar */}
                {submitted && (
                  <div className="text-sm mt-2">
                    <div className="text-green-600">
                      <b>Respuesta esperada:</b>{" "}
                      {q.type === "vf"
                        ? q.answer
                        : q.type === "mcq"
                        ? q.answer
                        : q.answer}
                    </div>
                    {q.explanation && (
                      <div className="text-xs text-gray-500">💡 {q.explanation}</div>
                    )}
                  </div>
                )}
              </motion.div>
            ))}
          </AnimatePresence>
        </div>

        <div className="flex flex-col sm:flex-row gap-4" style={{ marginTop: 18 }}>
          {!submitted ? (
            <button className="btn btn-green" onClick={submitQuiz}>Calificar</button>
          ) : (
            <>
              <button className="btn btn-indigo" onClick={resetQuiz}>Reintentar</button>
              <button className="btn btn-indigo" onClick={() => navigate("/")}>Volver al inicio</button>
            </>
          )}
        </div>

        {submitted && scoring && (
          <div className="text-center" style={{ marginTop: 12 }}>
            <b>Resultado:</b> {scoring.correct} / {scoring.total} (solo MCQ y V/F cuentan para nota automática)
          </div>
        )}
      </section>
    </main>
  );
}
