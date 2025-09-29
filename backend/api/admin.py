# api/admin.py
from django.contrib import admin
from .models import GenerationSession, RegenerationLog

@admin.register(GenerationSession)
class GenerationSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "topic", "difficulty", "created_at")
    search_fields = ("id", "topic", "category")
    readonly_fields = ("created_at",)

@admin.register(RegenerationLog)
class RegenerationLogAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "index", "created_at")
    search_fields = ("session__id",)
    readonly_fields = ("created_at",)
