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

    class Meta:
        model = SavedQuiz
        fields = [
            'id', 'title', 'topic', 'category', 'difficulty',
            'types', 'counts', 'questions', 'user_answers',
            'current_question', 'is_completed', 'score',
            'created_at', 'updated_at', 'last_accessed',
            'progress_percentage', 'answered_count', 'total_questions'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_total_questions(self, obj):
        return len(obj.questions) if obj.questions else 0


class SavedQuizListSerializer(serializers.ModelSerializer):
    """Serializer simplificado para listado"""
    progress_percentage = serializers.ReadOnlyField(source='get_progress_percentage')
    answered_count = serializers.ReadOnlyField(source='get_answered_count')
    total_questions = serializers.SerializerMethodField()

    class Meta:
        model = SavedQuiz
        fields = [
            'id', 'title', 'topic', 'category', 'difficulty',
            'is_completed', 'created_at', 'updated_at', 'last_accessed',
            'progress_percentage', 'answered_count', 'total_questions'
        ]

    def get_total_questions(self, obj):
        return len(obj.questions) if obj.questions else 0


class SaveQuizRequestSerializer(serializers.Serializer):
    """Serializer para requests de guardado de cuestionario"""
    title = serializers.CharField(max_length=200)
    session_id = serializers.CharField(required=False, allow_blank=True)
    topic = serializers.CharField(max_length=200, required=False)
    difficulty = serializers.ChoiceField(choices=DIFFICULTY_CHOICES, required=False)
    types = serializers.ListField(child=serializers.CharField(), required=False)
    counts = serializers.DictField(required=False)
    questions = serializers.ListField(child=serializers.DictField(), required=False)
    user_answers = serializers.DictField(required=False)
    current_question = serializers.IntegerField(min_value=0, required=False)


class UpdateQuizProgressSerializer(serializers.Serializer):
    """Serializer para actualizar progreso del cuestionario"""
    current_question = serializers.IntegerField(min_value=0)
    user_answers = serializers.DictField()
    is_completed = serializers.BooleanField(required=False)
    score = serializers.DictField(required=False)
