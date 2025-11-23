import { Routes, Route, useLocation, Link, useNavigate } from "react-router-dom";
import "./App.css";
import React, { useEffect } from "react";
import { useVoiceCommands } from "./hooks/useVoiceCommands";
import { getSlot } from './utils/voiceParsing';
import QuizForm from "./components/QuizForm";
import QuizPlay from "./pages/QuizPlay";
import AdminMetrics from "./pages/AdminMetrics";
import SavedQuizzes from "./components/SavedQuizzes";
import MicTest from "./pages/MicTest";
import { v4 as uuidv4 } from "uuid";
import { setVoiceMetricsSession } from "./services/voiceMetricsService";

// Proveedor/selector de modelo
import { ModelProviderProvider } from "./ModelProviderContext";
import ModelProviderSelect from "./components/ModelProviderSelect";
// Privacidad de audio
import AudioPrivacySettings from "./components/AudioPrivacy/AudioPrivacySettings";
// Panel de voz
import VoiceCommandPanel from "./components/VoiceCommands/VoiceCommandPanel";
import VoiceChatWidget from "./components/VoiceCommands/VoiceChatWidget";

function App() {
  const location = useLocation();
  const [sessionId] = React.useState(()=> uuidv4());
  React.useEffect(()=> { setVoiceMetricsSession(sessionId); }, [sessionId]);
  // voiceOpen removed: widget manages its own open state
  const navigate = useNavigate();
  const { speak } = useVoiceCommands({ sessionId });

  // Escucha intents globales para acciones globales (navegación, crear quiz desde slots)
  useEffect(() => {
    const handler = async (e) => {
      const res = e.detail || {};
      const intent = (res.intent || '').toLowerCase();
      const text = (res.text || '').toLowerCase();

      // Helper: obtener slot si existe o parsear del texto
      // use shared getSlot util which handles both result.slots and text heuristics
      const getSlotLocal = (name) => getSlot(res, name);

      // Generar quiz: guarda en localStorage para prellenar QuizForm y navega a /
      // Usamos límites de palabra para evitar falsos positivos como 'regenerar'
      if (intent.includes('generate') || /\b(generar|genera|crea|crear|arma|haz)\b/.test(text)) {
        const topic = getSlotLocal('topic') || '';
        const difficulty = getSlotLocal('difficulty') || 'Fácil';
        const count = getSlotLocal('count') || 5;

        const autosave = {
          topic,
          difficulty,
          types: { mcq: true, vf: false, short: false },
          counts: { mcq: Number(count) || 5, vf: 0, short: 0 },
          timestamp: new Date().toISOString(),
        };
        try { localStorage.setItem('quizform_autosave', JSON.stringify(autosave)); } catch (e) {}
        try { await speak(`Creando borrador de quiz sobre ${topic || 'el tema indicado'} dificultad ${difficulty}`); } catch (e) {}
        navigate('/');
        return;
      }

      // Abrir lista de quizzes guardados
      if (intent.includes('saved') || /mis quizzes|mis cuestionarios|guardad/.test(text)) {
        navigate('/saved-quizzes');
        return;
      }

      // Ir a métricas/admin
      if (/métric|metricas|admin|estadís|estadisticas/.test(text)) {
        navigate('/admin/metrics');
        return;
      }
    };

    window.addEventListener('voice:intent', handler);
    return () => window.removeEventListener('voice:intent', handler);
  }, [navigate, speak, sessionId]);
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
                <Route path="/" element={<QuizForm sessionId={sessionId} />} />
                <Route path="/mic-test" element={<MicTest />} />
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
              <Route path="/mic-test" element={<MicTest />} />
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

          {/* Widget reducido de chat de voz (abre pequeña ventana de escucha) */}
          <VoiceChatWidget sessionId={sessionId} onCommand={() => {}} />
        </main>
      </div>
    </ModelProviderProvider>
  );
}

export default App;
