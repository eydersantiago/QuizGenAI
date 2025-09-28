// src/pages/QuizPlay.jsx
import React, { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import "../estilos/QuizPlay.css"; // <-- importante

const API_BASE =
  import.meta?.env?.VITE_API_BASE || "http://localhost:8000/api";

export default function QuizPlay() {
  const { sessionId } = useParams();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [warning, setWarning] = useState(null);
  const [error, setError] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({}); // {idx: "A"|"B"|"C"|"D"|true|false|string}
  const [submitted, setSubmitted] = useState(false);

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
        setQuestions(Array.isArray(data.preview) ? data.preview : []);
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

  // Auto-scoring para MCQ y VF
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
        const given = typeof user === "boolean" ? (user ? "verdadero" : "falso") : String(user ?? "").toLowerCase();
        if (expected && given && expected === given) correct += 1;
      }
    });
    return { correct, total };
  }, [submitted, answers, questions]);

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

  if (loading) {
    return (
      <main className="shell qp-root">
        <section className="card qp-loading">
          Cargando quiz...
        </section>
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
            {questions.map((q, idx) => (
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
                      const selected = (answers[idx] ?? "").toString().toUpperCase().charAt(0) === letter;
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

                {/* Solución al enviar */}
                {submitted && (
                  <div className="qp-solution">
                    <div className="qp-expected">
                      <b>Respuesta esperada:</b>{" "}
                      {q.type === "vf" ? q.answer : q.type === "mcq" ? q.answer : q.answer}
                    </div>
                    {q.explanation && (
                      <div className="qp-expl">💡 {q.explanation}</div>
                    )}
                  </div>
                )}
              </motion.div>
            ))}
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
