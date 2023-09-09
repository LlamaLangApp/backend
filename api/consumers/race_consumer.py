import asyncio
import json
from dataclasses import asdict

from channels.db import database_sync_to_async
from api.consumers.helpers import get_race_rounds, get_words_for_play
from api.consumers.messages import (
    ResultMessage,
    AnswerMessage,
    NewQuestionMessage,
    GameStartingMessage,
    GameFinalResultMessage
)
from api.consumers.waitlist_consumer import WaitListConsumer
from api.models import RaceActiveGame, GamePlayer


class RaceConsumer(WaitListConsumer):
    DEFAULT_ROUNDS_COUNT = 3

    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.last_answer = None
        self.race_session = None

    # Virtual functions implementations
    @staticmethod
    async def on_game_init(players):
        return (await RaceConsumer.create_race_active_game(players)).pk

    async def on_start(self, session_id):
        await self.init_race_session(session_id)
        await self.send(await self.create_starting_message())
        await asyncio.sleep(1)
        await self.send(await self.create_question_message())

    async def on_message(self, message):
        message = AnswerMessage(answer=message["answer"])

        if await self.handle_answer(message):
            await self.group_send("event_send_results", {})

    async def on_disconnected(self):
        await self.clear_race_session()

    # Database functions

    @staticmethod
    @database_sync_to_async
    def create_race_active_game(players):
        race_rounds = get_race_rounds(get_words_for_play())
        game_session = RaceActiveGame.objects.create(
            rounds=json.dumps([asdict(r) for r in race_rounds])
        )
        game_session.players.set([GamePlayer.objects.create(user=player) for player in players])
        game_session.save()
        return game_session

    @database_sync_to_async
    def init_race_session(self, session_id):
        self.race_session = RaceActiveGame.objects.get(pk=session_id)
        self.game_player = self.race_session.players.filter(user=self.user).first()

    @database_sync_to_async
    def create_question_message(self):
        rounds = json.loads(self.race_session.rounds)
        if self.race_session.round_count < len(rounds):
            round = rounds[self.race_session.round_count]
            return NewQuestionMessage(
                question=round["question"], answers=round["options"]
            ).to_json()
        else:
            return None

    @database_sync_to_async
    def create_starting_message(self):
        usernames = [player.user.username for player in self.race_session.players.all()]

        return GameStartingMessage(players=usernames).to_json()

    @database_sync_to_async
    def create_result_message(self):
        self.race_session.refresh_from_db()
        round = json.loads(self.race_session.rounds)[self.race_session.round_count - 1]
        points = 0

        if round["answer"] == self.last_answer:
            points = 15
            self.game_player.add_points(points)

        self.game_player.refresh_from_db()

        return ResultMessage(correct=round["answer"], points=self.game_player.score).to_json()

    @database_sync_to_async
    def create_game_results_message(self):
        players_with_scores = self.race_session.players.values('user__username', 'score').order_by('-score')
        game_result_message = GameFinalResultMessage.create_from_players(players_with_scores)
        return game_result_message.to_json()

    @database_sync_to_async
    def handle_answer(self, message: AnswerMessage):
        """Returns True if all players had answered already"""
        self.last_answer = message.answer

        self.race_session.refresh_from_db()
        self.race_session.add_answer()
        self.race_session.refresh_from_db()

        if self.race_session.answers_count == len(self.race_session.players.all()):
            self.race_session.reset_answers_count()
            self.race_session.add_round()
            return True

        return False

    @database_sync_to_async
    def clear_race_session(self):
        self.race_session.refresh_from_db()
        self.race_session.add_answer()

        if self.race_session.answers_count == len(self.race_session.players.all()):
            self.race_session.delete()
        self.race_session = None

    # Group events
    async def event_send_results(self, event):
        await self.send(await self.create_result_message())
        await asyncio.sleep(1)

        if self.race_session.round_count < self.DEFAULT_ROUNDS_COUNT:
            message = await self.create_question_message()
            await self.send(message)
        else:
            await self.send(await self.create_game_results_message())

