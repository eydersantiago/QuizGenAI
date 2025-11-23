# api/serializers.py
from rest_framework import serializers
from .models import SavedQuiz, GenerationSession, GeneratedImage
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
import re

TAXONOMY = [
    "algoritmos", "redes", "bd", "bases de datos",
    "sistemas operativos", "poo", "ciberseguridad",
    "ia básica", "arquitectura", "estructura de datos",
    "complejidad computacional", "np-completitud",
    "teoría de la computación", "autómatas y gramáticas"
]

DIFFICULTY_CHOICES = ["Fácil", "Media", "Difícil"]
TYPE_CHOICES = ["mcq", "vf", "short"]

class RegenerateRequestSerializer(serializers.Serializer):
    session_id = serializers.CharField()
    index = serializers.IntegerField(min_value=0)
    type = serializers.ChoiceField(choices=TYPE_CHOICES)
    topic = serializers.CharField(required=False, allow_blank=False)
    difficulty = serializers.ChoiceField(choices=DIFFICULTY_CHOICES, required=False)
    debug = serializers.BooleanField(required=False, default=False)

    def validate_topic(self, value):
        v = value.strip().lower()
        if v not in [t.lower() for t in TAXONOMY]:
            raise serializers.ValidationError(
                "El tema no está en la taxonomía permitida (HU-06)."
            )
        return value

class QuestionSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=TYPE_CHOICES)
    question = serializers.CharField()
    answer = serializers.CharField(required=False, allow_blank=True)
    options = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=True
    )
    explanation = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        t = data.get("type")
        if t == "mcq":
            if "options" not in data or not isinstance(data["options"], list) or len(data["options"]) < 3:
                raise serializers.ValidationError("MCQ requiere al menos 3 opciones.")
            if "answer" not in data:
                raise serializers.ValidationError("MCQ requiere campo 'answer' (A/B/C/D).")
        if t == "vf":
            # answer esperado: "Verdadero" o "Falso"
            ans = (data.get("answer") or "").strip().lower()
            if ans not in ["verdadero", "falso"]:
                raise serializers.ValidationError("VF requiere answer = 'Verdadero' o 'Falso'.")
        # short: opcionalmente puede traer 'answer' y 'explanation'
        return data


