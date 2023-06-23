from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
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

class MemoryGameSession(models.Model):
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, null=False)
    wordset = models.ForeignKey(WordSet, on_delete= models.DO_NOTHING, null=False)
    score = models.IntegerField(validators=[MinValueValidator(0)])
    accuracy = models.FloatField(validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    duration = models.IntegerField(validators=[MinValueValidator(0)]) # in seconds
    timestamp = models.DateTimeField(auto_now_add=False)
