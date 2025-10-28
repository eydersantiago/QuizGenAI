# Pasos de Integración del Sistema de Edición de Preguntas

## Resumen
Esta guía te llevará paso a paso para integrar el sistema completo de edición y tracking de preguntas en tu proyecto QuizGenAI.

---

## Paso 1: Preparar el Backend

### 1.1 Importar los Nuevos Modelos

Edita `backend/api/models.py` y agrega al **FINAL** del archivo:

```python
# ============================================================================
# MODELOS DE TRACKING DE EDICIONES (importados de módulo separado)
# ============================================================================

from .models_question_tracking import QuestionEditLog, QuestionOriginMetadata

__all__ = [
    'GenerationSession',
    'RegenerationLog',
    'SavedQuiz',
    'AudioPrivacyPreference',
    'AudioSession',
    'AudioData',
    'AudioTranscription',
    'AudioDeletionAudit',
    'VoiceMetricEvent',
    'QuestionEditLog',          # NUEVO
    'QuestionOriginMetadata',   # NUEVO
]
```

### 1.2 Actualizar URLs

Edita `backend/api/urls.py` y agrega las nuevas rutas:

```python
from .views_question_editing import (
    create_session_with_edits,
    regenerate_in_preview_mode,
    track_question_edit,
    get_question_history
)

urlpatterns = [
    # ... rutas existentes ...

    # ========================================
    # Edición y tracking de preguntas
    # ========================================
    path(
        "sessions/create-with-edits/",
        create_session_with_edits,
        name="create_session_with_edits"
    ),
    path(
        "regenerate-preview/",
        regenerate_in_preview_mode,
        name="regenerate_preview"
    ),
    path(
        "track-edit/",
        track_question_edit,
        name="track_edit"
    ),
    path(
        "sessions/<uuid:session_id>/questions/<int:question_index>/history/",
        get_question_history,
        name="question_history"
    ),
]
```

---

## Paso 2: Crear y Ejecutar Migraciones

### 2.1 Crear Migraciones

```bash
cd backend
python manage.py makemigrations api
```

Deberías ver algo como:
```
Migrations for 'api':
  api/migrations/0005_questioneditlog_questionoriginmetadata.py
    - Create model QuestionEditLog
    - Create model QuestionOriginMetadata
    - Add index on questioneditlog (session, question_index)
    - Add index on questionoriginmetadata (session, question_index)
```

### 2.2 Aplicar Migraciones

```bash
python manage.py migrate
```

Deberías ver:
```
Running migrations:
  Applying api.0005_questioneditlog_questionoriginmetadata... OK
```

### 2.3 Verificar Tablas Creadas

```bash
python manage.py dbshell
```

Luego en SQLite:
```sql
.tables
-- Deberías ver:
-- question_edit_log
-- question_origin_metadata
```

---

## Paso 3: Actualizar el Frontend

### 3.1 Modificar handleEditorConfirm en QuizForm.jsx

Actualiza la función para usar el nuevo endpoint:

```javascript
// En QuizForm.jsx
const handleEditorConfirm = async (editedQuestions) => {
  try {
    setCreating(true);

    // CAMBIO: Usar nuevo endpoint con preguntas editadas
    const res = await fetch(
      `${API_BASE}/sessions/create-with-edits/`,
      withProviderHeaders(
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            topic,
            difficulty,
            types: Object.keys(types).filter((k) => types[k]),
            counts,
            questions: editedQuestions  // ← NUEVO: enviar preguntas editadas
          }),
        },
        provider,
        headerName
      )
    );

    let json = {};
    try {
      json = await res.json();
    } catch (_) {}

    if (!res.ok) {
      Swal.fire("Error", json?.error || "No se pudo crear la sesión", "error");
      return;
    }

    const sessionId = json.session_id;

    // Pop de éxito y luego redirigir
    await Swal.fire({
      title: "Sesión creada",
      text: `ID: ${sessionId}`,
      icon: "success",
      confirmButtonText: "Ir al quiz",
      timer: 1800,
      timerProgressBar: true,
    });

    // Limpiar datos guardados después del éxito
    clearSavedData();
    navigate(`/quiz/${sessionId}`);
  } catch (err) {
    Swal.fire("Error", String(err), "error");
  } finally {
    setCreating(false);
  }
};
```

