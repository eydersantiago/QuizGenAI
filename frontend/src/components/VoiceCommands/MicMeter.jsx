import React from "react";
import "../../estilos/VoiceCommandPanel.css";

export default function MicMeter({ level=0, db=-Infinity, listening=false }) {
  const pct = Math.round(level * 100);
  return (
    <div className="mic-wrap" aria-live="polite">
      <div className={`mic-led ${listening ? "on" : "off"} ${level > 0.9 ? "clip" : ""}`} />
      <div className="mic-bar">
        <div className="mic-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="mic-text">
        {listening ? `🎙️ escuchando · ${pct}% (${db.toFixed(1)} dB)` : "Mic apagado"}
      </div>
    </div>
  );
}
