// src/ModelProviderContext.jsx
import React, { createContext, useContext, useEffect, useMemo, useState } from "react";


const DEFAULT_PROVIDER = "openai";
const ALLOWED_PROVIDERS = ["openai", "gemini"];
const STORAGE_KEY = "quizgenai_llm_provider";
const CTX = createContext({ provider: DEFAULT_PROVIDER, setProvider: () => {}, headerName: "X-LLM-Provider" });

export function ModelProviderProvider({ children }) {
  const [provider, setProvider] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored && ALLOWED_PROVIDERS.includes(stored)) return stored;
      return DEFAULT_PROVIDER;
    } catch { return DEFAULT_PROVIDER; }
  });

  useEffect(() => { try { localStorage.setItem(STORAGE_KEY, provider); } catch {} }, [provider]);

  const value = useMemo(() => ({ provider, setProvider, headerName: "X-LLM-Provider" }), [provider]);
  return <CTX.Provider value={value}>{children}</CTX.Provider>;
}

export function useModelProvider() {
  return useContext(CTX);
}

// Adjunta el header de proveedor a cualquier fetch
export function withProviderHeaders(init = {}, provider, headerName = "X-LLM-Provider") {
  const headers = { ...(init.headers || {}) };
  headers[headerName] = provider;
  return { ...init, headers };
}

export const PROVIDER_LABELS = {
  openai: "OpenAI [procura no usar en pruebas]",
  gemini: "Gemini Flash 2.5 [usar en pruebas]",
};
