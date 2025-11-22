from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0008_generationsession_cover_image_history_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ImagePromptCache',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user_identifier', models.CharField(db_index=True, max_length=255)),
                ('prompt', models.TextField()),
                ('prompt_hash', models.CharField(db_index=True, max_length=64)),
                ('image_path', models.CharField(max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='prompt_caches', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'image_prompt_cache',
                'unique_together': {('user_identifier', 'prompt_hash')},
                'indexes': [models.Index(fields=['user_identifier', 'prompt_hash', 'expires_at'])],
            },
        ),
        migrations.CreateModel(
            name='ImageGenerationLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user_identifier', models.CharField(db_index=True, max_length=255)),
                ('prompt', models.TextField()),
                ('provider', models.CharField(default='unknown', max_length=50)),
                ('image_path', models.CharField(blank=True, default='', max_length=500)),
                ('reused_from_cache', models.BooleanField(default=False)),
                ('estimated_cost_usd', models.DecimalField(blank=True, decimal_places=4, max_digits=8, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='image_generations', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'image_generation_log',
                'indexes': [
                    models.Index(fields=['user_identifier', 'created_at']),
                    models.Index(fields=['provider', 'created_at']),
                    models.Index(fields=['reused_from_cache', 'created_at']),
                ],
            },
        ),
    ]
