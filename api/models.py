from dataclasses import dataclass
from typing import List
from django.db import models, transaction
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.auth.models import User, AbstractUser
from django.db.models import F

from backend import settings

POINTS_PER_LEVEL = 100


class Translation(models.Model):
    english = models.CharField(max_length=64)
    polish = models.CharField(max_length=64)
    starred_by = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='favorite_translations', blank=True)

    def __str__(self) -> str:
        return self.english


class AnswerCounter(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    translation = models.ForeignKey(Translation, on_delete=models.CASCADE)
    good_answers_counter = models.PositiveIntegerField(default=0)

    @classmethod
    def increment_good_answer(cls, user, translation_id):
        try:
            answer_counter = cls.objects.get(translation_id=translation_id, user=user)
            answer_counter.good_answers_counter += 1
            answer_counter.save()
        except cls.DoesNotExist:
            cls.objects.create(translation_id=translation_id, user=user, good_answers_counter=1)

    @classmethod
    def decrement_good_answer(cls, user, translation_id):
        try:
            answer_counter = cls.objects.get(translation_id=translation_id, user=user)
            if answer_counter.good_answers_counter > 0:
                answer_counter.good_answers_counter -= 1
            answer_counter.save()
        except cls.DoesNotExist:
            cls.objects.create(translation_id=translation_id, user=user, good_answers_counter=0)


class WordSet(models.Model):
    english = models.TextField()
    polish = models.TextField()

    words = models.ManyToManyField(Translation)

    def __str__(self) -> str:
        return self.english


class ScoreHistory(models.Model):
    user = models.ForeignKey("CustomUser", on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now_add=True)
    game_name = models.CharField(max_length=20, default="")
    score_gained = models.PositiveIntegerField()


class CustomUser(AbstractUser):
    score = models.PositiveIntegerField(default=0)
    level = models.PositiveIntegerField(blank=False, default=1)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True, default='avatars/default_avatar.png')

    def calculate_level(self):
        self.level = self.score // POINTS_PER_LEVEL + 1
        self.save()

    def add_score(self, score, game_name):
        with transaction.atomic():
            self.score = self.score + score
            self.save()
            self.calculate_level()

            ScoreHistory.objects.create(user=self, score_gained=score, game_name=game_name)


# Game Sessions
class BaseGameSession(models.Model):
    GAME_CHOICES = [
        ('memory', 'Memory'),
        ('falling_words', 'Falling Words'),
        ('race', 'Race'),
    ]

    user = models.ForeignKey("CustomUser", on_delete=models.DO_NOTHING, null=False)
    wordset = models.ForeignKey(WordSet, on_delete=models.DO_NOTHING, null=False)
    score = models.IntegerField(validators=[MinValueValidator(0)])
    duration = models.IntegerField(validators=[MinValueValidator(0)], default=0)  # in seconds
    accuracy = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    timestamp = models.DateTimeField(auto_now_add=False)
    game_name = models.CharField(max_length=20, choices=GAME_CHOICES, default='memory')  # Default to 'memory'

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.user.add_score(self.score, self.game_name)
        #add timestamp
        self.timestamp = self.user.scorehistory_set.last().date
        super(BaseGameSession, self).save(*args, **kwargs)


class MemoryGameSession(BaseGameSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game_name = 'memory'


class FallingWordsGameSession(BaseGameSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game_name = 'falling_words'


class RaceGameSession(BaseGameSession):
    opponents = models.ManyToManyField("CustomUser", related_name="race_game_sessions", blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game_name = 'race'


class MultiplayerGames(models.TextChoices):
    RACE = "RACE", "Race"


class WaitingRoom(models.Model):
    game = models.TextField(choices=MultiplayerGames.choices)
    users = models.ManyToManyField("CustomUser", blank=True)
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
    answer_id: int
    question: str


class GamePlayer(models.Model):
    score = models.IntegerField(default=0)
    user = models.ForeignKey("CustomUser", on_delete=models.DO_NOTHING, null=False)
    good_answers = models.IntegerField(default=0)

    def get_username(self):
        return self.user.username

    def add_points(self, points_to_add=15):
        self.score = F('score') + points_to_add
        self.save()

    def add_good_answer(self):
        self.good_answers = F('good_answers') + 1
        self.save()


class RaceActiveGame(models.Model):
    players = models.ManyToManyField(GamePlayer, related_name='race_active_games', blank=True)
    answers_count = models.IntegerField(default=0)
    round_count = models.IntegerField(default=0)
    wordset = models.ForeignKey(WordSet, on_delete=models.DO_NOTHING, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    # Contains an array of `RaceRound` objects
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

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            for player in self.players.all():
                # player.user.add_score(player.score)
                player.delete()
            super(RaceActiveGame, self).delete(*args, **kwargs)


class FriendRequest(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_friend_requests')
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_friend_requests')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['sender', 'receiver']


class Friendship(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='friend')
    friend = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='friend_of')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'friend']
