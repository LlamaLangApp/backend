# Generated by Django 4.2.1 on 2023-10-08 17:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0015_wordsetuseraccuracy_unlocked"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customuser",
            name="avatar",
            field=models.ImageField(
                blank=True,
                default="defaults/default_avatar.png",
                null=True,
                upload_to="avatars",
            ),
        ),
    ]
