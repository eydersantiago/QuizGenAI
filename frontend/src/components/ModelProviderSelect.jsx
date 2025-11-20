// src/components/ModelProviderSelect.jsx
import React, { useEffect, useMemo, useState } from "react";
import { useModelProvider, PROVIDER_LABELS } from "../ModelProviderContext";
import { fetchProvidersHealth, mapHealthByName } from "../services/healthService";
import "../estilos/ModelProviderSelect.css";

export default function ModelProviderSelect({ compact = false }) {
  const { provider, setProvider } = useModelProvider();
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const data = await fetchProvidersHealth();
        if (!alive) return;
        setHealth(data);
      } catch (err) {
        if (!alive) return;
        setError(err.message);
      }
    })();
    return () => { alive = false; };
  }, []);

  const byName = useMemo(() => mapHealthByName(health || {}), [health]);

  const renderStatus = (name) => {
    const status = byName[name]?.status || "unknown";
    const missing = byName[name]?.missing_env || [];
    const notes = byName[name]?.notes;
    const labelMap = {
      ok: "OK",
      degraded: "Degradado",
      skipped: "Opcional",
      unknown: "Desconocido",
    };
    const classMap = {
      ok: "health-ok",
      degraded: "health-warn",
      skipped: "health-skip",
      unknown: "health-unknown",
    };
    return (
      <div className={`health-pill ${classMap[status] || "health-unknown"}`} title={missing.join(", ") || notes || ""}>
        <span className="dot" />
        <span className="text">{labelMap[status] || status}</span>
      </div>
    );
  };

  const retryInfo = health?.retry_strategy ? `Intentos: ${health.retry_strategy.attempts} / modo ${health.retry_strategy.mode}` : null;

  return (
    <div className={compact ? "model-select compact" : "model-select"}>
      {!compact && <label className="mr-2 font-semibold text-sm">Motor IA:</label>}
      <select
        value={provider}
        onChange={(e) => setProvider(e.target.value)}
        className="border rounded-md px-2 py-1 text-sm"
        title="Selecciona el backend de generación"
      >
        <option value="perplexity">{PROVIDER_LABELS.perplexity}</option>
        <option value="gemini_flash_2_5_demo">{PROVIDER_LABELS.gemini_flash_2_5_demo}</option>
      </select>

      <div className="health-row">
        <div className="health-item">
          <span className="health-name">Perplexity</span>
          {renderStatus("perplexity")}
        </div>
        <div className="health-item">
          <span className="health-name">Gemini</span>
          {renderStatus("gemini")}
        </div>
        <div className="health-item">
          <span className="health-name">Secundario</span>
          {renderStatus("stability_placeholder")}
        </div>
        {(retryInfo || error) && (
          <div className="health-meta" title={error || retryInfo}>
            {error ? "Health no disponible" : retryInfo}
          </div>
        )}
      </div>
    </div>
  );
}
