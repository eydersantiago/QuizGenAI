// src/pages/QuizPlay.jsx
import React, { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import "../estilos/QuizPlay.css";

const API_BASE = import.meta?.env?.VITE_API_BASE || "http://localhost:8000/api";

export default function QuizPlay() {
  const { sessionId } = useParams();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [warning, setWarning] = useState(null);
  const [error, setError] = useState(null);

  // Preguntas "vigentes" que se muestran
  const [questions, setQuestions] = useState([]);
  // Respuestas del usuario
  const [answers, setAnswers] = useState({});
  const [submitted, setSubmitted] = useState(false);

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
        const resp = await fetch(`${API_BASE}/preview/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data?.error || "No se pudo cargar el quiz");
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
    return () => { alive = false; };
  }, [sessionId]);

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
      clone.question = (clone.question || "Pregunta").replace(/\s*— variante.*/i, "") + " — variante";
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
        body: JSON.stringify({ session_id: sessionId, index: idx, question: candidate }),
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

  const submitQuiz = () => setSubmitted(true);
  const resetQuiz = () => { setAnswers({}); setSubmitted(false); };

  // -------- Scoring automático (MCQ y VF) ----------
  const scoring = useMemo(() => {
    if (!submitted) return null;
    let total = 0, correct = 0;
    questions.forEach((q, idx) => {
      const user = answers[idx];
      if (q.type === "mcq") {
        total += 1;
        const expected = String(q.answer ?? "").trim().toUpperCase().charAt(0);
        const given = (user ?? "").toString().trim().toUpperCase().charAt(0);
        if (expected && given && expected === given) correct += 1;
      } else if (q.type === "vf") {
        total += 1;
        const expected = String(q.answer ?? "").toLowerCase();
        const given = typeof user === "boolean"
          ? (user ? "verdadero" : "falso")
          : String(user ?? "").toLowerCase();
        if (expected && given && expected === given) correct += 1;
      }
    });
    return { correct, total };
  }, [submitted, answers, questions]);

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
            <button className="btn btn-indigo" onClick={() => navigate(-1)}>Volver</button>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="shell qp-root">
      <header className="hero qp-header">
        <h1>Tu Quiz</h1>
        <p>Responde las preguntas. Cuando termines, presiona “Calificar”.</p>
        {warning && <p className="qp-warning">⚠️ {warning}</p>}
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
                        const letter = String.fromCharCode("A".charCodeAt(0) + i);
                        const selected = (answers[idx] ?? "")
                          .toString().toUpperCase().charAt(0) === letter;
                        return (
                          <label
                            key={i}
                            className={`qp-option ${selected ? "is-selected" : ""}`}
                            onClick={() => handleSelectMCQ(idx, i)}
                          >
                            <span className="qp-badge">{letter}</span>
                            <span className="qp-text">{opt.replace(/^[A-D]\)\s*/i, "")}</span>
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
                        <span className="qp-regen-note">Nueva variante lista</span>
                        <button className="btn btn-black" onClick={() => handleRegenerateAgain(idx)}>
                          Regenerar de nuevo
                        </button>
                        <button className="btn btn-green" onClick={() => handleConfirmReplace(idx)}>
                          Reemplazar
                        </button>
                        <button className="btn btn-red" onClick={() => handleCancelRegenerate(idx)}>
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
                          {draft.options.map((o, i) => <li key={i}>{o}</li>)}
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

                  {/* Historial opcional (colapsado simple) */}
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
            <button className="btn btn-green" onClick={submitQuiz}>Calificar</button>
          ) : (
            <>
              <button className="btn btn-indigo" onClick={resetQuiz}>Reintentar</button>
              <button className="btn btn-indigo" onClick={() => navigate("/")}>Volver al inicio</button>
            </>
          )}
        </div>

        {submitted && scoring && (
          <div className="qp-score">
            Resultado: {scoring.correct} / {scoring.total} <br />
            <small>(Solo MCQ y V/F cuentan para nota automática)</small>
          </div>
        )}
      </section>
    </main>
  );
}
