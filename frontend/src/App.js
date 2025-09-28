import { Routes, Route, useLocation } from "react-router-dom";
import "./App.css";
import QuizForm from "./components/QuizForm";
import QuizPlay from "./pages/QuizPlay";

function App() {
  const location = useLocation();
  const isPlay = location.pathname.startsWith("/quiz/");

  return (
    <div className="App">
      {/* Fondo dinámico */}
      <div className="bg-layer gradient" />
      <div className="bg-layer blobs" />
      <div className="bg-noise" />

      <main className="shell">
        {/* Header principal SOLO en la home (QuizForm) */}
        {!isPlay && (
          <header className="hero">
            <h1>QuizGenAI</h1>
            <p>Genera cuestionarios dinámicos a partir de un tema y dificultad.</p>
          </header>
        )}

        {/* En la home, mostramos el contenido dentro de .card.
            En /quiz/*, NO envolvemos en .card para evitar tarjeta doble */}
        {!isPlay ? (
          <section className="card">
            <Routes>
              <Route path="/" element={<QuizForm />} />
            </Routes>
          </section>
        ) : (
          <Routes>
            <Route path="/quiz/:sessionId" element={<QuizPlay />} />
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
