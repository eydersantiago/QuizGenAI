# Guía de Implementación: Sistema de Edición de Preguntas con Tracking

Esta guía explica la implementación completa del sistema de previsualización y edición de preguntas con tracking detallado.

## Tabla de Contenidos

1. [Arquitectura General](#arquitectura-general)
2. [Modelos de Base de Datos](#modelos-de-base-de-datos)
3. [Serializers y Validación](#serializers-y-validación)
4. [Endpoints API](#endpoints-api)
5. [Tracking de Ediciones](#tracking-de-ediciones)
6. [Seguridad](#seguridad)
7. [Flujos de Usuario](#flujos-de-usuario)
8. [Instalación y Migración](#instalación-y-migración)

---

## Arquitectura General

### Componentes Principales

```
Frontend (React)
    ↓
QuizPreviewEditor
    ↓
Backend API Endpoints
    ↓
┌─────────────────────────────────────┐
│  Capa de Validación (Serializers)  │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Capa de Negocio (Views)            │
│  - Validación                       │
│  - Sanitización                     │
│  - Tracking                         │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Modelos de Datos                   │
│  - GenerationSession                │
│  - QuestionEditLog                  │
│  - QuestionOriginMetadata           │
│  - RegenerationLog                  │
└─────────────────────────────────────┘
```

---

## Modelos de Base de Datos

### 1. QuestionEditLog

**Propósito**: Registrar TODAS las operaciones realizadas sobre cada pregunta.

**Campos clave**:
- `session`: FK a GenerationSession
- `question_index`: Índice de la pregunta en el array
- `operation_type`: Tipo de operación (manual_edit, ai_regeneration, duplication, creation)
- `question_before`: Estado anterior (JSON)
- `question_after`: Estado posterior (JSON)
- `changed_fields`: Lista de campos modificados
- `ai_provider`: Proveedor usado (gemini/perplexity/local)
- `created_at`: Timestamp de la operación

**Ejemplo de uso**:
```python
# Usuario edita el enunciado
QuestionEditLog.log_manual_edit(
    session=session,
    index=0,
    before={'question': 'Pregunta original', ...},
    after={'question': 'Pregunta editada', ...}
)

# Usuario regenera con IA
QuestionEditLog.log_ai_regeneration(
    session=session,
    index=0,
    before={'question': 'Pregunta vieja', ...},
    after={'question': 'Pregunta regenerada', ...},
    provider='gemini'
)
```

### 2. QuestionOriginMetadata

**Propósito**: Mantener el estado ACTUAL de origen de cada pregunta (snapshot rápido).

**Campos clave**:
- `origin_type`: pure_ai, ai_edited, user_created, duplicated
- `edit_count`: Número de ediciones manuales
- `regeneration_count`: Número de regeneraciones con IA
- `initial_ai_provider`: Proveedor que generó inicialmente

**Ventajas**:
- Consultas rápidas sin procesar todo el log
- Métricas agregadas fáciles
- Índices optimizados

---

## Serializers y Validación

### EditableQuestionSerializer

Valida cada pregunta individual con **múltiples capas de seguridad**:

```python
class EditableQuestionSerializer(serializers.Serializer):
    # Validaciones base
    type = ChoiceField(['mcq', 'vf', 'short'])
    question = CharField(min=10, max=500)
    options = ListField(child=CharField(max=200))
    answer = CharField(required=True)

    # Validaciones de seguridad
    def validate_question(self, value):
        # 1. Detectar HTML/JS injection
        if re.search(r'<script', value, re.I):
            raise ValidationError("Patrón peligroso")

        # 2. Detectar SQL injection
        if re.search(r"union\s+select", value, re.I):
            raise ValidationError("Patrón peligroso")

        # 3. Detectar caracteres sospechosos
        if re.search(r'[\{\}\[\]<>]{5,}', value):
            raise ValidationError("Secuencia sospechosa")

        return value
```

### Función sanitize_question_data()

Capa adicional de sanitización:

```python
def sanitize_question_data(question_dict):
    """
    - Remueve campos no autorizados
    - Limita longitud de strings
    - Elimina caracteres de control
    - Normaliza tipos de datos
    """
    allowed_fields = {
        'type', 'question', 'options', 'answer',
        'explanation', 'originalIndex', 'isModified', 'isNew'
    }

    sanitized = {}
    for key in allowed_fields:
        if key in question_dict:
            value = question_dict[key]

            # Sanitizar strings
            if isinstance(value, str):
                # Remover caracteres de control
                value = ''.join(
                    char for char in value
                    if ord(char) >= 32 or char in ('\n', '\t')
                )

                # Limitar longitud
                if key == 'question':
                    value = value[:500]
                elif key == 'answer':
                    value = value[:500]

            sanitized[key] = value

    return sanitized
```

---

## Endpoints API

### 1. POST /api/sessions/create-with-edits/

**Propósito**: Crear sesión con soporte para preguntas editadas.

**Casos de uso**:

#### Caso A: Solo configuración (generación automática)
```json
POST /api/sessions/create-with-edits/
{
  "topic": "algoritmos",
  "difficulty": "Media",
  "types": ["mcq", "vf"],
  "counts": {"mcq": 5, "vf": 3}
}
```

Respuesta:
```json
{
  "session_id": "uuid-here",
  "topic": "algoritmos",
  "difficulty": "Media",
  "questions_count": 8,
  "mode": "ai_generated",
  "provider": "gemini"
}
```

#### Caso B: Con preguntas editadas (confirmación después de editar)
```json
POST /api/sessions/create-with-edits/
{
  "topic": "algoritmos",
  "difficulty": "Media",
  "types": ["mcq", "vf"],
  "counts": {"mcq": 5, "vf": 3},
  "questions": [
    {
      "type": "mcq",
      "question": "¿Cuál es la complejidad de búsqueda binaria?",
      "options": ["A) O(1)", "B) O(n)", "C) O(log n)", "D) O(n^2)"],
      "answer": "C",
      "explanation": "La búsqueda binaria divide el espacio...",
      "isModified": true,
      "originalIndex": 0
    },
    {
      "type": "vf",
      "question": "Quicksort es siempre O(n log n)",
      "answer": "Falso",
      "explanation": "En el peor caso es O(n^2)",
      "isNew": true,
      "originalIndex": -1
    }
  ]
}
```

Respuesta:
```json
{
  "session_id": "uuid-here",
  "topic": "algoritmos",
  "difficulty": "Media",
  "questions_count": 2,
  "mode": "edited"
}
```

**Validaciones aplicadas**:
1. Validación de schema con `SessionWithEditedQuestionsSerializer`
2. Sanitización con `sanitize_question_data()`
3. Validación secundaria con `EditableQuestionSerializer`
4. Verificación de dominio (taxonomía)
5. Detección de duplicados

**Tracking creado**:
- `QuestionEditLog` para cada pregunta (según isModified/isNew)
- `QuestionOriginMetadata` para cada pregunta

### 2. POST /api/regenerate-preview/

**Propósito**: Regenerar pregunta en modo preview (sin session_id obligatorio).

**Request**:
```json
POST /api/regenerate-preview/
{
  "topic": "algoritmos",
  "difficulty": "Media",
  "type": "mcq",
  "base_question": {
    "type": "mcq",
    "question": "¿Qué es un árbol AVL?",
    ...
  },
  "avoid_phrases": ["árbol AVL", "árbol binario balanceado"],
  "session_id": "uuid-optional",
  "index": 0
}
```

**Response**:
```json
{
  "question": {
    "type": "mcq",
    "question": "¿Cuál es la característica principal de un árbol rojo-negro?",
    "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
    "answer": "B",
    "explanation": "..."
  },
  "provider": "gemini",
  "fallback_used": false
}
```

**Características**:
- No requiere session_id (funciona en preview)
- Si hay session_id, crea logs de tracking
- Usa `avoid_phrases` para evitar duplicados
- Reintentos automáticos si tiene issues severos

### 3. POST /api/track-edit/

**Propósito**: Registrar edición manual para tracking (llamado desde frontend).

**Request**:
```json
POST /api/track-edit/
{
  "session_id": "uuid",
  "question_index": 0,
  "question_before": {...},
  "question_after": {...}
}
```

**Response**:
```json
{
  "success": true,
  "message": "Edición registrada correctamente"
}
```

### 4. GET /api/sessions/{session_id}/questions/{index}/history/

**Propósito**: Obtener historial completo de ediciones de una pregunta.

**Response**:
```json
{
  "session_id": "uuid",
  "question_index": 0,
  "history": [
    {
      "id": "log-uuid-1",
      "operation_type": "manual_edit",
      "question_before": {...},
      "question_after": {...},
      "changed_fields": ["question", "explanation"],
      "ai_provider": null,
      "created_at": "2025-01-15T10:30:00Z",
      "summary": "Editados campos: question, explanation"
    },
    {
      "id": "log-uuid-2",
      "operation_type": "ai_regeneration",
      "question_before": {...},
      "question_after": {...},
      "changed_fields": ["question", "answer", "options", "explanation"],
      "ai_provider": "gemini",
      "created_at": "2025-01-15T10:35:00Z",
      "summary": "Regenerado con gemini"
    }
  ],
  "metadata": {
    "origin_type": "ai_edited",
    "edit_count": 2,
    "regeneration_count": 1,
    "total_operations": 3,
    "initial_provider": "gemini"
  }
}
```

---

## Tracking de Ediciones

### Escenario Complejo: Editar → Regenerar → Editar

**Situación**: Usuario realiza múltiples operaciones sobre la misma pregunta.

**Timeline**:

1. **T0**: Pregunta generada por IA
   ```json
   {"question": "¿Qué es un algoritmo?", ...}
   ```
   - Se crea: `QuestionOriginMetadata(origin_type='pure_ai', edit_count=0)`

2. **T1**: Usuario edita manualmente
   ```json
   {"question": "Explique qué es un algoritmo", ...}
   ```
   - Se crea: `QuestionEditLog(operation_type='manual_edit', ...)`
   - Se actualiza: `QuestionOriginMetadata(origin_type='ai_edited', edit_count=1)`

3. **T2**: Usuario regenera con IA
   ```json
   {"question": "¿Cuál es la definición formal de algoritmo?", ...}
   ```
   - Se crea: `QuestionEditLog(operation_type='ai_regeneration', provider='gemini', ...)`
   - Se actualiza: `QuestionOriginMetadata(regeneration_count=1)`

4. **T3**: Usuario edita nuevamente
   ```json
   {"question": "¿Cuál es la definición formal y precisa de algoritmo?", ...}
   ```
   - Se crea: `QuestionEditLog(operation_type='manual_edit', ...)`
   - Se actualiza: `QuestionOriginMetadata(edit_count=2)`

**Resultado final**:
- 3 logs en `QuestionEditLog` (secuencia completa)
- `QuestionOriginMetadata`:
  ```json
  {
    "origin_type": "ai_edited",
    "edit_count": 2,
    "regeneration_count": 1,
    "total_operations": 3
  }
  ```

**NO se pierde tracking**: Toda la historia está preservada en `QuestionEditLog`, y el estado actual en `QuestionOriginMetadata`.

---

## Seguridad

### Capas de Protección

```
Request (JSON)
    ↓
1. Serializer Validation
   - Schema validation
   - Type checking
   - Range validation
    ↓
2. Sanitization
   - Remove dangerous chars
   - Limit length
   - Strip unauthorized fields
    ↓
3. Security Validation
   - Injection detection (HTML/JS/SQL)
   - Suspicious patterns
   - Duplicate detection
    ↓
4. Secondary Validation
   - Re-validate after sanitization
   - Cross-field checks
    ↓
5. Business Logic
   - Save to database
   - Create tracking logs
```

### Ataques Prevenidos

#### 1. HTML/JavaScript Injection
```python
# BLOQUEADO
{
  "question": "<script>alert('XSS')</script>¿Qué es...?"
}
# Error: "La pregunta contiene caracteres o patrones no permitidos"
```

#### 2. SQL Injection
```python
# BLOQUEADO
{
  "question": "¿Qué es...? ' OR '1'='1"
}
# Error: "La pregunta contiene patrones no permitidos por seguridad"
```

#### 3. Campos No Autorizados
```python
# Request malicioso
{
  "question": "...",
  "malicious_field": "DROP TABLE users",
  "__proto__": {"admin": true}
}

# Después de sanitize_question_data():
{
  "question": "..."
  # malicious_field y __proto__ removidos
}
```

#### 4. Longitud Excesiva (DoS)
```python
# BLOQUEADO
{
  "question": "A" * 10000  # 10KB
}
# Truncado a 500 caracteres máximo
```

#### 5. Caracteres de Control
```python
# Request con caracteres de control
{
  "question": "¿Qué\x00es\x01un\x02algoritmo?"
}

# Sanitizado a:
{
  "question": "¿Qué es un algoritmo?"
}
```

### Rate Limiting (Recomendado)

Agregar en `settings.py`:
```python
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour'
    }
}
```

---

## Flujos de Usuario

### Flujo Completo: Desde Configuración hasta Quiz Final

```
1. Usuario en QuizForm
   ↓
2. Configura: tema, dificultad, tipos, cantidades
   ↓
3. Click "Previsualizar"
   ↓
4. Frontend llama POST /api/sessions/
   - Crea sesión temporal
   - Genera preguntas con IA
   ↓
5. Frontend llama POST /api/preview/ con session_id
   - Persiste preguntas en latest_preview
   - Retorna preguntas
   ↓
6. Frontend muestra QuizPreviewEditor
   ↓
7. Usuario EDITA, DUPLICA, ELIMINA, REGENERA
   - Cada regeneración llama /api/regenerate-preview/
   - Frontend mantiene estado local
   ↓
8. Usuario click "Confirmar y Crear Quiz"
   ↓
9. Frontend llama POST /api/sessions/create-with-edits/
   con questions editadas
   ↓
10. Backend:
    - Valida y sanitiza TODAS las preguntas
    - Crea logs de tracking
    - Guarda en latest_preview
    - Retorna session_id
    ↓
11. Frontend redirige a /quiz/{session_id}
```

---

## Instalación y Migración

### Paso 1: Agregar los Nuevos Archivos

1. Copiar archivos:
   - `api/models_question_tracking.py`
   - `api/serializers.py` (actualizado)
   - `api/views_question_editing.py`

2. Importar modelos en `api/models.py`:
```python
# Al final de api/models.py
from .models_question_tracking import QuestionEditLog, QuestionOriginMetadata
```

### Paso 2: Actualizar URLs

En `api/urls.py`:
```python
from .views_question_editing import (
    create_session_with_edits,
    regenerate_in_preview_mode,
    track_question_edit,
    get_question_history
)

urlpatterns = [
    # ... rutas existentes ...

    # Nuevas rutas
    path("sessions/create-with-edits/", create_session_with_edits, name="create_session_with_edits"),
    path("regenerate-preview/", regenerate_in_preview_mode, name="regenerate_preview"),
    path("track-edit/", track_question_edit, name="track_edit"),
    path("sessions/<uuid:session_id>/questions/<int:question_index>/history/",
         get_question_history,
         name="question_history"),
]
```

### Paso 3: Crear Migración

```bash
python manage.py makemigrations
python manage.py migrate
```

### Paso 4: Actualizar Frontend

Modificar `QuizForm.jsx`:
```javascript
// En handleEditorConfirm
const handleEditorConfirm = async (editedQuestions) => {
  const res = await fetch(`${API_BASE}/sessions/create-with-edits/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      topic,
      difficulty,
      types,
      counts,
      questions: editedQuestions  // Preguntas editadas
    })
  });

  const json = await res.json();
  navigate(`/quiz/${json.session_id}`);
};
```

### Paso 5: Testing

```bash
# Test crear sesión sin preguntas
curl -X POST http://localhost:8000/api/sessions/create-with-edits/ \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "algoritmos",
    "difficulty": "Media",
    "types": ["mcq"],
    "counts": {"mcq": 3}
  }'

# Test crear sesión con preguntas editadas
curl -X POST http://localhost:8000/api/sessions/create-with-edits/ \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "algoritmos",
    "difficulty": "Media",
    "types": ["mcq"],
    "counts": {"mcq": 1},
    "questions": [{
      "type": "mcq",
      "question": "¿Qué es un algoritmo de ordenamiento?",
      "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
      "answer": "A",
      "isModified": true,
      "originalIndex": 0
    }]
  }'

# Test regenerar en preview
curl -X POST http://localhost:8000/api/regenerate-preview/ \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "algoritmos",
    "difficulty": "Media",
    "type": "mcq"
  }'
