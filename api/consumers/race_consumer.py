import asyncio
import json
from datetime import datetime, timezone
from channels.db import database_sync_to_async
from api.consumers.helpers import SocketGameState
from api.consumers.messages import (
    RaceRoundResultMessage,
    RaceAnswerMessage,
    RaceNewQuestionMessage,
    GameFinalResultMessage
)
from api.consumers.waitroom_consumer import DEFAULT_TIMEOUT, WaitListConsumer
from api.models import RaceActiveGame, GamePlayer, RaceGameSession, TranslationUserAccuracyCounter, WaitingRoom

class RaceConsumer(WaitListConsumer):
    DEFAULT_ROUNDS_COUNT = 3

    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.player: GamePlayer = None
        self.last_answer = None

    # Virtual functions implementations
    @staticmethod
    def game_name() -> str:
        return "race"

    @staticmethod
    @database_sync_to_async
    def create_session_from_waiting_room(room: WaitingRoom) -> str:
        if not room:
            return False

        session = RaceActiveGame.create_session_from_waiting_room(room)
        room.delete()
        return session.pk

    @database_sync_to_async
    def load_active_game(self, session_id):
        self.active_game = RaceActiveGame.objects.get(pk=session_id)
        self.player = self.active_game.players.filter(user=self.user).first()

    async def on_game_started(self):
        await self.send(await self.create_question_message())

    async def on_message(self, message):
        try:
            message = RaceAnswerMessage.from_json(message)
        except RuntimeError:
            await self.send_error("Bad message")
            return

        await self.handle_answer(message)
        await self.check_if_round_ended()

    # Database functions
    @database_sync_to_async
    def handle_disconnection(self):
        accuracy = 0
        if self.active_game.round_count > 0:
            self.player.good_answers / self.active_game.round_count

        race_game_session = RaceGameSession.objects.create(
            user=self.user,
            wordset=self.active_game.wordset,
            score=self.player.score,
            accuracy=accuracy,
            duration=(datetime.now(timezone.utc) - self.active_game.timestamp).total_seconds())
        race_game_session.opponents.set(self.active_game.players.exclude(user=self.user).values_list("user", flat=True))
        race_game_session.save()

        self.active_game.required_answers -= 1
        self.active_game.save()

        if self.active_game.required_answers == 0:
            self.active_game.delete()

    @database_sync_to_async
    def create_question_message(self):
        rounds = json.loads(self.active_game.rounds)
        if self.active_game.all_rounds_played():
            return None
        
        round = rounds[self.active_game.round_count]
        message = RaceNewQuestionMessage(
            question=round["question"], answers=round["options"],
            timeout=DEFAULT_TIMEOUT
        )
        return message.to_json()

    @database_sync_to_async
    def create_result_message(self):
        self.active_game.refresh_from_db()
        rounds = json.loads(self.active_game.rounds)
        round = rounds[self.active_game.round_count - 1]

        if round["answer"] == self.last_answer:
            points = 15

            TranslationUserAccuracyCounter.increment_good_answer(user=self.user, translation_id=round["answer_id"])

            self.player.add_good_answer()
            self.player.add_points(points)

        TranslationUserAccuracyCounter.increment_bad_answer(user=self.user, translation_id=round["answer_id"])
        self.player.refresh_from_db()

        return RaceRoundResultMessage(correct=round["answer"], points=self.player.score).to_json()

    @database_sync_to_async
    def create_game_results_message(self):
        players_with_scores = self.active_game.players.values('user__username', 'score').order_by('-score')
        game_result_message = GameFinalResultMessage.create_from_players(players_with_scores)
        return game_result_message.to_json()

    @database_sync_to_async
    def handle_answer(self, message: RaceAnswerMessage):
        self.last_answer = message.answer

        self.active_game.mark_player_answer()

    async def event_end_round(self, event):
        message = await self.create_result_message()
        await self.send(message)
        await asyncio.sleep(1)

        message = await self.create_question_message()
        if message:
            await self.send(message)
        else:
            self.state = SocketGameState.ENDING_GAME
            message = await self.create_game_results_message()
            await self.send(message)

    async def end_round_event(self, event):
        message = await self.create_result_message()
        self.last_answer = None
        await self.send(message)

    async def new_round_event(self, event):
        message = await self.create_question_message()
        if message:
            await self.send(message)
        else:
            self.state = SocketGameState.ENDING_GAME
            message = await self.create_game_results_message()
            await self.send(message)