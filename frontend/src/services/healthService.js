// services/healthService.js
// Utilidades para consultar la salud de los proveedores de IA expuestos por el backend

const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:8000/api";

export async function fetchProvidersHealth() {
  const res = await fetch(`${API_BASE}/health/providers/`);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Health check failed: ${res.status} ${text}`.trim());
  }
  return res.json();
}

export function mapHealthByName(health) {
  const providers = health?.providers || [];
  return providers.reduce((acc, p) => {
    acc[p.name] = p;
    return acc;
  }, {});
}
