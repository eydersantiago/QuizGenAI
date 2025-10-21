import React, { useEffect, useMemo, useState } from "react";
import "../estilos/AdminMetrics.css";

const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:8000/api";

function HBar({ label, value, max }) {
  const width = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="am-hbar">
      <div className="am-hbar__head">
        <span className="am-hbar__label">{label}</span>
        <span className="am-hbar__value">{value}</span>
      </div>
      <div className="am-hbar__track">
        <div className="am-hbar__fill" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

export default function AdminMetrics() {
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [data, setData] = useState(null);

  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");

  // ADDED: Voice Metrics state
  const [voiceMetrics, setVoiceMetrics] = useState(null);
  const [voiceLoading, setVoiceLoading] = useState(false);

  const fetchMetrics = async () => {
    setLoading(true);
    setErr(null);
    try {
      const params = new URLSearchParams();
      if (start) params.set("start", start);
      if (end) params.set("end", end);
      const url = `${API_BASE}/metrics/${params.toString() ? "?" + params.toString() : ""}`;
      const resp = await fetch(url);
      const json = await resp.json();
      if (!resp.ok) throw new Error(json?.error || "No se pudo cargar métricas");
      setData(json);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  };

  // ADDED: Voice Metrics fetch function
  const fetchVoiceMetrics = async () => {
    setVoiceLoading(true);
    try {
      const params = new URLSearchParams();
      if (start) params.set("start", start);
      if (end) params.set("end", end);
      const url = `${API_BASE}/voice-metrics/summary/${params.toString() ? "?" + params.toString() : ""}`;
      const resp = await fetch(url);
      const json = await resp.json();
      setVoiceMetrics(json);
    } catch (e) {
      console.error("Error loading voice metrics:", e);
    } finally {
      setVoiceLoading(false);
    }
  };

  useEffect(() => {
    fetchMetrics();
    fetchVoiceMetrics(); // ADDED: Voice Metrics
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const maxDiff = useMemo(() => {
    const d = data?.distribution?.difficulty || {};
    return Object.values(d).reduce((m, v) => Math.max(m, Number(v || 0)), 0);
  }, [data]);

  const maxType = useMemo(() => {
    const d = data?.distribution?.type || {};
    return Object.values(d).reduce((m, v) => Math.max(m, Number(v || 0)), 0);
  }, [data]);

  const exportHref = useMemo(() => {
    const params = new URLSearchParams();
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    return `${API_BASE}/metrics/export/${params.toString() ? "?" + params.toString() : ""}`;
  }, [start, end]);

  return (
    <main className="am-root">
      <header className="am-header">
        <h1 className="am-title">Métricas de uso</h1>
        <p className="am-subtitle">
          HU-11 · Total de sesiones, preguntas generadas, regeneraciones, distribución por dificultad y tipo.
        </p>
      </header>

      <section className="am-filters card-glass">
        <div className="am-filters__grid">
          <div className="am-field">
            <label className="am-label">Inicio</label>
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="am-input"
            />
          </div>
          <div className="am-field">
            <label className="am-label">Fin</label>
            <input
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="am-input"
            />
          </div>
          <div className="am-actions">
            <button className="btn-primary" onClick={() => { fetchMetrics(); fetchVoiceMetrics(); }}>
              Aplicar filtros
            </button>
            <a className="btn-ghost" href={exportHref}>
              Exportar CSV
            </a>
          </div>
        </div>
      </section>

      {loading && (
        <div className="am-skeleton">
          <div className="sk-line" />
          <div className="sk-cards">
            <div className="sk-card" />
            <div className="sk-card" />
            <div className="sk-card" />
            <div className="sk-card" />
          </div>
          <div className="sk-block" />
          <div className="sk-block" />
        </div>
      )}

      {err && (
        <div className="am-error card-glass">
          <span>⚠️ Error: {err}</span>
        </div>
      )}

      {data && !loading && !err && (
        <>
          <section className="am-kpis">
            <div className="kpi card-glass kpi-1">
              <div className="kpi__label">Sesiones</div>
              <div className="kpi__value">{data.total_sessions ?? 0}</div>
            </div>
            <div className="kpi card-glass kpi-2">
              <div className="kpi__label">Preguntas generadas</div>
              <div className="kpi__value">{data.total_questions_generated ?? 0}</div>
            </div>
            <div className="kpi card-glass kpi-3">
              <div className="kpi__label">Regeneraciones</div>
              <div className="kpi__value">{data.total_regenerations ?? 0}</div>
            </div>
            <div className="kpi card-glass kpi-4">
              <div className="kpi__label">Tasa de regeneración</div>
              <div className="kpi__value">
                {((data.regeneration_rate ?? 0) * 100).toFixed(1)}%
              </div>
            </div>
          </section>

          <section className="am-block card-glass">
            <h3 className="am-block__title">Distribución por dificultad</h3>
            {Object.entries(data?.distribution?.difficulty || {}).length === 0 ? (
              <div className="am-empty">Sin datos de dificultad.</div>
            ) : (
              Object.entries(data?.distribution?.difficulty || {}).map(([k, v]) => (
                <HBar key={k} label={k} value={Number(v || 0)} max={maxDiff} />
              ))
            )}
          </section>

          <section className="am-block card-glass">
            <h3 className="am-block__title">Distribución por tipo</h3>
            {Object.entries(data?.distribution?.type || {}).length === 0 ? (
              <div className="am-empty">Sin datos de tipo.</div>
            ) : (
              Object.entries(data?.distribution?.type || {}).map(([k, v]) => (
                <HBar key={k} label={k.toUpperCase()} value={Number(v || 0)} max={maxType} />
              ))
            )}
          </section>
        </>
      )}

      {/* ADDED: Voice Metrics Section */}
      <header className="am-header" style={{ marginTop: '3rem' }}>
        <h1 className="am-title">Métricas de Voz</h1>
        <p className="am-subtitle">
          QGAI-108 · Métricas de STT/TTS, intenciones, fallbacks y sugerencias proactivas.
        </p>
      </header>

      {voiceLoading && (
        <div className="am-skeleton">
          <div className="sk-line" />
          <div className="sk-cards">
            <div className="sk-card" />
            <div className="sk-card" />
            <div className="sk-card" />
            <div className="sk-card" />
          </div>
        </div>
      )}

      {voiceMetrics && !voiceLoading && (
        <>
          {/* Latency KPIs */}
          <section className="am-kpis">
            <div className="kpi card-glass kpi-1">
              <div className="kpi__label">STT Latencia p50</div>
              <div className="kpi__value">{Math.round(voiceMetrics.stt_latency_p50_ms ?? 0)} ms</div>
            </div>
            <div className="kpi card-glass kpi-2">
              <div className="kpi__label">STT Latencia p95</div>
              <div className="kpi__value">{Math.round(voiceMetrics.stt_latency_p95_ms ?? 0)} ms</div>
            </div>
            <div className="kpi card-glass kpi-3">
              <div className="kpi__label">TTS Latencia p50</div>
              <div className="kpi__value">{Math.round(voiceMetrics.tts_latency_p50_ms ?? 0)} ms</div>
            </div>
            <div className="kpi card-glass kpi-4">
              <div className="kpi__label">TTS Latencia p95</div>
              <div className="kpi__value">{Math.round(voiceMetrics.tts_latency_p95_ms ?? 0)} ms</div>
            </div>
          </section>

          {/* Intent & Interaction KPIs */}
          <section className="am-kpis">
            <div className="kpi card-glass kpi-1">
              <div className="kpi__label">Intenciones Reconocidas</div>
              <div className="kpi__value">{voiceMetrics.total_intents ?? 0}</div>
            </div>
            <div className="kpi card-glass kpi-2">
              <div className="kpi__label">Confianza Promedio</div>
              <div className="kpi__value">
                {((voiceMetrics.intent_avg_confidence ?? 0) * 100).toFixed(1)}%
              </div>
            </div>
            <div className="kpi card-glass kpi-3">
              <div className="kpi__label">Accuracy de Intenciones</div>
              <div className="kpi__value">
                {((voiceMetrics.intent_accuracy_rate ?? 0) * 100).toFixed(1)}%
              </div>
            </div>
            <div className="kpi card-glass kpi-4">
              <div className="kpi__label">Barge-ins</div>
              <div className="kpi__value">{voiceMetrics.barge_in_count ?? 0}</div>
            </div>
          </section>

          {/* Fallback & Suggestions KPIs */}
          <section className="am-kpis">
            <div className="kpi card-glass kpi-1">
              <div className="kpi__label">Fallbacks</div>
              <div className="kpi__value">{voiceMetrics.fallback_count ?? 0}</div>
            </div>
            <div className="kpi card-glass kpi-2">
              <div className="kpi__label">Tasa de Fallback</div>
              <div className="kpi__value">
                {((voiceMetrics.fallback_rate ?? 0) * 100).toFixed(1)}%
              </div>
            </div>
            <div className="kpi card-glass kpi-3">
              <div className="kpi__label">Sugerencias Aceptadas</div>
              <div className="kpi__value">
                {voiceMetrics.suggestions_accepted ?? 0} / {voiceMetrics.suggestions_shown ?? 0}
              </div>
            </div>
            <div className="kpi card-glass kpi-4">
              <div className="kpi__label">Tasa de Aceptación</div>
              <div className="kpi__value">
                {((voiceMetrics.suggestion_accept_rate ?? 0) * 100).toFixed(1)}%
              </div>
            </div>
          </section>

          {/* Backend Distribution Table */}
          <section className="am-block card-glass">
            <h3 className="am-block__title">Distribución por Backend</h3>
            {Object.entries(voiceMetrics?.backend_distribution || {}).length === 0 ? (
              <div className="am-empty">Sin datos de uso de backends.</div>
            ) : (
              <table className="am-table">
                <thead>
                  <tr>
                    <th>Backend</th>
                    <th>Usos</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(voiceMetrics?.backend_distribution || {}).map(([backend, count]) => (
                    <tr key={backend}>
                      <td style={{ textTransform: 'capitalize' }}>{backend}</td>
                      <td>{count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}

      {voiceMetrics && !voiceLoading && Object.keys(voiceMetrics).length === 0 && (
        <div className="am-empty card-glass">
          No hay datos de métricas de voz disponibles.
        </div>
      )}
    </main>
  );
}
