# Diagrama de fallback y manejo de errores IA

Este flujo resume cómo se manejan los proveedores de generación de preguntas y los reintentos con backoff exponencial.

```mermaid
graph TD
    A[Solicitud de generación/regeneración] --> B[Proveedor preferido (X-LLM-Provider)]
    B -->|éxito| Z[Respuesta OK]
    B -->|error| C[Reintento (backoff 0.75s -> 1.5s)]
    C -->|éxito| Z
    C -->|error| D[Fallback proveedor alterno]
    D -->|éxito| Z
    D -->|error| E[Proveedor secundario (placeholder Stability)]
    E -->|éxito| Z
    E -->|error| F[Error final providers_failed]
```

**Detalles clave**
- Cada proveedor remoto (Gemini/Perplexity) tiene 2 intentos con backoff exponencial.
- Si ambos fallan (por ejemplo, sin créditos), se recurre al proveedor secundario local `stability_placeholder` para mantener la continuidad del servicio.
- El endpoint `GET /api/health/providers/` expone el estado de configuración de cada proveedor y la política de reintentos para monitoreo.
- Los errores y fallbacks quedan registrados en el logging estructurado y (si se configura `SENTRY_DSN`) se reportan a Sentry.
