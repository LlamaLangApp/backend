# Generated by Django 4.2.1 on 2023-09-23 08:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0004_customuser_avatar'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customuser',
            name='avatar',
            field=models.BinaryField(null=True),
        ),
    ]
