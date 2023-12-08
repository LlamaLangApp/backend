from dataclasses import asdict, dataclass
import json
from typing import List
from django.db import models, transaction
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.auth.models import AbstractUser
from django.db.models import F, Avg
from api.consumers.helpers import FindingWordsRound, get_finding_words_rounds, get_race_rounds, get_words_for_play
from api.helpers import get_score_goal_for_level
from backend import settings


class Translation(models.Model):
    english = models.CharField(max_length=64)
    polish = models.CharField(max_length=64)
    starred_by = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='favorite_translations', blank=True)

    def __str__(self) -> str:
        return self.english


class TranslationUserAccuracyCounter(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    translation = models.ForeignKey(Translation, on_delete=models.CASCADE)
    good_answers_counter = models.PositiveIntegerField(default=0)
    bad_answers_counter = models.PositiveIntegerField(default=0)
    accuracy = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])

    def calculate_accuracy(self):
        if self.good_answers_counter + self.bad_answers_counter == 0:
            self.accuracy = 0.0
        else:
            self.accuracy = round(self.good_answers_counter / (self.good_answers_counter + self.bad_answers_counter), 2)

    @classmethod
    def increment_good_answer(cls, user, translation_id):
        try:
            answer_counter = cls.objects.get(translation_id=translation_id, user=user)
            answer_counter.good_answers_counter += 1
            answer_counter.calculate_accuracy()
            answer_counter.save()
        except cls.DoesNotExist:
            cls.objects.create(translation_id=translation_id, user=user, good_answers_counter=1, bad_answers_counter=0,
                               accuracy=100.0)

    @classmethod
    def increment_bad_answer(cls, user, translation_id):
        try:
            answer_counter = cls.objects.get(translation_id=translation_id, user=user)
            answer_counter.bad_answers_counter += 1
            answer_counter.calculate_accuracy()
            answer_counter.save()
        except cls.DoesNotExist:
            cls.objects.create(translation_id=translation_id, user=user, good_answers_counter=0, bad_answers_counter=1,
                               accuracy=0.0)


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

    def calculate_average_accuracy(self, user):
        translations = self.words.all()
        user_accuracies = TranslationUserAccuracyCounter.objects.filter(translation__in=translations, user=user)
        avg_accuracy = user_accuracies.aggregate(Avg("accuracy"))["accuracy__avg"]

        if avg_accuracy is not None:
            return round(avg_accuracy, 2)
        else:
            return 0.0

    def are_all_words_revised_at_least_x_times(self, user, min_revisions=5):
        translations = self.words.all()
        user_accuracies = TranslationUserAccuracyCounter.objects.filter(translation__in=translations, user=user)
        return user_accuracies.filter(good_answers_counter__gte=min_revisions).count() == translations.count()

    def is_locked_for_user(self, user):
        wordset_user_accuracy, _ = WordSetUserAccuracy.objects.get_or_create(user=user, wordset=self)
        if wordset_user_accuracy:
            return wordset_user_accuracy.locked
        return True


class WordSetUserAccuracy(models.Model):
    user = models.ForeignKey("CustomUser", on_delete=models.CASCADE)
    wordset = models.ForeignKey(WordSet, on_delete=models.CASCADE)
    accuracy = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    unlocked = models.BooleanField(default=False)
    class Meta:
        unique_together = ('user', 'wordset')

    @property
    def locked(self):
        if self.wordset.difficulty == 1 or self.unlocked:
            self.unlocked = True
            return False

        lower_difficulty_wordsets = WordSet.objects.filter(
            category=self.wordset.category,
            difficulty__lt=self.wordset.difficulty
        )

        for lower_difficulty_wordset in lower_difficulty_wordsets:
            if not lower_difficulty_wordset.are_all_words_revised_at_least_x_times(self.user):
                return True

            lower_difficulty_wordset_user_accuracy, created = WordSetUserAccuracy.objects.get_or_create(
                user=self.user,
                wordset=lower_difficulty_wordset
            )
            lower_difficulty_wordset_user_accuracy.save()

        if WordSetUserAccuracy.objects.filter(
                wordset__in=lower_difficulty_wordsets,
                user=self.user,
                accuracy__lt=0.7
        ).exists():
            return True

        self.unlocked = True
        return False

    def save(self, *args, **kwargs):
        self.accuracy = self.wordset.calculate_average_accuracy(self.user)
        super().save(*args, **kwargs)


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


class FallingWordsGameSession(BaseGameSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game_name = 'falling_words'


class RaceGameSession(BaseGameSession):
    opponents = models.ManyToManyField("CustomUser", related_name="race_game_sessions", blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game_name = 'race'

class FindingWordsGameSession(BaseGameSession):
    opponents = models.ManyToManyField("CustomUser", related_name="finding_words_game_sessions", blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game_name = 'race'


class MultiplayerGames(models.TextChoices):
    RACE = "race"
    FINDING_WORDS = "findingwords"


class WaitingRoom(models.Model):
    game = models.TextField(choices=MultiplayerGames.choices)
    wordset = models.ForeignKey(WordSet, on_delete=models.CASCADE)
    users = models.ManyToManyField("CustomUser", related_name="in_waiting_room", blank=True)
    owner = models.ForeignKey("Customuser", null=True, related_name="owns_waiting_room", on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    @classmethod
    def get_waiting_room_by_game_and_wordset(cls, game, wordset):
        try:
            return cls.objects.get(game=game, wordset=wordset)
        except cls.DoesNotExist:
            return None

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
