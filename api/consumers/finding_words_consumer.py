import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from random import shuffle
from typing import List

from channels.db import database_sync_to_async
from django.core.exceptions import ObjectDoesNotExist

from api.consumers.helpers import get_words_for_play, SocketGameState
from api.consumers.messages import (
    FindingWordsRoundResultMessage,
    FindingWordsAnswerMessage,
    FindingWordsNewQuestionMessage,
    GameStartingMessage,
    GameFinalResultMessage
)
from api.consumers.waitroom_consumer import WaitListConsumer
from api.models import FindingWordsActiveGame, GamePlayer, FindingWordsGameSession, TranslationUserAccuracyCounter


class FindingWordsConsumer(WaitListConsumer):
    DEFAULT_ROUNDS_COUNT = 3

    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.active_game = None
        self.player: GamePlayer = None
        self.last_answer = None
        self.start_game_timestamp = None

    # Virtual functions implementations
    @staticmethod
    async def on_game_init(players):
        active_game = await FindingWordsConsumer.create_active_game(players)
        return active_game.pk

    async def on_start(self, session_id):
        await self.init_active_game(session_id)
        await self.send(await self.create_starting_message())
        
        await asyncio.sleep(1)
        
        self.start_game_timestamp = datetime.now()
        await self.send(await self.create_question_message())

    async def on_message(self, message):
        message = FindingWordsAnswerMessage(answer=message["answer"])

        if await self.handle_answer(message):
            await self.group_send("event_end_round", {})

    async def on_disconnected(self):
        await self.save_game_session()
        await self.clear_active_game()

    # Database functions
    @database_sync_to_async
    def save_game_session(self):
        game_session = FindingWordsGameSession.objects.create(
            user=self.user,
            wordset=self.active_game.wordset,
            score=self.player.score,
            accuracy=self.player.good_answers / self.active_game.round_count,
            duration=(datetime.now() - self.start_game_timestamp).total_seconds())
        game_session.opponents.set(self.active_game.players.exclude(user=self.user).values_list("user", flat=True))
        game_session.save()

    @staticmethod
    @database_sync_to_async
    def create_active_game(players):
        words, wordset = get_words_for_play()
        rounds = get_rounds([word['english'] for word in words], 3)
        game_session = FindingWordsActiveGame.objects.create(
            rounds=json.dumps([asdict(r) for r in rounds]),
            wordset=wordset,
        )
        game_session.players.set([GamePlayer.objects.create(user=player) for player in players])
        game_session.save()
        return game_session

    @database_sync_to_async
    def init_active_game(self, session_id):
        self.active_game = FindingWordsActiveGame.objects.get(pk=session_id)
        self.player = self.active_game.players.filter(user=self.user).first()

    @database_sync_to_async
    def create_question_message(self):
        rounds: FindingWordsRound = json.loads(self.active_game.rounds)
        if self.active_game.round_count < len(rounds):
            round = rounds[self.active_game.round_count]
            message = FindingWordsNewQuestionMessage(round["letters"])
            return message.to_json()
        else:
            return None

    @database_sync_to_async
    def create_starting_message(self):
        usernames = [player.user.username for player in self.active_game.players.all()]

        return GameStartingMessage(players=usernames).to_json()

    @database_sync_to_async
    def create_result_message(self):
        self.active_game.refresh_from_db()
        rounds = json.loads(self.active_game.rounds)
        round: FindingWordsRound = rounds[self.active_game.round_count - 1]
        wordset = self.active_game.wordset

        valid_answer = all([letter in round["letters"] for letter in self.last_answer])
        correct_answer = wordset.words.all().filter(english=self.last_answer).values("id").first()
        
        player_won = valid_answer and correct_answer

        if player_won:
            points = get_points(self.last_position)
            TranslationUserAccuracyCounter.increment_good_answer(user=self.user, translation_id=correct_answer["id"])

            self.player.add_good_answer()
            self.player.add_points(points)

        self.player.refresh_from_db()

        word = self.last_answer if player_won else round["answer"]

        return FindingWordsRoundResultMessage(word, self.player.score).to_json()

    @database_sync_to_async
    def create_game_results_message(self):
        players_with_scores = self.active_game.players.values('user__username', 'score').order_by('-score')
        game_result_message = GameFinalResultMessage.create_from_players(players_with_scores)
        return game_result_message.to_json()

    @database_sync_to_async
    def handle_answer(self, message: FindingWordsAnswerMessage):
        """Returns True if all players had answered already"""
        self.active_game.refresh_from_db()

        self.last_answer = message.answer
        self.last_position = self.active_game.answers_count

        self.active_game.record_answer()

        self.active_game.refresh_from_db()
        if self.active_game.answers_count == len(self.active_game.players.all()):
            self.active_game.move_to_next_round()
            return True

        return False

    @database_sync_to_async
    def clear_active_game(self):
        if self.active_game:
            try:
                self.active_game.refresh_from_db()
                self.active_game.delete()
            except ObjectDoesNotExist:
                pass
            finally:
                self.active_game = None

    async def event_end_round(self, event):
        message = await self.create_result_message()
        await self.send(message)
        await asyncio.sleep(1)

        if self.active_game.round_count < self.DEFAULT_ROUNDS_COUNT:
            message = await self.create_question_message()
            await self.send(message)
        else:
            self.__state = SocketGameState.ENDING_GAME
            message = await self.create_game_results_message()
            await self.send(message)


@dataclass
class FindingWordsRound:
    letters: List[str]
    answer: str

def get_rounds(words: List[str], round_count: int) -> List[FindingWordsRound]:
    LETTER_COUNT = 8
    ADD_ADDITIONAL_LETTERS = False
    rounds = []

    all_letters = list(set([letter for word in words for letter in word]))

    shuffle(words)
    for _ in range(round_count):
        shuffle(all_letters)

        word = words.pop()
        letters = list(word)

        remaining_letters = LETTER_COUNT - len(letters)
        if remaining_letters > 0 and ADD_ADDITIONAL_LETTERS:
            letters += all_letters[:remaining_letters]

        shuffle(letters)

        rounds.append(FindingWordsRound(letters, word))

    return rounds

def get_points(position: int):
    POINTS_PER_POSITION = [25, 20, 15, 10, 5]
    if position < len(POINTS_PER_POSITION):
        return POINTS_PER_POSITION[position]
    return POINTS_PER_POSITION[-1]