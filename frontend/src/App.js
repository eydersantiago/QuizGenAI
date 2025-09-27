import "./App.css";
import QuizForm from "./components/QuizForm";

function App() {
  return (
    <div className="App">
      {/* Capas del fondo animado */}
      <div className="bg-layer gradient" />
      <div className="bg-layer blobs" />
      <div className="bg-noise" />

      {/* Contenido con efecto glass */}
      <main className="shell">
        <header className="hero">
          <h1>QuizGenAI</h1>
          <p>Genera cuestionarios dinámicos a partir de un tema y dificultad.</p>
        </header>

        <section className="card">
          <QuizForm />
        </section>

        <footer className="footer">
          <span>Proyecto Integrador II — MVP1</span>
        </footer>
      </main>
    </div>
  );
}

export default App;
