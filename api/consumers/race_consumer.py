import asyncio
import json
from dataclasses import asdict
from datetime import datetime

from channels.db import database_sync_to_async
from django.core.exceptions import ObjectDoesNotExist

from api.consumers.helpers import get_race_rounds, get_words_for_play, SocketGameState
from api.consumers.messages import (
    RaceRoundResultMessage,
    RaceAnswerMessage,
    RaceNewQuestionMessage,
    GameStartingMessage,
    GameFinalResultMessage
)
from api.consumers.waitroom_consumer import WaitListConsumer
from api.models import RaceActiveGame, GamePlayer, RaceGameSession


class RaceConsumer(WaitListConsumer):
    DEFAULT_ROUNDS_COUNT = 3

    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.start_game_timestamp = None
        self.game_player = None
        self.last_answer = None
        self.race_active_game = None

    # Virtual functions implementations
    @staticmethod
    async def on_game_init(players, wordset):
        return (await RaceConsumer.create_race_active_game(players, wordset)).pk

    async def on_start(self, session_id):
        await self.init_race_active_game(session_id)
        await self.send(await self.create_starting_message())
        
        await asyncio.sleep(1)
        
        self.start_game_timestamp = datetime.now()
        await self.send(await self.create_question_message())

    async def on_message(self, message):
        message = RaceAnswerMessage(answer=message["answer"])

        if await self.handle_answer(message):
            await self.group_send("event_end_round", {})

    async def on_disconnected(self):
        await self.save_race_game_session()
        await self.clear_race_active_game()

    # Database functions
    @database_sync_to_async
    def save_race_game_session(self):
        race_game_session = RaceGameSession.objects.create(
            user=self.user,
            wordset=self.race_active_game.wordset,
            score=self.game_player.score,
            duration=(datetime.now() - self.start_game_timestamp).total_seconds())
        race_game_session.opponents.set(self.race_active_game.players.exclude(user=self.user).values_list("user", flat=True))
        print(race_game_session)
        race_game_session.save()

    @staticmethod
    @database_sync_to_async
    def create_race_active_game(players, wordset):
        words = get_words_for_play(wordset)
        race_rounds = get_race_rounds(words)
        game_session = RaceActiveGame.objects.create(
            rounds=json.dumps([asdict(r) for r in race_rounds]),
            wordset=wordset,
        )
        game_session.players.set([GamePlayer.objects.create(user=player) for player in players])
        game_session.save()
        return game_session

    @database_sync_to_async
    def init_race_active_game(self, session_id):
        self.race_active_game = RaceActiveGame.objects.get(pk=session_id)
        self.game_player = self.race_active_game.players.filter(user=self.user).first()

    @database_sync_to_async
    def create_question_message(self):
        rounds = json.loads(self.race_active_game.rounds)
        if self.race_active_game.round_count < len(rounds):
            round = rounds[self.race_active_game.round_count]
            return RaceNewQuestionMessage(
                question=round["question"], answers=round["options"]
            ).to_json()
        else:
            return None

    @database_sync_to_async
    def create_starting_message(self):
        usernames = [player.user.username for player in self.race_active_game.players.all()]

        return GameStartingMessage(players=usernames).to_json()

    @database_sync_to_async
    def create_result_message(self):
        self.race_active_game.refresh_from_db()
        round = json.loads(self.race_active_game.rounds)[self.race_active_game.round_count - 1]

        if round["answer"] == self.last_answer:
            points = 15
            self.game_player.add_good_answer()
            self.game_player.add_points(points)

        self.game_player.refresh_from_db()

        return RaceRoundResultMessage(correct=round["answer"], points=self.game_player.score).to_json()

    @database_sync_to_async
    def create_game_results_message(self):
        players_with_scores = self.race_active_game.players.values('user__username', 'score').order_by('-score')
        game_result_message = GameFinalResultMessage.create_from_players(players_with_scores)
        return game_result_message.to_json()

    @database_sync_to_async
    def handle_answer(self, message: RaceAnswerMessage):
        """Returns True if all players had answered already"""
        self.last_answer = message.answer

        self.race_active_game.refresh_from_db()
        self.race_active_game.add_answer()
        self.race_active_game.refresh_from_db()

        if self.race_active_game.answers_count == len(self.race_active_game.players.all()):
            self.race_active_game.reset_answers_count()
            self.race_active_game.add_round()
            return True

        return False

    @database_sync_to_async
    def clear_race_active_game(self):
        if self.race_active_game:
            try:
                self.race_active_game.refresh_from_db()
                self.race_active_game.delete()
            except ObjectDoesNotExist:
                pass
            finally:
                self.race_active_game = None

    async def event_end_round(self, event):
        await self.send(await self.create_result_message())
        await asyncio.sleep(1)

        if self.race_active_game.round_count < self.DEFAULT_ROUNDS_COUNT:
            await self.send_next_question()
        else:
            self.__state = SocketGameState.ENDING_GAME
            await self.send_game_results()

    async def send_next_question(self):
        message = await self.create_question_message()
        await self.send(message)

    async def send_game_results(self):
        await self.send(await self.create_game_results_message())