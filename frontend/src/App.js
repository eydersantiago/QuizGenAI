import { Routes, Route } from "react-router-dom";
import "./App.css";
import QuizForm from "./components/QuizForm";
import QuizPlay from "./pages/QuizPlay";

function App() {
  return (
    <div className="App">
      {/* Fondo dinámico */}
      <div className="bg-layer gradient" />
      <div className="bg-layer blobs" />
      <div className="bg-noise" />

      <main className="shell">
        <header className="hero">
          <h1>QuizGenAI</h1>
          <p>Genera cuestionarios dinámicos a partir de un tema y dificultad.</p>
        </header>

        <section className="card">
          {/* NO pongas BrowserRouter aquí */}
          <Routes>
            <Route path="/" element={<QuizForm />} />
            <Route path="/quiz/:sessionId" element={<QuizPlay />} />
          </Routes>
        </section>

        <footer className="footer">
          <span>Proyecto Integrador II — MVP1</span>
        </footer>
      </main>
    </div>
  );
}

export default App;
