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
    GameResultMessage,
)
from api.consumers.waitlist_consumer import WaitListConsumer
from api.models import RaceActiveGame


class RaceConsumer(WaitListConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.last_answer = None
        self.race_session = None
        self.score = 0

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
        game_session.users.set(players)
        game_session.save()
        return game_session

    @database_sync_to_async
    def init_race_session(self, session_id):
        self.race_session = RaceActiveGame.objects.get(pk=session_id)

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
        players = self.race_session.users.all().values_list("username", flat=True)
        return GameStartingMessage(players=list(players)).to_json()

    @database_sync_to_async
    def create_result_message(self):
        self.race_session.refresh_from_db()
        round = json.loads(self.race_session.rounds)[self.race_session.round_count - 1]
        points = 0
        if round["answer"] == self.last_answer:
            points = 15
            self.score += 15
        return ResultMessage(correct=round["answer"], points=points).to_json()

    @database_sync_to_async
    def create_game_results_message(self):
        return GameResultMessage(winner="future_feature", points=self.score).to_json()

    @database_sync_to_async
    def handle_answer(self, message: AnswerMessage):
        """Returns True if all players had answered already"""
        self.last_answer = message.answer
        self.race_session.refresh_from_db()
        self.race_session.answers_count += 1
        self.race_session.save()

        if self.race_session.answers_count == len(self.race_session.users.all()):
            self.race_session.answers_count = 0
            self.race_session.round_count += 1
            self.race_session.save()
            return True

        return False
    
    @database_sync_to_async
    def clear_race_session(self):
        self.race_session.refresh_from_db()
        self.race_session.answers_count += 1
        self.race_session.save()
        if self.race_session.answers_count == len(self.race_session.users.all()):
            self.race_session.delete()
        self.race_session = None

    # Group events
    async def event_send_results(self, event):
        await self.send(await self.create_result_message())
        await asyncio.sleep(1)

        if self.race_session.round_count < 4:
            message = await self.create_question_message()
            await self.send(message)
        else:
            await self.send(await self.create_game_results_message())
