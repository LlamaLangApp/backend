from dataclasses import dataclass
from typing import List
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.auth.models import User
from django.db.models import F


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
    user = models.ForeignKey("auth.User", on_delete=models.DO_NOTHING, null=False)
    wordset = models.ForeignKey(WordSet, on_delete=models.DO_NOTHING, null=False)
    score = models.IntegerField(validators=[MinValueValidator(0)])
    accuracy = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    duration = models.IntegerField(validators=[MinValueValidator(0)])  # in seconds
    timestamp = models.DateTimeField(auto_now_add=False)


class MultiplayerGames(models.TextChoices):
    RACE = "RACE", "Race"


class WaitingRoom(models.Model):
    game = models.TextField(choices=MultiplayerGames.choices)
    users = models.ManyToManyField("auth.User", blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def add_user(self, user):
        self.users.add(user)
        self.save()

    def remove_user(self, user):
        self.users.remove(user)
        self.save()

    def is_full(self):
        return self.users.count() == 2

    @classmethod
    def get_waiting_room_by_game(cls, game):
        try:
            return cls.objects.get(game=game)
        except cls.DoesNotExist:
            return None


@dataclass
class RaceRound:
    options: List[str]
    answer: str
    question: str


class GamePlayer(models.Model):
    score = models.IntegerField(default=0)
    user = models.ForeignKey("auth.User", on_delete=models.DO_NOTHING, null=False)

    def get_username(self):
        return self.user.username

    def add_points(self, points_to_add=15):
        self.score = F('score') + points_to_add
        self.save()


class RaceActiveGame(models.Model):
    players = models.ManyToManyField(GamePlayer, related_name='race_active_games')
    answers_count = models.IntegerField(default=0)
    round_count = models.IntegerField(default=0)
    # Contains an array of `RaceRound``
    rounds = models.JSONField()

    def add_player_to_active_game(self, player):
        self.players.add(player)
        self.save()

    def add_round(self):
        self.round_count = F('round_count') + 1
        self.save()

    def add_answer(self):
        self.answers_count = F('answers_count') + 1
        self.save()

    def reset_answers_count(self):
        self.answers_count = 0
        self.save()

    # def remove_player_from_active_game(self, player):
    #     self.players.remove(player)

    # def increment_round_count(self):
    #     self.round_count += 1
    #     self.save()