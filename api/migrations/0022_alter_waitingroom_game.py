# Generated by Django 4.2.1 on 2023-12-09 20:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0021_remove_findingwordsactivegame_answers_count_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='waitingroom',
            name='game',
            field=models.TextField(choices=[('race', 'Race'), ('findingwords', 'Finding Words')]),
        ),
    ]
