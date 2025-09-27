import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Eye, PlusCircle, CheckCircle, XCircle } from "lucide-react";
import Swal from "sweetalert2";

const TAXONOMY = [
  "algoritmos", "redes", "bd", "bases de datos",
  "sistemas operativos", "poo", "ciberseguridad",
  "ia básica", "arquitectura"
];

export default function QuizForm() {
  const [topic, setTopic] = useState("");
  const [difficulty, setDifficulty] = useState("Fácil");
  const [types, setTypes] = useState({ mcq: true, vf: true, short: false });
  const [counts, setCounts] = useState({ mcq: 5, vf: 3, short: 0 });
  const [preview, setPreview] = useState(null);
  const MAX_TOTAL = 20;

  function toggleType(t) {
    setTypes(prev => ({ ...prev, [t]: !prev[t] }));
  }

  function handleCountChange(t, v) {
    setCounts(prev => ({ ...prev, [t]: Math.max(0, Math.min(20, Number(v))) }));
  }

  function validate() {
    const topicNorm = topic.trim().toLowerCase();
    const matched = TAXONOMY.find(x => topicNorm.includes(x) || x.includes(topicNorm));
    if (!matched) {
      Swal.fire("Tema no válido", "Debe ser un tema de informática/sistemas.", "warning");
      return false;
    }
    let total = 0;
    Object.keys(types).forEach(t => { if (types[t]) total += counts[t]; });
    if (total === 0) { Swal.fire("Sin preguntas", "Debes asignar al menos 1 pregunta.", "error"); return false; }
    if (total > MAX_TOTAL) { Swal.fire("Excedido", `Máx ${MAX_TOTAL} preguntas.`, "error"); return false; }
    return true;
  }

  async function handlePreview() {
    if (!validate()) return;
    const payload = { topic, difficulty, types: Object.keys(types).filter(k => types[k]), counts };
    const res = await fetch("/api/preview/", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const json = await res.json();
    if (res.ok) setPreview(json.preview);
    else Swal.fire("Error", json.error || "No se pudo obtener preview", "error");
  }

  async function handleCreate() {
    if (!validate()) return;
    const payload = { topic, difficulty, types: Object.keys(types).filter(k => types[k]), counts };
    const res = await fetch("/api/sessions/", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const json = await res.json();
    if (res.ok) Swal.fire("Sesión creada", `ID: ${json.session_id}`, "success");
    else Swal.fire("Error", json.error, "error");
  }

  return (
    <motion.div
      className="w-full max-w-2xl bg-white rounded-3xl shadow-2xl p-8 backdrop-blur-md"
      initial={{ opacity: 0, y: 40 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <h2 className="text-3xl font-extrabold text-indigo-700 text-center mb-6">
        🎯 Genera tu Quiz Inteligente
      </h2>

      {/* Tema */}
      <label className="block font-bold text-gray-700 mb-1">Tema</label>
      <input
        className="w-full border-2 border-indigo-300 rounded-xl p-3 mb-4 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        value={topic} onChange={e => setTopic(e.target.value)}
        placeholder="Ej: Algoritmos de búsqueda"
      />

      {/* Dificultad */}
      <label className="block font-bold text-gray-700 mb-1">Dificultad</label>
      <select
        value={difficulty} onChange={e => setDifficulty(e.target.value)}
        className="w-full border-2 border-indigo-300 rounded-xl p-3 mb-4 focus:outline-none focus:ring-2 focus:ring-indigo-500"
      >
        <option>Fácil</option><option>Media</option><option>Difícil</option>
      </select>

      {/* Tipos de pregunta */}
      <div className="grid grid-cols-3 gap-2 mb-6">
        {["mcq","vf","short"].map(t => (
          <motion.label key={t}
            whileTap={{ scale: 0.95 }}
            className={`cursor-pointer flex items-center gap-2 px-3 py-2 rounded-xl border-2 ${
              types[t] ? "bg-indigo-100 border-indigo-400" : "border-gray-300"
            }`}
          >
            <input type="checkbox" className="hidden" checked={types[t]} onChange={() => toggleType(t)} />
            <span className="capitalize">{t === "mcq" ? "Opción múltiple" : t === "vf" ? "V/F" : "Corta"}</span>
          </motion.label>
        ))}
      </div>

      {/* Cantidades */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        {Object.keys(counts).map(t => (
          <div key={t} className="flex flex-col">
            <span className="text-sm font-semibold mb-1">{t.toUpperCase()}</span>
            <input type="number" min="0" max="20"
              value={counts[t]} onChange={e => handleCountChange(t, e.target.value)}
              className="border-2 border-indigo-200 rounded-xl text-center p-1 focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        ))}
      </div>

      {/* Botones */}
      <div className="flex gap-4">
        <button onClick={handlePreview}
          className="flex-1 flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white py-3 rounded-2xl shadow-lg transition">
          <Eye size={20}/> Previsualizar
        </button>
        <button onClick={handleCreate}
          className="flex-1 flex items-center justify-center gap-2 bg-green-600 hover:bg-green-700 text-white py-3 rounded-2xl shadow-lg transition">
          <PlusCircle size={20}/> Crear Sesión
        </button>
      </div>

      {/* Preview */}
      <AnimatePresence>
        {preview && (
          <motion.div
            className="mt-6 space-y-4"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          >
            <h3 className="text-2xl font-bold text-indigo-600">📋 Previsualización</h3>
            {preview.map((q, i) => (
              <motion.div
                key={i}
                className="bg-indigo-50 p-4 rounded-2xl shadow hover:shadow-xl transition"
                whileHover={{ scale: 1.02 }}
              >
                <div className="font-semibold">{q.question}</div>
                {q.options && (
                  <ul className="list-disc ml-5 text-gray-700">
                    {q.options.map((o, idx) => <li key={idx}>{o}</li>)}
                  </ul>
                )}
                <div className="text-sm text-green-600 mt-1 flex items-center gap-1">
                  <CheckCircle size={16}/> {q.answer}
                </div>
                {q.explanation && <div className="text-xs text-gray-500">💡 {q.explanation}</div>}
              </motion.div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
