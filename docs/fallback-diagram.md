# Fallback LLM e Imágenes (Gemini ⇄ OpenAI)

```mermaid
graph TD
    A[Petición con X-LLM-Provider\n(openai|gemini)] --> B{Proveedor preferido?}
    B -->|Gemini| C[Gemini]
    B -->|OpenAI| D[OpenAI]
    C --> E{Exitoso?}
    D --> F{Exitoso?}
    E -->|Sí| G[Responder]
    F -->|Sí| G
    E -->|No\n(Sin créditos u otro error)| D
    F -->|No\n(Sin créditos u otro error)| C
    C -->|Timeout/errores| H[Sentry + error 5xx/503]
    D -->|Timeout/errores| H
```

## Reglas clave
- **Orden dinámico:** el header `X-LLM-Provider` fija el orden de prueba. `gemini` prueba Gemini primero y cae a OpenAI; `openai` invierte el orden.
- **Reintentos:** cada proveedor se invoca con hasta **2 reintentos adicionales** (backoff exponencial 1s → 2s) antes de marcarse como fallo.
- **Cobertura:**
  - Generación y regeneración de preguntas.
  - Generación de imágenes de portada.
  - Sugerencias NLU en el motor proactivo.
- **Errores y monitoreo:** cuando ambos proveedores fallan o se quedan sin créditos se devuelve 503 y se reporta a Sentry.
- **Configuración:**
  - `GEMINI_API_KEY` (rotación automática si hay múltiples claves).
  - `OPENAI_API_KEY` (texto, imágenes y sugerencias). Modelos por defecto: `gemini-2.5-flash` / `gpt-4o-mini` para texto y `dall-e-3` para imágenes.