### 3.2 Actualizar regenerateQuestion en QuizPreviewEditor.jsx

Modifica para usar el nuevo endpoint de regeneración:

```javascript
// En QuizPreviewEditor.jsx
const regenerateQuestion = useCallback(async (globalIdx) => {
  const questionToRegenerate = editedQuestions[globalIdx];

  // ... código de confirmación ...

  setQuestionLoading(globalIdx, true);

  try {
    // CAMBIO: Usar nuevo endpoint de regeneración en preview
    const response = await fetch(`${API_BASE}/regenerate-preview/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        topic: config.topic,
        difficulty: config.difficulty,
        type: questionToRegenerate.type,
        base_question: questionToRegenerate,
        session_id: sessionId,  // Enviar sessionId si existe
        index: globalIdx
      })
    });

    if (!response.ok) {
      throw new Error("Error al regenerar la pregunta");
    }

    const data = await response.json();
    const newQuestion = data.question;

    // Actualizar la pregunta en el estado
    setEditedQuestions(prev => prev.map((q, idx) => {
      if (idx === globalIdx) {
        return {
          ...newQuestion,
          originalIndex: q.originalIndex,
          isModified: true,
          isNew: false
        };
      }
      return q;
    }));

    Swal.fire({
      icon: "success",
      title: "Pregunta regenerada",
      text: "Se ha generado una nueva variante de la pregunta",
      timer: 2000,
      showConfirmButton: false
    });

  } catch (error) {
    console.error("Error regenerando pregunta:", error);
    Swal.fire({
      icon: "error",
      title: "Error",
      text: "No se pudo regenerar la pregunta. Intenta de nuevo.",
      confirmButtonText: "OK"
    });
  } finally {
    setQuestionLoading(globalIdx, false);
  }
}, [editedQuestions, sessionId, config, setQuestionLoading]);
```

---

## Paso 4: Testing Manual

### 4.1 Test Backend (Sin Frontend)

#### Test 1: Crear sesión sin preguntas (modo generación)
```bash
curl -X POST http://localhost:8000/api/sessions/create-with-edits/ \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "algoritmos",
    "difficulty": "Media",
    "types": ["mcq", "vf"],
    "counts": {"mcq": 3, "vf": 2}
  }'
```

Esperado:
```json
{
  "session_id": "...",
  "topic": "algoritmos",
  "difficulty": "Media",
  "questions_count": 5,
  "mode": "ai_generated",
  "provider": "gemini"
}
```

#### Test 2: Crear sesión con preguntas editadas
```bash
curl -X POST http://localhost:8000/api/sessions/create-with-edits/ \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "algoritmos",
    "difficulty": "Media",
    "types": ["mcq"],
    "counts": {"mcq": 1},
    "questions": [{
      "type": "mcq",
      "question": "¿Cuál es la complejidad de búsqueda binaria en un array ordenado?",
      "options": [
        "A) O(1)",
        "B) O(n)",
        "C) O(log n)",
        "D) O(n^2)"
      ],
      "answer": "C",
      "explanation": "La búsqueda binaria divide el espacio de búsqueda a la mitad en cada iteración.",
      "isModified": true,
      "originalIndex": 0
    }]
  }'
```

Esperado:
```json
{
  "session_id": "...",
  "topic": "algoritmos",
  "difficulty": "Media",
  "questions_count": 1,
  "mode": "edited"
}
```

#### Test 3: Regenerar en preview
```bash
curl -X POST http://localhost:8000/api/regenerate-preview/ \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "algoritmos",
    "difficulty": "Media",
    "type": "mcq",
    "base_question": {
      "type": "mcq",
      "question": "¿Qué es un algoritmo de ordenamiento?",
      "answer": "A"
    }
  }'
