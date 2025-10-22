import { Routes, Route, useLocation, Link } from "react-router-dom";
import "./App.css";
import React, { useEffect, useState } from "react";
import QuizForm from "./components/QuizForm";
import QuizPlay from "./pages/QuizPlay";
import AdminMetrics from "./pages/AdminMetrics";
import SavedQuizzes from "./components/SavedQuizzes";
import { v4 as uuidv4 } from "uuid";
import { setVoiceMetricsSession } from "./services/voiceMetricsService";

// Proveedor/selector de modelo
import { ModelProviderProvider } from "./ModelProviderContext";
import ModelProviderSelect from "./components/ModelProviderSelect";
// Privacidad de audio
import AudioPrivacySettings from "./components/AudioPrivacy/AudioPrivacySettings";
// Panel de voz
import VoiceCommandPanel from "./components/VoiceCommands/VoiceCommandPanel";

function App() {
  const location = useLocation();
  const [sessionId] = React.useState(()=> uuidv4());
  React.useEffect(()=> { setVoiceMetricsSession(sessionId); }, [sessionId]);
  const isPlay = location.pathname.startsWith("/quiz/");
  const isMetrics = location.pathname.startsWith("/admin/");
  const isSavedQuizzes = location.pathname === "/saved-quizzes";
  const hideHomeChrome = isPlay || isMetrics || isSavedQuizzes;

  return (
    <ModelProviderProvider>
      <div className="App">
        <div className="bg-layer gradient" />
        <div className="bg-layer blobs" />
        <div className="bg-noise" />

        <main className="shell">
          {/* Header solo en Home, centrado */}
          {!hideHomeChrome && (
            <header className="hero">
              <div style={{ textAlign: "center", maxWidth: 800, margin: "0 auto" }}>
                <h1 style={{ margin: 0 }}>QuizGenAI</h1>
                <p style={{ marginTop: 8 }}>
                  Genera cuestionarios dinámicos a partir de un tema y dificultad.
                </p>
              </div>
            </header>
          )}

          {/* Toolbar SOLO EN HOME (versión MÓVIL/pequeñas) -> fuera de la tarjeta */}
          {!hideHomeChrome && (
            <div
              className="app-toolbar app-toolbar--home-outside"
              aria-hidden={false}
            >
              <Link
                to="/voice"
                className="btn-voice-link"
                title="Abrir panel de comandos de voz"
              >
                🎤 Panel de voz
              </Link>
              <ModelProviderSelect compact />
            </div>
          )}

          {/* Contenido */}
          {!hideHomeChrome ? (
            <section className="card has-toolbar">
              {/* Toolbar SOLO EN ESCRITORIO -> dentro de la tarjeta (esquinas superiores) */}
              <div
                className="app-toolbar app-toolbar--card-inside"
                aria-hidden={false}
              >
                <Link
                  to="/voice"
                  className="btn-voice-link"
                  title="Abrir panel de comandos de voz"
                >
                  🎤 Panel de voz
                </Link>
                <ModelProviderSelect compact />
              </div>

              <Routes>
                <Route path="/" element={<QuizForm />} />
                <Route path="/settings/audio-privacy" element={<AudioPrivacySettings />} />
                <Route
                  path="/voice"
                  element={
                    <section className="card" style={{ padding: 16 }}>
                      <h2 style={{ marginTop: 0 }}>Comandos de Voz</h2>
                      <VoiceCommandPanel sessionId={sessionId} />
                    </section>
                  }
                />
              </Routes>
            </section>
          ) : (
            <Routes>
              <Route path="/quiz/:sessionId" element={<QuizPlay />} />
              <Route path="/saved-quizzes" element={<SavedQuizzes />} />
              <Route path="/admin/metrics" element={<AdminMetrics />} />
              <Route path="/settings/audio-privacy" element={<AudioPrivacySettings />} />
              <Route
                path="/voice"
                element={
                  <section className="card" style={{ padding: 16 }}>
                    <h2 style={{ marginTop: 0 }}>Comandos de Voz</h2>
                    <VoiceCommandPanel sessionId={sessionId} />
                  </section>
                }
              />
            </Routes>
          )}

          <footer className="footer">
            <span>Proyecto Integrador II — MVP1</span>
            <a href="/settings/audio-privacy" className="ml-4">Privacidad de audio</a>
          </footer>
        </main>
      </div>
    </ModelProviderProvider>
  );
}

export default App;
