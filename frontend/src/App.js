import { Routes, Route, useLocation } from "react-router-dom";
import "./App.css";
import QuizForm from "./components/QuizForm";
import QuizPlay from "./pages/QuizPlay";
import AdminMetrics from "./pages/AdminMetrics";
import SavedQuizzes from "./components/SavedQuizzes";

function App() {
  const location = useLocation();
  const isPlay = location.pathname.startsWith("/quiz/");
  const isMetrics = location.pathname.startsWith("/admin/");
  const isSavedQuizzes = location.pathname === "/saved-quizzes";
  const hideHomeChrome = isPlay || isMetrics || isSavedQuizzes; // ← unificamos

  return (
    <div className="App">
      {/* Fondo dinámico */}
      <div className="bg-layer gradient" />
      <div className="bg-layer blobs" />
      <div className="bg-noise" />

      <main className="shell">
        {/* Header principal SOLO en la home (QuizForm) */}
        {!hideHomeChrome && (
          <header className="hero">
            <h1>QuizGenAI</h1>
            <p>Genera cuestionarios dinámicos a partir de un tema y dificultad.</p>
          </header>
        )}

        {/* En la home, el contenido va dentro de .card.
            En /quiz/* y /admin/*, SIN .card para evitar tarjeta doble */}
        {!hideHomeChrome ? (
          <section className="card">
            <Routes>
              <Route path="/" element={<QuizForm />} />
            </Routes>
          </section>
        ) : (
          <Routes>
            <Route path="/quiz/:sessionId" element={<QuizPlay />} />
            <Route path="/saved-quizzes" element={<SavedQuizzes />} />
            <Route path="/admin/metrics" element={<AdminMetrics />} />
          </Routes>
        )}

        <footer className="footer">
          <span>Proyecto Integrador II — MVP1</span>
        </footer>
      </main>
    </div>
  );
}

export default App;
