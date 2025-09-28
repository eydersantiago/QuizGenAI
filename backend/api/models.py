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