import uuid
from django.db import models
from django.contrib.postgres.fields import ArrayField  # si usas Postgres
from django.core.validators import MinValueValidator, MaxValueValidator

try:
    from django.db.models import JSONField  # Django 3.1+ (alias)
except ImportError:
    from django.contrib.postgres.fields import JSONField  # fallback

DIFFICULTY_CHOICES = (
    ("Fácil", "Fácil"),
    ("Media", "Media"),
    ("Difícil", "Difícil"),
)

class GenerationSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    topic = models.CharField(max_length=200)
    category = models.CharField(max_length=100, blank=True)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES)
    types = models.JSONField(default=list)   # ["mcq","vf","short"]
    counts = models.JSONField(default=dict)  # {"mcq":5,"vf":2,"short":3}
    created_at = models.DateTimeField(auto_now_add=True)

    # Último preview generado para esta sesión (persistimos para HU-05)
    latest_preview = JSONField(default=list, blank=True)


    class Meta:
        db_table = "generation_session"

    def __str__(self):
        return f"{self.id} - {self.topic} ({self.difficulty})"

class RegenerationLog(models.Model):
    """
    Traza cada regeneración:
    - session: sesión propietaria
    - index: índice de la pregunta regenerada (según el preview vigente)
    - old_question/new_question: versión anterior y la variante generada
    """
    id = models.BigAutoField(primary_key=True)
    session = models.ForeignKey(GenerationSession, on_delete=models.CASCADE, related_name="regens")
    index = models.PositiveIntegerField(validators=[MinValueValidator(0), MaxValueValidator(999)])
    old_question = JSONField()
    new_question = JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "regeneration_log"
        indexes = [
            models.Index(fields=["session", "index"]),
        ]

    def __str__(self):
        return f"regen[{self.session_id}] idx={self.index} at {self.created_at}"


class SavedQuiz(models.Model):
    """
    Cuestionarios guardados por el usuario para continuar más tarde.
    Almacena el estado completo del cuestionario y su configuración.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200, help_text="Título personalizado del cuestionario guardado")
    topic = models.CharField(max_length=200)
    category = models.CharField(max_length=100, blank=True)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES)
    
    # Configuración original
    types = models.JSONField(default=list, help_text="Tipos de pregunta habilitados")
    counts = models.JSONField(default=dict, help_text="Cantidad por tipo de pregunta")
    
    # Estado del cuestionario
    questions = JSONField(default=list, help_text="Preguntas generadas del cuestionario")
    user_answers = JSONField(default=dict, help_text="Respuestas del usuario {index: respuesta}")
    current_question = models.PositiveIntegerField(default=0, help_text="Índice de la pregunta actual")
    is_completed = models.BooleanField(default=False, help_text="Si el cuestionario fue completado")
    score = models.JSONField(default=dict, blank=True, help_text="Puntaje y detalles de evaluación")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_accessed = models.DateTimeField(auto_now=True, help_text="Última vez que se accedió al cuestionario")

    class Meta:
        db_table = "saved_quiz"
        ordering = ['-last_accessed', '-updated_at']
        indexes = [
            models.Index(fields=['topic', 'difficulty']),
            models.Index(fields=['created_at']),
            models.Index(fields=['last_accessed']),
            models.Index(fields=['is_completed']),
        ]

    def __str__(self):
        status = "Completado" if self.is_completed else f"Pregunta {self.current_question + 1}/{len(self.questions)}"
        return f"{self.title} - {self.topic} ({self.difficulty}) - {status}"

    def get_progress_percentage(self):
        """Retorna el porcentaje de progreso del cuestionario"""
        if not self.questions:
            return 0
        if self.is_completed:
            return 100
        return int((self.current_question / len(self.questions)) * 100)

    def get_answered_count(self):
        """Retorna la cantidad de preguntas respondidas"""
        return len(self.user_answers) if isinstance(self.user_answers, dict) else 0

from django.contrib.postgres.fields import JSONField  # if using Postgres, else use TextField

class GenerationSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    topic = models.CharField(max_length=200)
    category = models.CharField(max_length=100, blank=True)  # assigned taxonomy category
    difficulty = models.CharField(max_length=20)
    types = models.JSONField(default=list)  # e.g. ["mcq","vf","short"]
    counts = models.JSONField(default=dict) # e.g. {"mcq":5,"vf":2,"short":3}
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.id} - {self.topic} ({self.difficulty})"
