// src/components/ModelProviderSelect.jsx
import React from "react";
import { useModelProvider, PROVIDER_LABELS } from "../ModelProviderContext";
import "../estilos/ModelProviderSelect.css";

export default function ModelProviderSelect({ compact = false }) {
  const { provider, setProvider } = useModelProvider();
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
    </div>
  );
}
