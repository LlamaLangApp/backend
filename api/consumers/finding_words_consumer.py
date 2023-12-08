import json
from datetime import datetime, timezone
from typing import List
from channels.db import database_sync_to_async
from api.consumers.helpers import FindingWordsRound, SocketGameState
from api.consumers.messages import (
    FindingWordsRoundResultMessage,
    FindingWordsAnswerMessage,
    FindingWordsNewQuestionMessage,
    GameFinalResultMessage
)
from api.consumers.waitroom_consumer import DEFAULT_TIMEOUT, WaitListConsumer
from api.models import FindingWordsActiveGame, GamePlayer, FindingWordsGameSession, WaitingRoom


class FindingWordsConsumer(WaitListConsumer):
    DEFAULT_ROUNDS_COUNT = 3

    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.start_game_timestamp = None
        self.player: GamePlayer = None
        self.last_answer = None

    # Virtual functions implementations
    @staticmethod
    def game_name() -> str:
        return "findingwords"

    @staticmethod
    @database_sync_to_async
    def create_session_from_waiting_room(room: WaitingRoom) -> str:
        if not room:
            return False

        session = FindingWordsActiveGame.create_session_from_waiting_room(room)
        room.delete()
        return session.pk

    @database_sync_to_async
    def load_active_game(self, session_id):
        self.active_game = FindingWordsActiveGame.objects.get(pk=session_id)
        self.player = self.active_game.players.filter(user=self.user).first()

    async def on_game_started(self):
        message = await self.create_question_message()
        await self.send(message)

    async def on_message(self, message):
        try:
            message = FindingWordsAnswerMessage.from_json(message)
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

        saved_session = FindingWordsGameSession.objects.create(
            user=self.user,
            wordset=self.active_game.wordset,
            score=self.player.score,
            accuracy= accuracy,
            duration=(datetime.now(timezone.utc) - self.active_game.timestamp).total_seconds())
        saved_session.opponents.set(self.active_game.players.exclude(user=self.user).values_list("user", flat=True))
        saved_session.save()

        self.active_game.required_answers -= 1
        self.active_game.save()

    @database_sync_to_async
    def create_question_message(self):
        rounds: List[FindingWordsRound] = json.loads(self.active_game.rounds)
        if self.active_game.all_rounds_played():
            return None
        
        round = rounds[self.active_game.round_count]
        message = FindingWordsNewQuestionMessage(letters=round["letters"], round=self.active_game.round_count, timeout=DEFAULT_TIMEOUT)
        return message.to_json()

    @database_sync_to_async
    def create_result_message(self):
        self.active_game.refresh_from_db()
        rounds = json.loads(self.active_game.rounds)
        round: FindingWordsRound = rounds[self.active_game.round_count - 1]

        player_won = self.active_game.is_answer_valid_for_round(self.last_answer, self.active_game.round_count - 1)
        if player_won:
            points = get_points(self.last_position)

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
        self.active_game.refresh_from_db()

        if message.round != self.active_game.round_count:
            return

        if not self.active_game.is_answer_valid_for_round(message.answer, self.active_game.round_count):
            return

        self.last_answer = message.answer
        self.last_position = self.active_game.answers_in_current_round

        self.active_game.mark_player_answer()

    async def end_round_event(self, event):
        message = await self.create_result_message()
        self.last_answer = None
        self.last_position = None
        await self.send(message)

    async def new_round_event(self, event):
        message = await self.create_question_message()
        if message:
            await self.send(message)
        else:
            self.state = SocketGameState.ENDING_GAME
            message = await self.create_game_results_message()
            await self.send(message)

def get_points(position: int):
    POINTS_PER_POSITION = [25, 20, 15, 10, 5]
    if position < len(POINTS_PER_POSITION):
        return POINTS_PER_POSITION[position]
    return POINTS_PER_POSITION[-1]