from django.db import models

class Translation(models.Model):
    english = models.CharField(max_length=64)
    polish = models.CharField(max_length=64)

    def __str__(self) -> str:
        return self.english

class WordSet(models.Model):
    english = models.TextField()
    polish = models.TextField()

    words = models.ManyToManyField(Translation)

    def __str__(self) -> str:
        return self.english