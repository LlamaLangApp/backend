# Generated by Django 4.2.1 on 2023-09-30 16:55

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0012_alter_translationuseraccuracycounter_accuracy'),
    ]

    operations = [
        migrations.AlterField(
            model_name='translationuseraccuracycounter',
            name='accuracy',
            field=models.FloatField(default=0.0, validators=[django.core.validators.MinValueValidator(0.0), django.core.validators.MaxValueValidator(1.0)]),
        ),
    ]
