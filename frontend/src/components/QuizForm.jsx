import React, { useState, useMemo, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Eye, PlusCircle, CheckCircle, BookOpen } from "lucide-react";
import Swal from "sweetalert2";
import "../estilos/QuizForm.css";
import { useModelProvider, withProviderHeaders } from "../ModelProviderContext";
import ModelProviderSelect from "../components/ModelProviderSelect";
import { useVoiceCommands } from "../hooks/useVoiceCommands";
import { getSlot, extractTypeCounts } from '../utils/voiceParsing';

const TAXONOMY = [
  "algoritmos", "estructura de datos", "complejidad computacional", "np-completitud",
  "teoría de la computación", "autómatas y gramáticas", "compiladores", "intérpretes",
  "lenguajes de programación", "sistemas de tipos", "verificación formal", "model checking",
  "programación orientada a objetos", "patrones de diseño", "programación funcional",
  "metodologías ágiles", "scrum", "kanban", "devops", "sre", "observabilidad",
  "logging", "monitoring", "tracing", "apm", "optimización de rendimiento", "profiling",
  "cachés", "cdn", "sistemas operativos", "gestión de memoria", "concurrencia",
  "paralelismo", "hilos", "procesos", "bloqueos y semáforos", "sistemas distribuidos",
  "consenso", "microservicios", "arquitectura hexagonal", "ddd", "event sourcing",
  "mensajería asíncrona", "kafka", "rabbitmq", "mqtt", "rest", "graphql", "grpc",
  "redes de computadores", "tcp/ip", "enrutamiento", "dns", "http/2", "http/3", "quic",
  "seguridad informática", "owasp", "criptografía", "pki", "ssl/tls", "iam",
  "seguridad en redes", "seguridad web", "pentesting", "forense digital",
  "bases de datos", "modelado relacional", "normalización", "transacciones",
  "aislamiento y concurrencia", "sql", "pl/sql", "postgresql", "mysql", "sqlite",
  "mariadb", "nosql", "mongodb", "redis", "elasticsearch", "data warehousing",
  "etl", "elt", "data lakes", "big data", "hadoop", "spark", "procesamiento en stream",
  "procesamiento batch", "ingeniería de datos", "mlops", "machine learning",
  "deep learning", "nlp", "computer vision", "reinforcement learning",
  "transformers", "embeddings", "llms", "prompt engineering", "evaluación de llms",
  "edge ai", "federated learning", "differential privacy", "autoML", "explicabilidad (xai)",
  "estadística", "probabilidad", "álgebra lineal", "cálculo", "matemática discreta",
  "optimización", "investigación de operaciones", "series de tiempo",
  "arquitectura de software", "requisitos de software", "uml", "pruebas unitarias",
  "pruebas de integración", "tdd", "ci/cd", "contenedores", "docker", "kubernetes",
  "serverless", "nubes públicas", "aws", "azure", "gcp", "iac (terraform)", "ansible",
  "backend", "frontend", "fullstack", "html", "css", "javascript",
  "typescript", "react", "next.js", "vue", "angular", "svelte", "node.js", "deno",
  "python", "java", "c", "c++", "c#", "go", "rust", "php", "ruby", "swift", "kotlin", "r",
  "matlab", "apis", "sockets", "iot", "sistemas embebidos", "esp32", "arduino", "robótica",
  "gráficos por computador", "opengl", "unity", "unreal", "ar/vr", "hci", "accesibilidad",
  "ux/ui", "bioinformática", "gis", "fintech", "e-commerce", "blockchain",
  "contratos inteligentes", "zk-proofs", "escalado blockchain", "privacidad", "etica en ia"
];

/** Utilidad para normalizar (tildes/case) */
const norm = (s) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase().trim();
const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:8000/api";

console.log("API_BASE:", process.env.REACT_APP_API_BASE);

