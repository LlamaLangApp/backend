from dataclasses import dataclass
from typing import List
from django.db import models, transaction
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.auth.models import User, AbstractUser
from django.db.models import F

from api.helpers import get_score_goal_for_level
from backend import settings


UNLOCK_WORDSET_THRESHOLD = 1000


class Translation(models.Model):
    english = models.CharField(max_length=64)
    polish = models.CharField(max_length=64)
    starred_by = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='favorite_translations', blank=True)

    def __str__(self) -> str:
        return self.english


class WordSetCategory(models.TextChoices):
    FOOD = "food", "Food"
    ANIMALS = "animals", "Animals"
    CLOTHES = "clothes", "Clothes"
    HOUSE = "house", "House"
    GENERAL = "general", "General"
    VACATIONS = "vacations", "Vacations"


class WordSet(models.Model):
    english = models.TextField()
    polish = models.TextField()
    category = models.CharField(max_length=64, choices=WordSetCategory.choices, default="General")
    difficulty = models.PositiveIntegerField(default=1)
    words = models.ManyToManyField(Translation)

    def __str__(self) -> str:
        return self.english

    def get_easier_wordsets_from_category(self):
        wordsets = WordSet.objects.filter(category=self.category, difficulty__lt=self.difficulty)
        return list(wordsets)

    def get_total_points_for_user(self, user):
        memory_sessions = MemoryGameSession.objects.filter(user=user, wordset=self)
        falling_words_sessions = FallingWordsGameSession.objects.filter(user=user, wordset=self)
        race_sessions = RaceGameSession.objects.filter(user=user, wordset=self)
        finding_words_sessions = FindingWordsGameSession.objects.filter(user=user, wordset=self)

        total_points = 0

        for session in memory_sessions:
            total_points += session.score
        for session in falling_words_sessions:
            total_points += session.score
        for session in race_sessions:
            total_points += session.score
        for session in finding_words_sessions:
            total_points += session.score

        return total_points

    def is_locked_for_user(self, user):
        easier_wordsets = list(self.get_easier_wordsets_from_category())
        for wordset in easier_wordsets:
            if wordset.get_total_points_for_user(user) < UNLOCK_WORDSET_THRESHOLD:
                return True
        return False


class ScoreHistory(models.Model):
    user = models.ForeignKey("CustomUser", on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now_add=True)
    game_name = models.CharField(max_length=20, default="")
    score_gained = models.PositiveIntegerField()


class CustomUser(AbstractUser):
    score = models.PositiveIntegerField(default=0)
    level = models.PositiveIntegerField(blank=False, default=1)
    avatar = models.ImageField(upload_to='avatars', null=True, blank=True, default='defaults/default_avatar.png')
    llama = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])

    def calculate_level(self):
        if self.score >= get_score_goal_for_level(self.level + 1):
            self.level = self.level + 1
        self.save()

    def get_points_to_next_level(self):
        return get_score_goal_for_level(self.level + 1) - self.score

    def add_score(self, score, game_name):
        with transaction.atomic():
            self.score = self.score + score
            self.save()
            self.calculate_level()
            print(f"User {self.username} gained {score} points in {game_name} game")
            ScoreHistory.objects.create(user=self, score_gained=score, game_name=game_name)


# Game Sessions
class BaseGameSession(models.Model):
    GAME_CHOICES = [
        ('memory', 'Memory'),
        ('falling_words', 'Falling Words'),
        ('finding_words', 'Finding Words'),
        ('race', 'Race'),
    ]

    user = models.ForeignKey("CustomUser", on_delete=models.DO_NOTHING, null=False)
    wordset = models.ForeignKey(WordSet, on_delete=models.DO_NOTHING, null=False)
    score = models.IntegerField(validators=[MinValueValidator(0)])
    duration = models.IntegerField(validators=[MinValueValidator(0)], default=0)  # in seconds
    timestamp = models.DateTimeField(auto_now_add=False)
    game_name = models.CharField(max_length=20, choices=GAME_CHOICES, default='memory')

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.user.add_score(self.score, self.game_name)
        self.timestamp = self.user.scorehistory_set.last().date
        super(BaseGameSession, self).save(*args, **kwargs)


class MemoryGameSession(BaseGameSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game_name = 'memory'

    def save(self, *args, **kwargs):
        super(MemoryGameSession, self).save(*args, **kwargs)


class FallingWordsGameSession(BaseGameSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game_name = 'falling_words'

    def save(self, *args, **kwargs):
        super(FallingWordsGameSession, self).save(*args, **kwargs)


class RaceGameSession(BaseGameSession):
    opponents = models.ManyToManyField("CustomUser", related_name="race_game_sessions", blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game_name = 'race'


class FindingWordsGameSession(BaseGameSession):
    opponents = models.ManyToManyField("CustomUser", related_name="finding_words_game_sessions", blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game_name = 'finding_words'

    def save(self, *args, **kwargs):
        super(FindingWordsGameSession, self).save(*args, **kwargs)


class MultiplayerGames(models.TextChoices):
    RACE = "race", "Race"


class WaitingRoom(models.Model):
    game = models.TextField(choices=MultiplayerGames.choices)
    wordset = models.ForeignKey(WordSet, on_delete=models.CASCADE)
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
    def get_waiting_room_by_game_and_wordset(cls, game, wordset):
        try:
            return cls.objects.get(game=game, wordset=wordset)
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
        self.score += points_to_add
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
            super(RaceActiveGame, self).delete(*args, **kwargs)


class FindingWordsActiveGame(models.Model):
    players = models.ManyToManyField(GamePlayer, related_name='finding_Words_active_games', blank=True)
    # Answers so far in the current round
    answers_count = models.IntegerField(default=0)
    round_count = models.IntegerField(default=0)
    wordset = models.ForeignKey(WordSet, on_delete=models.DO_NOTHING, null=True)
    # Contains an array of `FindingWordsRound` objects
    rounds = models.JSONField()

    def add_player_to_active_game(self, player):
        self.players.add(player)
        self.save()

    def move_to_next_round(self):
        self.answers_count = 0
        self.round_count = F('round_count') + 1
        self.save()

    def record_answer(self):
        self.answers_count = F('answers_count') + 1
        self.save()

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            super(FindingWordsActiveGame, self).delete(*args, **kwargs)


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