```

---

## Métricas y Análisis

### Consultas Útiles

#### 1. Preguntas más editadas
```python
from django.db.models import Count

QuestionOriginMetadata.objects.filter(
    edit_count__gt=0
).order_by('-edit_count')[:10]
```

#### 2. Tasa de edición por sesión
```python
sessions_with_edits = QuestionEditLog.objects.values('session').distinct().count()
total_sessions = GenerationSession.objects.count()
edit_rate = (sessions_with_edits / total_sessions) * 100
```

#### 3. Distribución de tipos de origen
```python
from django.db.models import Count

QuestionOriginMetadata.objects.values('origin_type').annotate(
    count=Count('id')
)
```

#### 4. Proveedores más usados en regeneraciones
```python
QuestionEditLog.objects.filter(
    operation_type='ai_regeneration'
).values('ai_provider').annotate(
    count=Count('id')
)
```

---

## Conclusión

Este sistema proporciona:

✅ **Validación robusta** con múltiples capas de seguridad
✅ **Tracking completo** de todas las operaciones
✅ **Flexibilidad** para el usuario (editar, regenerar, duplicar)
✅ **Auditoría** detallada para análisis y métricas
✅ **Prevención** de ataques comunes (injection, DoS)
✅ **Escalabilidad** con modelos optimizados e índices

El usuario tiene control total sobre las preguntas antes de confirmar, y el sistema mantiene un historial completo para análisis y mejora continua.