/** AutocompleteSelect: select con buscador */
function AutocompleteSelect({ value, onChange, options, placeholder }) {
  const [query, setQuery] = useState(value || "");
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);
  const rootRef = useRef(null);
  const listRef = useRef(null);

  // Cerrar al hacer click fuera
  useEffect(() => {
    const onClickOutside = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  // Mantener sincronizado con value externo
  useEffect(() => {
    setQuery(value || "");
  }, [value]);

  // Filtrado con prioridad startsWith luego includes
  const results = useMemo(() => {
    const q = norm(query);
    if (!q) return options.slice(0, 12);
    const starts = [];
    const contains = [];
    for (const t of options) {
      const nt = norm(t);
      if (nt.startsWith(q)) starts.push(t);
      else if (nt.includes(q)) contains.push(t);
      if (starts.length + contains.length >= 12) break;
    }
    return [...starts, ...contains].slice(0, 12);
  }, [query, options]);

  const commit = (val) => {
    onChange?.(val);
    setQuery(val);
    setOpen(false);
  };

  const onKeyDown = (e) => {
    if (!open && (e.key === "ArrowDown" || e.key === "Enter")) {
      setOpen(true);
      return;
    }
    if (!open) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, results.length - 1));
      listRef.current?.children?.[Math.min(activeIdx + 1, results.length - 1)]?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, 0));
      listRef.current?.children?.[Math.max(activeIdx - 1, 0)]?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (results[activeIdx]) commit(results[activeIdx]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className="combo" ref={rootRef}>
      <input
        className="combo-input w-full border-2 border-indigo-300 rounded-xl p-3 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        placeholder={placeholder}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          onChange?.(e.target.value);
          setOpen(true);
          setActiveIdx(0);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        role="combobox"
        aria-expanded={open}
        aria-controls="combo-listbox"
        aria-autocomplete="list"
      />
      <AnimatePresence>
        {open && results.length > 0 && (
          <motion.ul
            id="combo-listbox"
            ref={listRef}
            className="combo-list"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 6 }}
            role="listbox"
          >
            {results.map((item, idx) => (
              <li
                key={item}
                role="option"
                aria-selected={idx === activeIdx}
                className={`combo-item ${idx === activeIdx ? "is-active" : ""}`}
                onMouseEnter={() => setActiveIdx(idx)}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => commit(item)}
              >
                {item}
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function QuizForm(props) {
  const { speak } = useVoiceCommands({ sessionId: props.sessionId });
  const { provider, headerName } = useModelProvider();
  const { question, options } = props;
  const [topic, setTopic] = useState("");
  const [difficulty, setDifficulty] = useState("Fácil");
  const [types, setTypes] = useState({ mcq: true, vf: true, short: false });
  const [counts, setCounts] = useState({ mcq: 5, vf: 3, short: 0 });
  const [preview, setPreview] = useState(null);
  const [lastSaved, setLastSaved] = useState(null);
  const [isAutoSaving, setIsAutoSaving] = useState(false);
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const MAX_TOTAL = 20;

  // Clave para localStorage
  const AUTOSAVE_KEY = "quizform_autosave";

    const leerPregunta = async () => {
    const texto = `${question?.title || "Pregunta"}. ${options?.map((o, i)=>`Opción ${i+1}: ${o}`).join(". ")}`;
    try { await speak(texto, { voice: "es-ES-AlvaroNeural" }); } catch {}
 };

  // Cargar datos guardados al montar el componente
  useEffect(() => {
    const savedData = localStorage.getItem(AUTOSAVE_KEY);
    if (savedData) {
      try {
        const parsed = JSON.parse(savedData);
        if (parsed.topic) setTopic(parsed.topic);
        if (parsed.difficulty) setDifficulty(parsed.difficulty);
        if (parsed.types) setTypes(parsed.types);
        if (parsed.counts) setCounts(parsed.counts);
        if (parsed.timestamp) {
          setLastSaved(new Date(parsed.timestamp));
        }
      } catch (error) {
        console.error("Error al cargar datos guardados:", error);
        localStorage.removeItem(AUTOSAVE_KEY);
      }
    }
  }, []);

  // Escucha intents de voz para prellenar campos del formulario (contextual)
  useEffect(() => {
    const handler = (e) => {
      const res = e.detail || {};
      const text = (res.text || '').toLowerCase();
      const intent = (res.intent || '').toLowerCase();

      // slots detectados
      const topicSlot = getSlot(res, 'topic');
      const difficultySlot = getSlot(res, 'difficulty');
      const countSlot = getSlot(res, 'count');
      // extraer pares tipo+cantidad si vienen en la misma frase
      const multiCounts = extractTypeCounts(text || '');
      if (multiCounts && Object.keys(multiCounts).length > 0) {
        setCounts((prev) => ({ ...prev, ...multiCounts }));
      }

      if (topicSlot) {
        // Intent: prefer selecting an existing taxonomy item instead of creating a new free-text option
        const tNorm = norm(String(topicSlot || ""));
        const matched = TAXONOMY.find(
          (x) => norm(x) === tNorm || norm(x).includes(tNorm) || tNorm.includes(norm(x))
        );
        if (matched) {
          setTopic(matched);
        } else {
          // Try looser heuristics: startsWith / includes
          const loose = TAXONOMY.find((x) => norm(x).startsWith(tNorm) || norm(x).includes(tNorm) || tNorm.startsWith(norm(x)));
          if (loose) setTopic(loose);
          else {
            // Don't create a new taxonomy entry from voice — ask the user to pick or say a close match
            try {
                // speak is available from hook; fire-and-forget (catch to avoid uncaught rejections)
                speak(`No encontré el tema "${topicSlot}" en la lista. Por favor di el nombre exacto de un tema disponible.`).catch(()=>{});
              } catch (_) {}
          }
        }
      }
      if (difficultySlot) {
        setDifficulty(difficultySlot);
      }
      if (countSlot) {
        // Determinar a qué tipo de pregunta se refiere el comando de voz
        const n = Number(countSlot);
        if (!Number.isNaN(n)) {
          const t = text;
          let target = null;

          // palabras clave para verdadero/falso (revisar primero)
          if (/\b(vf|v\/f|v\s+f|verdader[oa]s?|verdader[oa]|fals[oa]s?|falso|verdadero-falso|verdadero\s*y\s*falso)\b/.test(t)) {
            target = 'vf';
          }
          // palabras clave para opción múltiple
          else if (/\b(mcq|opci[oó]n(es)?\s+m(u|ú)ltiple|opcion(es)?\s+m(u|ú)ltiple|m(u|ú)ltiple|opci[oó]n)\b/.test(t)) {
            target = 'mcq';
          }
          // palabras clave para respuesta corta
          else if (/\b(corta|respuesta corta|short|texto)\b/.test(t)) {
            target = 'short';
          }
          // si no se detecta tipo explícito, usar heurística: si únicamente mencionó un número, asignar a mcq
          else {
            target = 'mcq';
          }
          

          setCounts((prev) => ({ ...prev, [target]: Math.max(0, Math.min(20, n)) }));

          try {
            // fire-and-forget but avoid unhandled promise rejection
            speak(`Asignado ${n} preguntas de ${target === 'mcq' ? 'opción múltiple' : target === 'vf' ? 'verdadero/falso' : 'respuesta corta'}`).catch(()=>{});
          } catch (_) {}
        }
      }

      // acciones: previsualizar / crear
      if (/previsualiz|previsualizar/.test(text) || intent.includes('preview')) {
        handlePreview();
        return;
      }
      if (/crear sesi[oó]n|crear session|crear sesion|crear$|crear quiz|crear cuestionario/.test(text) || intent.includes('create')) {
        handleCreate();
        return;
      }
    };

    window.addEventListener('voice:intent', handler);
    return () => window.removeEventListener('voice:intent', handler);
  }, [setTopic, setDifficulty, setCounts, handlePreview, handleCreate, speak]);

  // Función para guardar automáticamente
  const autoSave = useCallback(() => {
    setIsAutoSaving(true);
    const dataToSave = {
      topic,
      difficulty,
      types,
      counts,
      timestamp: new Date().toISOString(),
    };

    localStorage.setItem(AUTOSAVE_KEY, JSON.stringify(dataToSave));
    setLastSaved(new Date());

    // Simular un pequeño delay para mostrar el indicador
    setTimeout(() => {
      setIsAutoSaving(false);
    }, 500);
  }, [topic, difficulty, types, counts]);

  // Auto-guardar cuando cambian los datos (con debounce)
  useEffect(() => {
    // Solo auto-guardar si hay datos significativos
    if (topic.trim() || Object.values(types).some(Boolean)) {
      const timeoutId = setTimeout(() => {
        autoSave();
      }, 1000); // Esperar 1 segundo después del último cambio

      return () => clearTimeout(timeoutId);
    }
  }, [topic, difficulty, types, counts, autoSave]);

  // Función para limpiar datos guardados
  const clearSavedData = useCallback(() => {
    localStorage.removeItem(AUTOSAVE_KEY);
    setLastSaved(null);
  }, []);

  function toggleType(t) {
    setTypes((prev) => ({ ...prev, [t]: !prev[t] }));
  }

  function handleCountChange(t, v) {
    setCounts((prev) => ({ ...prev, [t]: Math.max(0, Math.min(20, Number(v))) }));
  }

  function validate() {
    const topicNorm = norm(topic);
    const matched = TAXONOMY.find(
      (x) => norm(x) === topicNorm || norm(x).includes(topicNorm) || topicNorm.includes(norm(x))
    );
    if (!matched) {
      Swal.fire("Tema no válido", "Debe ser un tema de informática/sistemas.", "warning");
      return false;
    }
    let total = 0;
    Object.keys(types).forEach((t) => {
      if (types[t]) total += counts[t];
    });
    if (total === 0) {
      Swal.fire("Sin preguntas", "Debes asignar al menos 1 pregunta.", "error");
      return false;
    }
    if (total > MAX_TOTAL) {
      Swal.fire("Excedido", `Máx ${MAX_TOTAL} preguntas.`, "error");
      return false;
    }
    return true;
  }

  async function handlePreview() {
    if (!validate()) return;
    const payload = { topic, difficulty, types: Object.keys(types).filter((k) => types[k]), counts };

    const res = await fetch(
      `${API_BASE}/preview/`,
      withProviderHeaders(
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
        provider,
        headerName
      )
    );
    const json = await res.json();

    const usedHeader = res.headers.get("x-llm-effective-provider");
    const fbHeader = res.headers.get("x-llm-fallback");

    const used = usedHeader || json.source;           // respaldo al body
    const fallback = (fbHeader ?? (json.fallback_used ? "1" : "0")) === "1";

    console.log("[LLM] requested:", provider, "used:", used, "fallback:", fallback);
    if (res.ok) setPreview(json.preview);
    else Swal.fire("Error", json.error || "No se pudo obtener preview", "error");
  }

  // CREA SESIÓN (separado de métricas)
  async function handleCreate() {
    if (!validate()) return;
    try {
      setCreating(true);
      const payload = { topic, difficulty, types: Object.keys(types).filter((k) => types[k]), counts };
      const res = await fetch(
        `${API_BASE}/sessions/`,
        withProviderHeaders(
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          },
          provider,
          headerName
        )
      );

      // intenta parsear JSON incluso en error
      let json = {};
      try {
        json = await res.json();
      } catch (_) {}

      if (!res.ok) {
        Swal.fire("Error", json?.error || "No se pudo crear la sesión", "error");
        return;
      }

      const sessionId = json.session_id;

      // Pop de éxito y luego redirigir
      await Swal.fire({
        title: "Sesión creada",
        text: `ID: ${sessionId}`,
        icon: "success",
        confirmButtonText: "Ir al quiz",
        timer: 1800,
        timerProgressBar: true,
      });

      // Limpiar datos guardados después del éxito
      clearSavedData();
      navigate(`/quiz/${sessionId}`);
    } catch (err) {
      Swal.fire("Error", String(err), "error");
    } finally {
      setCreating(false);
    }
  }

  // OBTENER MÉTRICAS (endpoint separado)
  async function handleGetMetrics() {
    if (!validate()) return;
    try {
      setCreating(true);
      // Construir query string con los parámetros necesarios
      const params = new URLSearchParams({
        topic,
        difficulty,
        types: Object.keys(types).filter((k) => types[k]).join(","),
        counts: JSON.stringify(counts),
      }).toString();

      const res = await fetch(
        `${API_BASE}/metrics/?${params}`,
        withProviderHeaders(
          {
            method: "GET",
            headers: { "Content-Type": "application/json" },
          },
          provider,
          headerName
        )
      );

      let json = {};
      try {
        json = await res.json();
      } catch (_) {}

      if (!res.ok) {
        Swal.fire("Error", json?.error || "No se pudieron obtener las métricas", "error");
        return;
      }

      await Swal.fire({
        title: "Métricas creadas",
        text: "Las métricas se han generado correctamente.",
        icon: "success",
        confirmButtonText: "OK",
        timer: 1800,
        timerProgressBar: true,
      });

      // Limpiar datos guardados después del éxito (opcional)
      // clearSavedData();

      // Redirigir a panel de métricas
      navigate(`/admin/metrics`);
    } catch (err) {
      Swal.fire("Error", String(err), "error");
    } finally {
      setCreating(false);
    }
  }

  return (
    <motion.div
      className="quiz-root"
      initial={{ opacity: 0, y: 40 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <h2 className="text-3xl font-extrabold text-indigo-700 text-center mb-6">🎯 Genera tu Quiz Inteligente</h2>

      {/* Indicador de guardado automático */}
      <div className="autosave-indicator mb-4">
        {isAutoSaving ? (
          <div className="flex items-center justify-center gap-2 text-blue-600">
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
              className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full"
            />
            <span className="text-sm">Guardando...</span>
          </div>
        ) : lastSaved ? (
          <div className="flex items-center justify-center gap-2 text-green-600">
            <CheckCircle size={16} />
            <span className="text-sm">Guardado automáticamente a las {lastSaved.toLocaleTimeString()}</span>
          </div>
        ) : null}
      </div>

      {/* Tema (Autocomplete) */}
      <label className="block font-bold text-black-700 mb-1">Tema</label>
      <AutocompleteSelect value={topic} onChange={setTopic} options={TAXONOMY} placeholder="Ej: Algoritmos de búsqueda" />

      {/* Dificultad + Selector de proveedor */}
      <div className="flex items-center justify-between mt-4 mb-1">
        <label className="block font-bold text-black-700">Dificultad</label>
        {/* <ModelProviderSelect compact /> */}
      </div>
      <select
        value={difficulty}
        onChange={(e) => setDifficulty(e.target.value)}
        className="w-full border-2 border-indigo-300 rounded-xl p-3 mb-4 focus:outline-none focus:ring-2 focus:ring-indigo-500"
      >
        <option>Fácil</option>
        <option>Media</option>
        <option>Difícil</option>
      </select>

      {/* Tipos de pregunta */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-6">
        {["mcq", "vf", "short"].map((t) => (
          <motion.label key={t} whileTap={{ scale: 0.95 }} className={`toggle ${types[t] ? "is-on" : ""}`}>
            <input type="checkbox" className="hidden" checked={types[t]} onChange={() => toggleType(t)} />
            <span className="capitalize">{t === "mcq" ? "Opción múltiple" : t === "vf" ? "V/F" : "Corta"}</span>
          </motion.label>
        ))}
      </div>

      {/* Cantidades */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        {Object.keys(counts).map((t) => (
          <div key={t} className="flex flex-col">
            {/* Etiqueta + ayuda */}
            <div className="label-row">
              <span className="text-sm font-semibold">{t.toUpperCase()}</span>

              {/* Signo de admiración con tooltip */}
              <span className="hint" role="button" tabIndex={0} aria-label={`¿Qué significa ${t.toUpperCase()}?`}>
                !
                <span className="tooltip" role="tooltip">
                  {t === "mcq" && (
                    <>
                      <b>MCQ</b>: Preguntas de opción múltiple. <br />
                      Ingresa cuántas quieres (0–20).
                    </>
                  )}
                  {t === "vf" && (
                    <>
                      <b>VF</b>: Verdadero/Falso. <br />
                      Ingresa cuántas quieres (0–20).
                    </>
                  )}
                  {t === "short" && (
                    <>
                      <b>SHORT</b>: Respuesta corta (texto breve). <br />
                      Ingresa cuántas quieres (0–20).
                    </>
                  )}
                </span>
              </span>
            </div>

            <input
              type="number"
              min="0"
              max="20"
              value={counts[t]}
              onChange={(e) => handleCountChange(t, e.target.value)}
              className="border-2 border-indigo-200 rounded-xl text-center p-3 focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        ))}
      </div>

      {/* Botones */}
      <div className="flex flex-col sm:flex-row gap-4">
        <button onClick={handlePreview} className="btn btn-indigo">
          <Eye size={20} /> Previsualizar
        </button>
        <button onClick={handleCreate} className="btn btn-green" disabled={creating} aria-busy={creating}>
          <PlusCircle size={20} />
          {creating ? "Creando..." : "Crear Sesión"}
        </button>
        <button onClick={handleGetMetrics} className="btn btn-marron" disabled={creating} aria-busy={creating}>
          <CheckCircle size={20} />
          {creating ? "Creando..." : "Obtener Métricas"}
        </button>
      </div>

      {/* Botón para limpiar formulario */}
      {lastSaved && (
        <div className="mt-4 text-center">
          <button
            onClick={() => {
              // Confirmar antes de limpiar
              Swal.fire({
                title: "¿Limpiar formulario?",
                text: "Se perderán los datos guardados automáticamente",
                icon: "question",
                showCancelButton: true,
                confirmButtonText: "Sí, limpiar",
                cancelButtonText: "Cancelar",
                confirmButtonColor: "#dc2626",
              }).then((result) => {
                if (result.isConfirmed) {
                  // Resetear estados
                  setTopic("");
                  setDifficulty("Fácil");
                  setTypes({ mcq: true, vf: true, short: false });
                  setCounts({ mcq: 5, vf: 3, short: 0 });
                  setPreview(null);
                  clearSavedData();
                  Swal.fire("Limpiado", "El formulario ha sido limpiado", "success");
                }
              });
            }}
            className="btn-text text-red-600 hover:text-red-700 text-sm"
          >
            🗑️ Limpiar formulario guardado
          </button>
        </div>
      )}

      {/* Separador visual */}
      <div className="my-8 border-t border-gray-300 opacity-30"></div>

      {/* Enlace a cuestionarios guardados */}
      <div className="mt-8 text-center">
        <p className="text-sm text-gray-600 mb-3">¿Quieres continuar un quiz anterior?</p>
        <button onClick={() => navigate("/saved-quizzes")} className="btn btn-green-outline">
          <BookOpen size={20} />
          Ver Mis Cuestionarios Guardados
        </button>
      </div>

      {/* Preview */}
      <AnimatePresence>
        {preview && (
          <motion.div className="mt-6 space-y-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          {/* Botón para leer en voz alta la configuración general del quiz */}
          <div className="mb-3">
            <button
              className="btn btn-green-outline"
              onClick={async () => {
                const tipos = Object.entries(types).filter(([,v]) => v).map(([k]) => k).join(", ");
                const total = Object.entries(counts).reduce((acc,[k,v]) => acc + (types[k] ? Number(v||0) : 0), 0);
                const texto = `Vas a crear un cuestionario sobre ${topic || "tema no definido"}, dificultad ${difficulty}. ` +
                              `Tipos activos: ${tipos || "ninguno"}. Total de preguntas: ${total}.`;
                try { await speak(texto, { voice: "es-ES-AlvaroNeural" }); } catch {}
              }}
            >
              🔊 Leer configuración del quiz
            </button>
          </div>
            <h3 className="text-2xl font-bold text-indigo-600">📋 Previsualización</h3>
            {preview.map((q, i) => (
              <motion.div key={i} className="preview-card" whileHover={{ scale: 1.02 }}>
                <div className="font-semibold_2">{q.question}</div>
                {q.options && (
                  <ul className="list-disc ml-5 text-gray-700">
                    {q.options.map((o, idx) => (
                      <li key={idx}>{o}</li>
                    ))}
                  </ul>
                )}
                <div className="text-sm text-green-600 mt-1 flex items-center gap-1">
                  <CheckCircle size={16} /> {q.answer}
                </div>
                {q.explanation && <div className="text-xs text-gray-500">💡 {q.explanation}</div>}
                {/* Botón TTS para leer esta pregunta del preview */}
              <div className="mt-2">
                <button
                  className="btn btn-indigo"
                  onClick={async () => {
                    const texto = q.options?.length
                      ? `${q.question}. ${q.options.map((o, j)=>`Opción ${j+1}: ${o}`).join(". ")}`
                      : q.question;
                    try { await speak(texto, { voice: "es-ES-AlvaroNeural" }); } catch {}
                  }}
                  title="Leer esta pregunta en voz alta"
                >
                  🔊 Leer esta pregunta
                </button>
              </div>
              </motion.div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
