# Generated by Django 4.2.1 on 2023-07-10 18:57

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("api", "0003_waitingroom_memorygamesession"),
    ]

    operations = [
        migrations.CreateModel(
            name="RaceActiveGame",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("answers_count", models.IntegerField(default=0)),
                ("round_count", models.IntegerField(default=0)),
                ("rounds", models.JSONField()),
                ("users", models.ManyToManyField(to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]