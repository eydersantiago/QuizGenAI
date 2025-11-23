"""Create minimal GeneratedImage model to satisfy migration 0010.

This migration recreates a lightweight `GeneratedImage` model with the
fields and index names expected by migration `0010_rename_api_gene_user_created_generated_i_user_id_c6b153_idx_and_more`.

If the original `0009_generatedimage` contained more fields or different
behaviour, restore the original migration from version control instead
of this replacement.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0008_generationsession_image_counts'),
    ]

    operations = [
        migrations.CreateModel(
            name='GeneratedImage',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('image_rel', models.CharField(blank=True, help_text="Ruta relativa dentro de MEDIA_ROOT, p.ej. 'generated/x.png'", max_length=255)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'generated_image',
                'indexes': [
                    models.Index(fields=['user', 'created'], name='api_gene_user_created'),
                    models.Index(fields=['image_rel'], name='api_gene_image_rel'),
                ],
            },
        ),
    ]
