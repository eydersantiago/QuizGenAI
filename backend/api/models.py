import uuid
from django.db import models

class GenerationSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    topic = models.CharField(max_length=200)
    category = models.CharField(max_length=100, blank=True)
    difficulty = models.CharField(max_length=20)
    types = models.JSONField(default=list)   # ["mcq","vf","short"]
    counts = models.JSONField(default=dict)  # {"mcq":5,"vf":2,"short":3}
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.id} - {self.topic} ({self.difficulty})"
