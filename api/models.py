from dataclasses import asdict, dataclass
import json
from typing import List
from django.db import models, transaction
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.auth.models import AbstractUser
from django.db.models import F
from api.consumers.helpers import FindingWordsRound, get_finding_words_rounds, get_race_rounds, get_words_for_play
from api.consumers.updates_consumer import send_waitroom_invitations_cancelation
from api.helpers import get_score_goal_for_level
from backend import settings


UNLOCK_WORDSET_THRESHOLD = 1000


class Translation(models.Model):
    english = models.CharField(max_length=64)
    polish = models.CharField(max_length=64)
    starred_by = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='favorite_translations', blank=True)

    def __str__(self) -> str:
        return self.english

    def get_starred_by_user(self, user):
        self.refresh_from_db()
        return self.starred_by.filter(id=user.id).exists()


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
        total_points = 0
        for game_name, session_model in GAME_NAMES_MODELS_MAPPING.items():
            game_sessions = session_model.objects.filter(user=user, wordset=self)
            for session in game_sessions:
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


GAME_NAMES_MODELS_MAPPING = {
    "finding_words": FindingWordsGameSession,
    "memory": MemoryGameSession,
    "falling_words": FallingWordsGameSession,
    "race": RaceGameSession,

}


class MultiplayerGames(models.TextChoices):
    RACE = "race"
    FINDING_WORDS = "findingwords"


class WaitingRoom(models.Model):
    game = models.TextField(choices=MultiplayerGames.choices)
    wordset = models.ForeignKey(WordSet, on_delete=models.CASCADE)
    users = models.ManyToManyField("CustomUser", related_name="in_waiting_room", blank=True)
    owner = models.ForeignKey("Customuser", null=True, related_name="owns_waiting_room", on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)

    invited_players = models.ManyToManyField("CustomUser", related_name="invited_to")
    
    @classmethod
    def get_waiting_room_by_game_and_wordset(cls, game, wordset):
        try:
            return cls.objects.get(game=game, wordset=wordset)
        except cls.DoesNotExist:
            return None
        
    def delete(self, *args, **kwargs):
        send_waitroom_invitations_cancelation(self)
        super().delete(*args, **kwargs)

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

class ActiveMultiplayerGame(models.Model):
    wordset = models.ForeignKey(WordSet, on_delete=models.DO_NOTHING, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    players = models.ManyToManyField(GamePlayer, related_name='active_games', blank=True)
    required_answers = models.IntegerField()
    answers_in_current_round = models.IntegerField(default=0)
    round_count = models.IntegerField(default=0)
    total_round_count = models.IntegerField()

    def add_player(self, player: CustomUser):
        self.players.add(player)
        self.save()

    def mark_player_answer(self):
        self.refresh_from_db()
        self.answers_in_current_round = F('answers_in_current_round') + 1
        self.save()

    def have_all_players_answered(self) -> int:
        self.refresh_from_db()
        return self.answers_in_current_round == self.required_answers

    def progress_round(self):
        self.round_count = F('round_count') + 1
        self.answers_in_current_round = 0
        self.save()
    
    def all_rounds_played(self) -> bool:
        self.refresh_from_db()
        return self.round_count >= self.total_round_count


class RaceActiveGame(ActiveMultiplayerGame):
    # Contains an array of `RaceRound` objects
    rounds = models.JSONField()

    @staticmethod
    def create_session_from_waiting_room(waitroom: WaitingRoom) -> "RaceActiveGame":
        words = get_words_for_play(waitroom.wordset)
        race_rounds = get_race_rounds(words)
        game_session = RaceActiveGame.objects.create(
            rounds=json.dumps([asdict(r) for r in race_rounds]),
            required_answers=waitroom.users.count(),
            wordset=waitroom.wordset,
            total_round_count=len(race_rounds),
        )
        for player in waitroom.users.all():
            game_session.players.create(user=player)
        game_session.save()
        return game_session

class FindingWordsActiveGame(ActiveMultiplayerGame):
    # Contains an array of `FindingWordsRound` objects
    rounds = models.JSONField()

    @staticmethod
    def create_session_from_waiting_room(waitroom: WaitingRoom) -> "FindingWordsActiveGame":
        words = get_words_for_play(waitroom.wordset)
        rounds = get_finding_words_rounds([word['english'] for word in words], 3)
        game_session = FindingWordsActiveGame.objects.create(
            rounds=json.dumps([asdict(r) for r in rounds]),
            required_answers=waitroom.users.count(),
            wordset=waitroom.wordset,
            total_round_count=len(rounds),
        )
        for player in waitroom.users.all():
            game_session.players.create(user=player)
        game_session.save()
        return game_session
    
    def is_answer_valid_for_round(self, answer: str, round: int) -> bool:
        round: FindingWordsRound = json.loads(self.rounds)[round]

        valid_answer = answer and all([letter in round["letters"] for letter in answer])
        correct_answer = self.wordset.words.all().filter(english=answer).values("id").first()
        return valid_answer and correct_answer

class FriendRequest(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_friend_requests')
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name='received_friend_requests')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['sender', 'receiver']


class Friendship(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='friend')
    friend = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='friend_of')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'friend']
