# Generated by Django 4.2.1 on 2023-10-15 07:40

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0016_alter_customuser_avatar'),
    ]

    operations = [
        migrations.AddField(
            model_name='waitingroom',
            name='wordset',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to='api.wordset'),
            preserve_default=False,
        ),
    ]
