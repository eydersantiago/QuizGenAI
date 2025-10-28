# api/serializers.py
from rest_framework import serializers
from .models import SavedQuiz, GenerationSession

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

    class Meta:
        model = SavedQuiz
        fields = [
            'id', 'title', 'topic', 'category', 'difficulty',
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
            'is_completed', 'created_at', 'updated_at', 'last_accessed',
            'progress_percentage', 'answered_count', 'total_questions',
            'favorite_questions',  # Lista completa de índices marcados
            'marked_count',  # Conteo rápido para UI
            'is_review',  # Indica si es un quiz de repaso
            'original_quiz_info'  # Info del quiz original si es repaso
        ]

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