```

Esperado:
```json
{
  "question": {
    "type": "mcq",
    "question": "¿Cuál es la principal diferencia entre Bubble Sort y Quick Sort?",
    "options": [...],
    "answer": "C",
    "explanation": "..."
  },
  "provider": "gemini",
  "fallback_used": false
}
```

#### Test 4: Validación de seguridad (debe fallar)
```bash
curl -X POST http://localhost:8000/api/sessions/create-with-edits/ \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "algoritmos",
    "difficulty": "Media",
    "types": ["mcq"],
    "counts": {"mcq": 1},
    "questions": [{
      "type": "mcq",
      "question": "<script>alert(\"XSS\")</script>¿Qué es un algoritmo?",
      "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
      "answer": "A"
    }]
  }'
```

Esperado:
```json
{
  "error": "Datos inválidos",
  "details": {
    "questions": [
      {
        "question": ["La pregunta contiene caracteres o patrones no permitidos por seguridad"]
      }
    ]
  }
}
```

### 4.2 Test Frontend (Con UI)

1. **Ir a la app**: http://localhost:3000
2. **Configurar quiz**: tema="algoritmos", dificultad="Media", mcq=5
3. **Click "Previsualizar"**
   - Debe crear sesión temporal
   - Debe mostrar QuizPreviewEditor con 5 preguntas
4. **Editar una pregunta**:
   - Click "Editar" en pregunta 1
   - Cambiar enunciado
   - Click "Guardar"
   - Debe marcar como "Modificada"
5. **Duplicar una pregunta**:
   - Click "Duplicar" en pregunta 2
   - Debe aparecer copia inmediatamente después
   - Debe marcar como "Nueva"
6. **Regenerar una pregunta**:
   - Click "Regenerar" en pregunta 3
   - Debe mostrar spinner
   - Debe reemplazar con nueva pregunta
   - Debe marcar como "Modificada"
7. **Eliminar una pregunta**:
   - Click "Eliminar" en pregunta 4
   - Confirmar en modal
   - Pregunta debe desaparecer
8. **Confirmar y crear**:
   - Click "Confirmar y Crear Quiz"
   - Debe validar
   - Debe crear sesión
   - Debe redirigir a /quiz/{session_id}

---

## Paso 5: Verificar Tracking en Base de Datos

### 5.1 Verificar Logs Creados

Después de crear una sesión con preguntas editadas:

```bash
python manage.py dbshell
```

```sql
-- Ver logs de edición
SELECT
    id,
    question_index,
    operation_type,
    created_at
FROM question_edit_log
ORDER BY created_at DESC
LIMIT 10;

-- Ver metadata de origen
SELECT
    question_index,
    origin_type,
    edit_count,
    regeneration_count
FROM question_origin_metadata
ORDER BY question_index;
```

---

## Paso 6: Configuración de Seguridad (Opcional pero Recomendado)

### 6.1 Rate Limiting

En `backend/backend/settings.py`:

```python
INSTALLED_APPS = [
    # ... apps existentes ...
    'rest_framework',  # Ya debería estar
]

REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',   # 100 requests por hora para anónimos
        'user': '1000/hour'   # 1000 requests por hora para usuarios autenticados
    }
}
```

### 6.2 CORS (Si frontend y backend están en dominios diferentes)

```python
# settings.py
INSTALLED_APPS = [
    # ... apps existentes ...
    'corsheaders',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # ← Al principio
    'django.middleware.common.CommonMiddleware',
    # ... resto ...
]

# En desarrollo
CORS_ALLOW_ALL_ORIGINS = True

