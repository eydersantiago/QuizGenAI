"""
Modelos para tracking de ediciones de preguntas.

Este módulo contiene modelos que rastrean el historial completo de ediciones
y operaciones realizadas sobre preguntas, permitiendo auditoría y análisis.
"""

import uuid
from django.db import models
from django.utils import timezone
from .models import GenerationSession

try:
    from django.db.models import JSONField
except ImportError:
    try:
        from django.contrib.postgres.fields import JSONField
    except ImportError:
        from django.db.models import TextField as JSONField


class QuestionEditLog(models.Model):
    """
    Registro de ediciones manuales de preguntas.

    Este modelo permite tracking completo de todas las ediciones que el usuario
    hace a las preguntas, distinguiendo entre:
    - Ediciones manuales del enunciado
    - Regeneraciones con IA
    - Duplicaciones
    - Nuevas preguntas agregadas

    Casos de uso:
    1. Usuario edita → log con operation_type='manual_edit'
    2. Usuario regenera → log con operation_type='ai_regeneration'
    3. Usuario duplica → log con operation_type='duplication'
    4. Usuario agrega nueva → log con operation_type='creation'

    Escenario complejo (editar → regenerar → editar):
    - Log 1: manual_edit (texto original → texto editado 1)
    - Log 2: ai_regeneration (texto editado 1 → pregunta IA)
    - Log 3: manual_edit (pregunta IA → texto editado 2)

    La secuencia se mantiene por created_at y question_index
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relación con la sesión
    session = models.ForeignKey(
        GenerationSession,
        on_delete=models.CASCADE,
        related_name="question_edits",
        help_text="Sesión a la que pertenece esta pregunta"
    )

    # Índice de la pregunta en el array
    question_index = models.PositiveIntegerField(
        help_text="Índice de la pregunta en el array latest_preview"
    )

    # Tipo de operación
    OPERATION_CHOICES = [
        ('manual_edit', 'Edición Manual'),
        ('ai_regeneration', 'Regeneración con IA'),
        ('duplication', 'Duplicación'),
        ('creation', 'Creación Nueva'),
    ]

    operation_type = models.CharField(
        max_length=20,
        choices=OPERATION_CHOICES,
        help_text="Tipo de operación realizada"
    )

    # Estado antes y después
    question_before = JSONField(
        null=True,
        blank=True,
        help_text="Estado de la pregunta antes de la operación"
    )

    question_after = JSONField(
        help_text="Estado de la pregunta después de la operación"
    )

    # Metadata de la operación
    changed_fields = JSONField(
        default=list,
        blank=True,
        help_text="Lista de campos que cambiaron (ej: ['question', 'explanation'])"
    )

    # Source de generación (para regeneraciones)
    ai_provider = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Proveedor de IA usado para regeneración (gemini/perplexity/local)"
    )

    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Momento en que se realizó la operación"
    )

    class Meta:
        db_table = "question_edit_log"
        ordering = ['session', 'question_index', 'created_at']
        indexes = [
            models.Index(fields=['session', 'question_index']),
            models.Index(fields=['session', 'created_at']),
            models.Index(fields=['operation_type']),
        ]

    def __str__(self):
        return f"{self.operation_type} - Q{self.question_index} - Session {self.session_id}"

    @classmethod
    def log_manual_edit(cls, session, index, before, after):
        """
        Helper para crear un log de edición manual.

        Args:
            session: GenerationSession instance
            index: índice de la pregunta
            before: dict con pregunta anterior
            after: dict con pregunta editada

        Returns:
            QuestionEditLog instance
        """
        # Detectar qué campos cambiaron
        changed = []
        for key in ['question', 'answer', 'options', 'explanation']:
            if before.get(key) != after.get(key):
                changed.append(key)

        return cls.objects.create(
            session=session,
            question_index=index,
            operation_type='manual_edit',
            question_before=before,
            question_after=after,
            changed_fields=changed
        )

    @classmethod
    def log_ai_regeneration(cls, session, index, before, after, provider='gemini'):
        """
        Helper para crear un log de regeneración con IA.

        Args:
            session: GenerationSession instance
            index: índice de la pregunta
            before: dict con pregunta anterior
            after: dict con pregunta regenerada
            provider: proveedor de IA usado

        Returns:
            QuestionEditLog instance
        """
        return cls.objects.create(
            session=session,
            question_index=index,
            operation_type='ai_regeneration',
            question_before=before,
            question_after=after,
            ai_provider=provider,
            changed_fields=['question', 'answer', 'options', 'explanation']
        )

    @classmethod
    def log_duplication(cls, session, original_index, new_index, question_data):
        """
        Helper para crear un log de duplicación.

        Args:
            session: GenerationSession instance
            original_index: índice de la pregunta original
            new_index: índice de la pregunta duplicada
            question_data: dict con datos de la pregunta duplicada

        Returns:
            QuestionEditLog instance
        """
        return cls.objects.create(
            session=session,
            question_index=new_index,
            operation_type='duplication',
            question_before=None,
            question_after=question_data,
            changed_fields=[]
        )

    @classmethod
    def log_creation(cls, session, index, question_data):
        """
        Helper para crear un log de pregunta nueva.

        Args:
            session: GenerationSession instance
            index: índice de la pregunta nueva
            question_data: dict con datos de la pregunta

        Returns:
            QuestionEditLog instance
        """
        return cls.objects.create(
            session=session,
            question_index=index,
            operation_type='creation',
            question_before=None,
            question_after=question_data,
            changed_fields=[]
        )

    def get_edit_summary(self):
        """
        Retorna un resumen legible de la edición.

        Returns:
            str: Resumen de la operación
        """
        if self.operation_type == 'manual_edit':
            fields_str = ', '.join(self.changed_fields)
            return f"Editados campos: {fields_str}"
        elif self.operation_type == 'ai_regeneration':
            return f"Regenerado con {self.ai_provider}"
        elif self.operation_type == 'duplication':
            return "Duplicado de otra pregunta"
        elif self.operation_type == 'creation':
            return "Pregunta nueva creada"
        return "Operación desconocida"


class QuestionOriginMetadata(models.Model):
    """
    Metadata sobre el origen de cada pregunta en una sesión.

    Este modelo complementa QuestionEditLog manteniendo el estado final
    de origen de cada pregunta (IA pura vs editada manualmente).

    Se actualiza cada vez que hay una operación sobre la pregunta.

    Útil para métricas rápidas sin tener que procesar todo el log.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    session = models.ForeignKey(
        GenerationSession,
        on_delete=models.CASCADE,
        related_name="question_metadata",
        help_text="Sesión a la que pertenece"
    )

    question_index = models.PositiveIntegerField(
        help_text="Índice de la pregunta"
    )

    # Origen final
    ORIGIN_CHOICES = [
        ('pure_ai', 'IA Pura (sin ediciones)'),
        ('ai_edited', 'IA con ediciones manuales'),
        ('user_created', 'Creada por usuario'),
        ('duplicated', 'Duplicada de otra'),
    ]

    origin_type = models.CharField(
        max_length=20,
        choices=ORIGIN_CHOICES,
        default='pure_ai',
        help_text="Tipo de origen final de la pregunta"
    )

    # Contador de operaciones
    edit_count = models.PositiveIntegerField(
        default=0,
        help_text="Número de ediciones manuales"
    )

    regeneration_count = models.PositiveIntegerField(
        default=0,
        help_text="Número de regeneraciones con IA"
    )

    # Proveedor original
    initial_ai_provider = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Proveedor que generó la pregunta inicialmente"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    last_modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "question_origin_metadata"
        unique_together = [['session', 'question_index']]
        indexes = [
            models.Index(fields=['session', 'question_index']),
            models.Index(fields=['origin_type']),
        ]

    def __str__(self):
        return f"Q{self.question_index} ({self.origin_type}) - Session {self.session_id}"

    def increment_edits(self):
        """Incrementa el contador de ediciones y actualiza origin_type."""
        self.edit_count += 1
        if self.origin_type == 'pure_ai':
            self.origin_type = 'ai_edited'
        self.save(update_fields=['edit_count', 'origin_type', 'last_modified_at'])

    def increment_regenerations(self):
        """Incrementa el contador de regeneraciones."""
        self.regeneration_count += 1
        self.save(update_fields=['regeneration_count', 'last_modified_at'])

    @classmethod
    def create_or_update_metadata(cls, session, index, operation_type, ai_provider=None):
        """
        Crea o actualiza metadata para una pregunta.

        Args:
            session: GenerationSession instance
            index: índice de la pregunta
            operation_type: tipo de operación realizada
            ai_provider: proveedor de IA (si aplica)

        Returns:
            QuestionOriginMetadata instance
        """
        metadata, created = cls.objects.get_or_create(
            session=session,
            question_index=index,
            defaults={
                'initial_ai_provider': ai_provider if operation_type == 'ai_regeneration' else None
            }
        )

        if operation_type == 'manual_edit':
            metadata.increment_edits()
        elif operation_type == 'ai_regeneration':
            metadata.increment_regenerations()
        elif operation_type == 'duplication':
            metadata.origin_type = 'duplicated'
            metadata.save(update_fields=['origin_type'])
        elif operation_type == 'creation':
            metadata.origin_type = 'user_created'
            metadata.save(update_fields=['origin_type'])

        return metadata

    def get_summary(self):
        """
        Retorna un resumen de la metadata.

        Returns:
            dict: Resumen de la metadata
        """
        return {
            'origin_type': self.origin_type,
            'edit_count': self.edit_count,
            'regeneration_count': self.regeneration_count,
            'total_operations': self.edit_count + self.regeneration_count,
            'initial_provider': self.initial_ai_provider,
        }