class SavedQuizSerializer(serializers.ModelSerializer):
    progress_percentage = serializers.ReadOnlyField(source='get_progress_percentage')
    answered_count = serializers.ReadOnlyField(source='get_answered_count')
    total_questions = serializers.SerializerMethodField()
    marked_count = serializers.SerializerMethodField()
    is_review = serializers.SerializerMethodField()
    original_quiz_info = serializers.SerializerMethodField()
    cover_image = serializers.SerializerMethodField()

    class Meta:
        model = SavedQuiz
        fields = [
            'id', 'title', 'topic', 'category', 'difficulty',
                'cover_image',
            'types', 'counts', 'questions', 'user_answers',
            'current_question', 'is_completed', 'score',
            'favorite_questions',  # Campo de preguntas marcadas
            'created_at', 'updated_at', 'last_accessed',
            'progress_percentage', 'answered_count', 'total_questions',
            'marked_count',  # Conteo de preguntas marcadas
            'is_review',  # Indica si es un quiz de repaso
            'original_quiz_info'  # Información básica del quiz original
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_total_questions(self, obj):
        """Retorna el número total de preguntas en el quiz"""
        return len(obj.questions) if obj.questions else 0

    def get_cover_image(self, obj):
        """Devuelve la URL pública completa de la imagen de portada.
        Si `cover_image` ya es una URL absoluta, la devuelve tal cual. Si es
        una ruta relativa (p.ej. 'generated/x.png'), la prefija con
        `settings.MEDIA_URL`.
        """
        v = (getattr(obj, 'cover_image', '') or '')
        v = v.strip()
        if not v:
            return ''
        if v.startswith('http://') or v.startswith('https://'):
            return v
        # Si tenemos la request en el contexto, preferimos construir una URL absoluta
        # que use el proxy interno para servir archivos desde MEDIA_ROOT (más robusto en dev).
        req = self.context.get('request') if hasattr(self, 'context') else None
        if req:
            try:
                return req.build_absolute_uri(f"/api/media/proxy/{v.lstrip('/')}" )
            except Exception:
                pass

        # Fallback: construir con MEDIA_URL
        media_url = (getattr(settings, 'MEDIA_URL', '/') or '/')
        if not media_url.endswith('/'):
            media_url = media_url + '/'
        if v.startswith('/'):
            v = v.lstrip('/')
        return f"{media_url}{v}"

    def get_marked_count(self, obj):
        """Retorna el número de preguntas marcadas como favoritas"""
        if obj.favorite_questions and isinstance(obj.favorite_questions, list):
            return len(obj.favorite_questions)
        return 0

    def get_is_review(self, obj):
        """Indica si este quiz es un repaso de otro quiz"""
        return obj.is_review_quiz()

    def get_original_quiz_info(self, obj):
        """
        Retorna información básica del quiz original si este es un repaso

        Returns:
            dict o None: Información del quiz original (id, title, topic) o None si no es repaso
        """
        if not obj.is_review_quiz():
            return None

        original = obj.original_quiz
        if not original:
            return None

        return {
            'id': str(original.id),
            'title': original.title,
            'topic': original.topic,
            'difficulty': original.difficulty
        }

    def validate_favorite_questions(self, value):
        """
        Valida que favorite_questions sea una lista de enteros o None/null

        Args:
            value: El valor a validar (puede ser lista, None, o null)

        Returns:
            Lista validada de enteros o lista vacía

        Raises:
            serializers.ValidationError: Si el formato es inválido
        """
        # Permitir None o null
        if value is None:
            return []

        # Debe ser una lista
        if not isinstance(value, list):
            raise serializers.ValidationError(
                "favorite_questions debe ser una lista de índices de preguntas"
            )

        # Validar que todos los elementos sean enteros
        for item in value:
            if not isinstance(item, int):
                raise serializers.ValidationError(
                    f"Todos los elementos deben ser enteros. Encontrado: {type(item).__name__}"
                )

            # Validar que sean no negativos
            if item < 0:
                raise serializers.ValidationError(
                    f"Los índices no pueden ser negativos. Encontrado: {item}"
                )

        # Remover duplicados manteniendo el orden
        seen = set()
        unique_values = []
        for item in value:
            if item not in seen:
                seen.add(item)
                unique_values.append(item)

        return unique_values


class SavedQuizListSerializer(serializers.ModelSerializer):
    """
    Serializer simplificado para listado de quizzes guardados

    Incluye información resumida optimizada para mostrar en tarjetas/listas,
    incluyendo el conteo de preguntas marcadas como favoritas e información jerárquica.
    """
    progress_percentage = serializers.ReadOnlyField(source='get_progress_percentage')
    answered_count = serializers.ReadOnlyField(source='get_answered_count')
    total_questions = serializers.SerializerMethodField()
    marked_count = serializers.SerializerMethodField()
    is_review = serializers.SerializerMethodField()
    original_quiz_info = serializers.SerializerMethodField()

    class Meta:
        model = SavedQuiz
        fields = [
            'id', 'title', 'topic', 'category', 'difficulty',
                'cover_image',
            'is_completed', 'created_at', 'updated_at', 'last_accessed',
            'progress_percentage', 'answered_count', 'total_questions',
            'favorite_questions',  # Lista completa de índices marcados
            'marked_count',  # Conteo rápido para UI
            'is_review',  # Indica si es un quiz de repaso
            'original_quiz_info'  # Info del quiz original si es repaso
        ]

    cover_image = serializers.SerializerMethodField()

    def get_cover_image(self, obj):
        v = (getattr(obj, 'cover_image', '') or '').strip()
        if not v:
            return ''
        if v.startswith('http://') or v.startswith('https://'):
            return v
        # Prefer proxy URL when request is available
        req = self.context.get('request') if hasattr(self, 'context') else None
        if req:
            try:
                return req.build_absolute_uri(f"/api/media/proxy/{v.lstrip('/')}" )
            except Exception:
                pass

        media_url = (getattr(settings, 'MEDIA_URL', '/') or '/')
        if not media_url.endswith('/'):
            media_url = media_url + '/'
        if v.startswith('/'):
            v = v.lstrip('/')
        return f"{media_url}{v}"

    def get_total_questions(self, obj):
        """Retorna el número total de preguntas en el quiz"""
        return len(obj.questions) if obj.questions else 0

    def get_marked_count(self, obj):
        """
        Retorna el número de preguntas marcadas como favoritas

        Este campo calculado facilita mostrar badges/contadores en la UI
        sin necesidad de calcular en el frontend.

        Returns:
            int: Número de preguntas marcadas (0 si no hay ninguna)
        """
        if obj.favorite_questions and isinstance(obj.favorite_questions, list):
            return len(obj.favorite_questions)
        return 0

    def get_is_review(self, obj):
        """Indica si este quiz es un repaso"""
        return obj.is_review_quiz()

    def get_original_quiz_info(self, obj):
        """Retorna información básica del quiz original si es repaso"""
        if not obj.is_review_quiz():
            return None

        original = obj.original_quiz
        if not original:
            return None

        return {
            'id': str(original.id),
            'title': original.title,
            'topic': original.topic
        }


class SaveQuizRequestSerializer(serializers.Serializer):
    """
    Serializer para requests de guardado de cuestionario

    Maneja la creación y actualización de quizzes guardados,
    incluyendo preguntas marcadas como favoritas.
    """
    title = serializers.CharField(max_length=200)
    session_id = serializers.CharField(required=False, allow_blank=True)
    topic = serializers.CharField(max_length=200, required=False)
    difficulty = serializers.ChoiceField(choices=DIFFICULTY_CHOICES, required=False)
    types = serializers.ListField(child=serializers.CharField(), required=False)
    counts = serializers.DictField(required=False)
    questions = serializers.ListField(child=serializers.DictField(), required=False)
    user_answers = serializers.DictField(required=False)
    current_question = serializers.IntegerField(min_value=0, required=False)
    favorite_questions = serializers.ListField(
        child=serializers.IntegerField(min_value=0),
        required=False,
        allow_null=True,
        allow_empty=True,
        help_text="Lista de índices de preguntas marcadas como favoritas"
    )
    original_quiz_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="ID del quiz original si este es un quiz de repaso"
    )

    def validate_favorite_questions(self, value):
        """
        Valida el campo favorite_questions permitiendo None, [], o lista de enteros

        Args:
            value: Puede ser None, lista vacía, o lista de enteros

        Returns:
            Lista validada (puede ser vacía)
        """
        # None o null se convierte en lista vacía
        if value is None:
            return []

        # Si ya es una lista, validar duplicados
        if isinstance(value, list):
            # Remover duplicados manteniendo orden
            seen = set()
            unique_values = []
            for item in value:
                if item not in seen:
                    seen.add(item)
                    unique_values.append(item)
            return unique_values

        return value