# En producción
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://tu-dominio.com",
]
```

### 6.3 Logging

```python
# settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'debug.log',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'api.views_question_editing': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
```

---

## Paso 7: Troubleshooting Común

### Problema 1: Migraciones no se aplican
```bash
# Listar migraciones
python manage.py showmigrations api

# Si hay conflictos, fusionar
python manage.py makemigrations --merge

# Aplicar de nuevo
python manage.py migrate
```

### Problema 2: Error 404 en endpoints
- Verificar que urls.py tenga las rutas correctas
- Verificar que el path no tenga trailing slash extra
- Reiniciar servidor Django

### Problema 3: ValidationError al crear sesión
- Verificar que JSON tenga todos los campos requeridos
- Revisar logs en `debug.log`
- Verificar que topic esté en taxonomía permitida

### Problema 4: Frontend no se conecta a backend
- Verificar REACT_APP_API_BASE en .env del frontend
- Verificar CORS configurado en Django
- Verificar que backend esté corriendo

---

## Paso 8: Métricas y Monitoreo

### 8.1 Panel de Admin Django

Registra los modelos en `backend/api/admin.py`:

```python
from django.contrib import admin
from .models_question_tracking import QuestionEditLog, QuestionOriginMetadata

@admin.register(QuestionEditLog)
class QuestionEditLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'session', 'question_index', 'operation_type', 'created_at']
    list_filter = ['operation_type', 'created_at']
    search_fields = ['session__id', 'session__topic']
    readonly_fields = ['id', 'created_at']

@admin.register(QuestionOriginMetadata)
class QuestionOriginMetadataAdmin(admin.ModelAdmin):
    list_display = ['session', 'question_index', 'origin_type', 'edit_count', 'regeneration_count']
    list_filter = ['origin_type']
    search_fields = ['session__id', 'session__topic']
```

### 8.2 Queries Útiles para Métricas

```python
# En Django shell (python manage.py shell)

from api.models_question_tracking import QuestionEditLog, QuestionOriginMetadata
from django.db.models import Count, Avg

# Tasa de edición general
total_questions = QuestionOriginMetadata.objects.count()
edited_questions = QuestionOriginMetadata.objects.filter(edit_count__gt=0).count()
edit_rate = (edited_questions / total_questions * 100) if total_questions > 0 else 0
print(f"Tasa de edición: {edit_rate:.2f}%")

# Promedio de ediciones por pregunta
avg_edits = QuestionOriginMetadata.objects.aggregate(Avg('edit_count'))
print(f"Promedio de ediciones: {avg_edits['edit_count__avg']:.2f}")

# Distribución por tipo de origen
distribution = QuestionOriginMetadata.objects.values('origin_type').annotate(count=Count('id'))
for item in distribution:
    print(f"{item['origin_type']}: {item['count']}")

# Preguntas más editadas
top_edited = QuestionOriginMetadata.objects.filter(
    edit_count__gt=0
).order_by('-edit_count')[:10]

for meta in top_edited:
    print(f"Sesión {meta.session_id}, Q{meta.question_index}: {meta.edit_count} ediciones")
```

---

## Checklist Final

- [ ] Archivos copiados: `models_question_tracking.py`, `views_question_editing.py`, `serializers.py` actualizado
- [ ] `models.py` actualizado con imports
- [ ] `urls.py` actualizado con nuevas rutas
- [ ] Migraciones creadas y aplicadas
- [ ] Frontend actualizado: `QuizForm.jsx` y `QuizPreviewEditor.jsx`
- [ ] Tests backend ejecutados exitosamente
- [ ] Test frontend manual completado
- [ ] Tracking verificado en base de datos
- [ ] Seguridad configurada (rate limiting, CORS, logging)
- [ ] Admin Django configurado
- [ ] Documentación leída: `QUESTION_EDITING_GUIDE.md`

---

¡Listo! El sistema de edición de preguntas con tracking completo está integrado. 🎉
