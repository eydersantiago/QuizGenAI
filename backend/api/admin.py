# api/admin.py
from django.contrib import admin
from .models import GenerationSession, RegenerationLog, ImagePromptCache, ImageGenerationLog

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


@admin.register(ImagePromptCache)
class ImagePromptCacheAdmin(admin.ModelAdmin):
    list_display = ("user_identifier", "prompt", "image_path", "expires_at", "created_at")
    search_fields = ("prompt", "user_identifier")
    list_filter = ("expires_at",)
    readonly_fields = ("created_at",)


@admin.register(ImageGenerationLog)
class ImageGenerationLogAdmin(admin.ModelAdmin):
    list_display = ("user_identifier", "provider", "reused_from_cache", "image_path", "created_at")
    search_fields = ("prompt", "user_identifier", "provider")
    list_filter = ("provider", "reused_from_cache", "created_at")
    readonly_fields = ("created_at",)