class UpdateQuizProgressSerializer(serializers.Serializer):
    """
    Serializer para actualizar progreso del cuestionario

    Permite actualizar respuestas, progreso y preguntas marcadas
    sin necesidad de enviar todos los campos del quiz.
    """
    current_question = serializers.IntegerField(min_value=0)
    user_answers = serializers.DictField()
    is_completed = serializers.BooleanField(required=False)
    score = serializers.DictField(required=False)
    favorite_questions = serializers.ListField(
        child=serializers.IntegerField(min_value=0),
        required=False,
        allow_null=True,
        allow_empty=True,
        help_text="Lista actualizada de preguntas marcadas"
    )

    def validate_favorite_questions(self, value):
        """Valida y normaliza favorite_questions"""
        if value is None:
            return []

        # Remover duplicados
        if isinstance(value, list):
            return list(dict.fromkeys(value))  # Mantiene orden, elimina duplicados

        return value


# ============================================================================
# NUEVOS SERIALIZERS PARA EDICIÓN Y VALIDACIÓN ROBUSTA DE PREGUNTAS
# ============================================================================

class EditableQuestionSerializer(serializers.Serializer):
    """
    Serializer robusto para validar preguntas editadas por el usuario.

    Características de seguridad:
    - Validación exhaustiva de campos obligatorios
    - Prevención de injection attacks (HTML, JS, SQL)
    - Limitación de longitud de campos
    - Normalización de respuestas
    - Validación específica por tipo de pregunta
    """

    type = serializers.ChoiceField(
        choices=['mcq', 'vf', 'short'],
        required=True,
        error_messages={
            'required': 'El campo type es obligatorio',
            'invalid_choice': 'El tipo debe ser mcq, vf o short'
        }
    )

    question = serializers.CharField(
        required=True,
        min_length=10,
        max_length=500,
        allow_blank=False,
        trim_whitespace=True,
        error_messages={
            'required': 'El campo question es obligatorio',
            'blank': 'La pregunta no puede estar vacía',
            'min_length': 'La pregunta debe tener al menos 10 caracteres',
            'max_length': 'La pregunta no puede exceder 500 caracteres'
        }
    )

    options = serializers.ListField(
        child=serializers.CharField(max_length=200),
        required=False,
        allow_null=True,
        allow_empty=False,
        max_length=4,
        min_length=4
    )

    answer = serializers.CharField(
        required=True,
        max_length=500,
        allow_blank=False,
        trim_whitespace=True,
        error_messages={
            'required': 'El campo answer es obligatorio',
            'blank': 'La respuesta no puede estar vacía'
        }
    )

    explanation = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=300,
        trim_whitespace=True
    )

    # Campos de tracking (opcionales, del frontend)
    originalIndex = serializers.IntegerField(required=False, allow_null=True, min_value=-1)
    isModified = serializers.BooleanField(required=False, default=False)
    isNew = serializers.BooleanField(required=False, default=False)

    def validate_question(self, value):
        """
        Valida el enunciado previniendo injection attacks.

        Detecta y rechaza:
        - HTML/JavaScript injection
        - SQL injection patterns
        - Caracteres de control maliciosos
        """
        # Patrones peligrosos de HTML/Script injection
        dangerous_patterns = [
            r'<script[^>]*>.*?</script>',
            r'javascript:',
            r'on\w+\s*=',  # onclick, onerror, etc.
            r'<iframe',
            r'<object',
            r'<embed',
            r'data:text/html',
            r'<link',
            r'<style',
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                raise serializers.ValidationError(
                    "La pregunta contiene caracteres o patrones no permitidos por seguridad"
                )

        # Patrones básicos de SQL injection
        sql_patterns = [
            r"('\s*(or|and)\s*'?\d*'?\s*=\s*'?\d)",
            r"(union\s+select)",
            r"(drop\s+table)",
            r"(insert\s+into)",
            r"(delete\s+from)",
            r"(update\s+\w+\s+set)",
            r"(--\s*$)",  # SQL comments
            r"(/\*.*\*/)",  # SQL comments
        ]

        for pattern in sql_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                raise serializers.ValidationError(
                    "La pregunta contiene patrones no permitidos por seguridad"
                )

        # Detectar exceso de caracteres especiales consecutivos (posible ataque)
        if re.search(r'[\{\}\[\]<>]{5,}', value):
            raise serializers.ValidationError(
                "La pregunta contiene una secuencia sospechosa de caracteres especiales"
            )

        return value

    def validate_options(self, value):
        """
        Valida las opciones para preguntas MCQ.
        """
        if value is None:
            return value

        if not isinstance(value, list):
            raise serializers.ValidationError("Las opciones deben ser una lista")

        if len(value) != 4:
            raise serializers.ValidationError("Debe haber exactamente 4 opciones")

        # Validar que no haya opciones vacías
        for i, option in enumerate(value):
            if not option or not str(option).strip():
                raise serializers.ValidationError(
                    f"La opción {i+1} no puede estar vacía"
                )

        # Validar que no haya opciones duplicadas (case-insensitive)
        normalized = [str(opt).strip().lower() for opt in value]
        if len(set(normalized)) != len(normalized):
            raise serializers.ValidationError(
                "No puede haber opciones duplicadas"
            )

        return value

    def validate(self, data):
        """
        Validación a nivel de objeto completo.

        Asegura coherencia entre tipo de pregunta y campos.
        """
        qtype = data.get('type')
        options = data.get('options')
        answer = data.get('answer', '').strip()

        # Validación específica por tipo
        if qtype == 'mcq':
            # MCQ debe tener opciones
            if not options or len(options) != 4:
                raise serializers.ValidationError({
                    'options': 'Las preguntas de opción múltiple deben tener exactamente 4 opciones'
                })

            # La respuesta debe ser A, B, C o D
            answer_normalized = answer.upper().strip()[:1]
            if answer_normalized not in ('A', 'B', 'C', 'D'):
                raise serializers.ValidationError({
                    'answer': 'La respuesta debe ser A, B, C o D para preguntas de opción múltiple'
                })

            # Normalizar la respuesta
            data['answer'] = answer_normalized

        elif qtype == 'vf':
            # VF no debe tener opciones
            if options:
                data['options'] = None

            # La respuesta debe ser Verdadero o Falso
            answer_normalized = answer.strip().capitalize()
            if answer_normalized not in ('Verdadero', 'Falso'):
                raise serializers.ValidationError({
                    'answer': 'La respuesta debe ser Verdadero o Falso para preguntas verdadero/falso'
                })

            # Normalizar la respuesta
            data['answer'] = answer_normalized

        elif qtype == 'short':
            # Short no debe tener opciones
            if options:
                data['options'] = None

            # La respuesta debe ser texto no vacío
            if len(answer) < 1:
                raise serializers.ValidationError({
                    'answer': 'La respuesta para preguntas de respuesta corta no puede estar vacía'
                })

        return data


class SessionWithEditedQuestionsSerializer(serializers.Serializer):
    """
    Serializer para crear sesión con preguntas editadas opcionales.

    Soporta dos flujos:
    1. Generación automática: Solo configuración (topic, difficulty, etc)
    2. Confirmación con ediciones: Incluye array de questions editadas
    """

    topic = serializers.CharField(
        required=True,
        max_length=200,
        min_length=3,
        trim_whitespace=True
    )

    difficulty = serializers.ChoiceField(
        choices=['Fácil', 'Media', 'Difícil'],
        required=True
    )

    types = serializers.ListField(
        child=serializers.ChoiceField(choices=['mcq', 'vf', 'short']),
        required=True,
        min_length=1,
        max_length=3
    )

    counts = serializers.DictField(
        child=serializers.IntegerField(min_value=0, max_value=20),
        required=True
    )

    # Preguntas editadas (opcional - viene del frontend después de editar)
    questions = serializers.ListField(
        child=EditableQuestionSerializer(),
        required=False,
        allow_null=True,
        min_length=1,
        max_length=20
    )

    def validate_counts(self, value):
        """
        Valida que las cantidades sean coherentes.
        """
        # Verificar que sea un diccionario
        if not isinstance(value, dict):
            raise serializers.ValidationError("counts debe ser un diccionario")

        # Calcular total
        total = sum(int(v) for v in value.values() if isinstance(v, (int, float)))

        if total == 0:
            raise serializers.ValidationError("El total de preguntas debe ser mayor a 0")
        if total > 20:
            raise serializers.ValidationError("El total de preguntas no puede exceder 20")

        return value

    def validate(self, data):
        """
        Validación cruzada entre configuración y preguntas editadas.
        """
        types = data.get('types', [])
        counts = data.get('counts', {})
        questions = data.get('questions')

        # Validar que counts tenga claves para todos los types
        for t in types:
            if t not in counts:
                raise serializers.ValidationError({
                    'counts': f'Falta el count para el tipo {t}'
                })

        # Si hay preguntas editadas, validar coherencia
        if questions:
            actual_total = len(questions)

            # Validar cantidad mínima y máxima
            if actual_total < 1:
                raise serializers.ValidationError({
                    'questions': 'Debe haber al menos 1 pregunta'
                })

            if actual_total > 20:
                raise serializers.ValidationError({
                    'questions': 'No puede haber más de 20 preguntas'
                })

            # Contar preguntas por tipo para logging/métricas
            type_counts = {'mcq': 0, 'vf': 0, 'short': 0}
            for q in questions:
                qtype = q.get('type')
                if qtype in type_counts:
                    type_counts[qtype] += 1

            # Guardar en el contexto para uso posterior
            self.context['actual_type_counts'] = type_counts

        return data


def sanitize_question_data(question_dict):
    """
    Sanitiza datos de pregunta removiendo campos no esperados.

    Esta es una capa adicional de seguridad que:
    - Remueve campos no autorizados
    - Limita longitud de strings
    - Elimina caracteres de control
    - Normaliza tipos de datos

    Args:
        question_dict: Diccionario con datos de pregunta

    Returns:
        Diccionario sanitizado con solo campos válidos
    """
    # Campos permitidos
    allowed_fields = {
        'type', 'question', 'options', 'answer', 'explanation',
        'originalIndex', 'isModified', 'isNew'
    }

    # Crear nuevo dict solo con campos permitidos
    sanitized = {}

    for key in allowed_fields:
        if key in question_dict:
            value = question_dict[key]

            # Sanitizar strings
            if isinstance(value, str):
                # Remover caracteres de control (excepto newline)
                value = ''.join(
                    char for char in value
                    if ord(char) >= 32 or char in ('\n', '\t')
                )

                # Limitar longitud según el campo
                if key == 'question':
                    value = value[:500]
                elif key == 'answer':
                    value = value[:500]
                elif key == 'explanation':
                    value = value[:300]
                elif key == 'type':
                    value = value[:10]

            # Sanitizar listas (options)
            elif isinstance(value, list) and key == 'options':
                sanitized_options = []
                for opt in value[:4]:  # Máximo 4 opciones
                    if isinstance(opt, str):
                        opt_clean = ''.join(
                            char for char in opt
                            if ord(char) >= 32 or char in ('\n', '\t')
                        )
                        sanitized_options.append(opt_clean[:200])
                value = sanitized_options

            # Sanitizar booleanos
            elif key in ('isModified', 'isNew'):
                value = bool(value)

            # Sanitizar enteros
            elif key == 'originalIndex':
                try:
                    value = int(value)
                    # Limitar rango razonable
                    if value < -1 or value > 1000:
                        value = -1
                except (ValueError, TypeError):
                    value = -1

            sanitized[key] = value

    return sanitized


def validate_edited_questions_batch(questions_list):
    """
    Valida un batch completo de preguntas editadas.

    Args:
        questions_list: Lista de diccionarios con preguntas

    Returns:
        tuple: (is_valid, errors_list, sanitized_questions)

    Esta función:
    - Valida cada pregunta individualmente
    - Sanitiza los datos
    - Detecta duplicados
    - Retorna errores detallados
    """
    errors = []
    sanitized_questions = []

    # Validar cantidad
    if not isinstance(questions_list, list):
        return False, ['questions debe ser una lista'], []

    if len(questions_list) < 1:
        return False, ['Debe haber al menos 1 pregunta'], []

    if len(questions_list) > 20:
        return False, ['No puede haber más de 20 preguntas'], []

    # Set para detectar duplicados
    seen_questions = set()

    for i, q_dict in enumerate(questions_list):
        # Sanitizar primero
        sanitized = sanitize_question_data(q_dict)

        # Validar con serializer
        serializer = EditableQuestionSerializer(data=sanitized)

        if not serializer.is_valid():
            errors.append({
                'index': i,
                'errors': serializer.errors
            })
            continue

        # Detectar duplicados
        q_text = sanitized.get('question', '').strip().lower()
        if q_text in seen_questions:
            errors.append({
                'index': i,
                'errors': {'question': ['Pregunta duplicada']}
            })
            continue

        seen_questions.add(q_text)
        sanitized_questions.append(serializer.validated_data)

    is_valid = len(errors) == 0
    return is_valid, errors, sanitized_questions


class GeneratedImageSerializer(serializers.ModelSerializer):

    # Represent session as a small object so frontend can show topic without extra requests
    session = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = GeneratedImage
        fields = ['id', 'session', 'user', 'kind', 'image_url', 'created']

    def get_image_url(self, obj):
        # `image_rel` may be an ImageFieldFile instance (not a plain string).
        raw = getattr(obj, 'image_rel', '') or ''
        if hasattr(raw, 'name'):
            v = (raw.name or '').strip()
        else:
            v = (str(raw) or '').strip()

        if not v:
            return ''
        if v.startswith('http://') or v.startswith('https://'):
            return v
        req = self.context.get('request') if hasattr(self, 'context') else None
        if req:
            try:
                return req.build_absolute_uri(f"/api/media/proxy/{v.lstrip('/')}")
            except Exception:
                pass

        media_url = (getattr(settings, 'MEDIA_URL', '/') or '/')
        if not media_url.endswith('/'):
            media_url = media_url + '/'
        if v.startswith('/'):
            v = v.lstrip('/')
        return f"{media_url}{v}"

    def get_session(self, obj):
        s = getattr(obj, 'session', None)
        if not s:
            return None
        try:
            return {'id': str(s.id), 'topic': s.topic}
        except Exception:
            return {'id': str(getattr(s, 'id', '')), 'topic': ''}
