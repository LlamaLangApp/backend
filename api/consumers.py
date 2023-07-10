import asyncio
from dataclasses import dataclass, asdict
from enum import Enum, auto
import json
from random import shuffle, sample
from typing import Any, List, Tuple

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import async_to_sync

from api.models import WaitingRoom, WordSet, RaceRound, RaceActiveGame
from django.contrib.auth import get_user_model

User = get_user_model()


@dataclass
class WebSocketMessage:
    def to_json(self):
        return json.dumps(asdict(self))


class WaitroomMessageType(str, Enum):
    WAITROOM_REQUEST = "waitroom_request"
    JOINED_WAITROOM = "joined_waitroom"
    GAME_STARTING = "game_starting"


@dataclass
class WaitroomRequestMessage(WebSocketMessage):
    game: str
    type: str = WaitroomMessageType.WAITROOM_REQUEST


@dataclass
class JoinedWaitroomMessage(WebSocketMessage):
    type: str = WaitroomMessageType.JOINED_WAITROOM


@dataclass
class GameStartingMessage(WebSocketMessage):
    players: List[str]
    type: str = WaitroomMessageType.GAME_STARTING


class SocketGameState(Enum):
    JUST_CONNECTED: int = auto()
    IN_WAITROOM: int = auto()
    BEFORE_GAME: int = auto()
    IN_GAME: int = auto()


class WaitListConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope["user"].is_authenticated:
            self.user: User = self.scope["user"]
            self.state = SocketGameState.JUST_CONNECTED
            await self.accept()
        else:
            self.user = None
            self.state = None
            await self.close()

    async def disconnect(self, close_code):
        if not self.state:
            return

        if self.state == SocketGameState.IN_WAITROOM:
            await self.remove_user_from_waitroom()
        elif self.state == SocketGameState.IN_GAME:
            await self.on_disconnected()

    @database_sync_to_async
    def remove_user_from_waitroom(self):
        room = WaitingRoom.objects.filter(users__pk__contains=self.user.pk).get()
        async_to_sync(self.channel_layer.group_discard)(str(room.pk), self.channel_name)
        room.users.remove(self.user)
        room.save()

    async def receive(self, text_data):
        message = json.loads(text_data)

        # TODO: security
        if self.state == SocketGameState.JUST_CONNECTED:
            message = WaitroomRequestMessage(game=message["game"])

            room_pk = await self.add_user_to_waitroom(message.game)
            self.group_name = str(room_pk)
            await self.channel_layer.group_add(self.group_name, self.channel_name)

            await self.send(JoinedWaitroomMessage().to_json())
            self.state = SocketGameState.IN_WAITROOM

            is_full, players = await self.is_waitroom_full(message.game)

            if is_full:
                session_id = await self.on_game_init(players)
                await self.channel_layer.group_send(
                    self.group_name, {"type": "start.game", "session_id": session_id}
                )
        elif self.state == SocketGameState.IN_WAITROOM:
            pass
        elif self.state == SocketGameState.IN_GAME:
            await self.on_message(message)

    @database_sync_to_async
    def add_user_to_waitroom(self, game) -> str:
        room, _ = WaitingRoom.objects.filter(game=game).get_or_create(game=game)

        room.users.add(self.user)
        room.save()

        return room.pk

    @database_sync_to_async
    def is_waitroom_full(self, game) -> Tuple[bool, Any]:
        room = WaitingRoom.objects.filter(game=game).get()
        if len(room.users.all()) == 2:
            players = list(room.users.all().values_list("pk", flat=True))
            room.delete()
            return True, players
        return False, None

    async def start_game(self, event):
        await self.on_start(event["session_id"])

    async def on_game_init(self, players):
        raise NotImplementedError()

    async def on_start(self, session_id):
        raise NotImplementedError()

    async def on_message(self, message):
        raise NotImplementedError()

    async def on_disconnected(self):
        raise NotImplementedError()


class RaceMessageType(str, Enum):
    NEW_QUESTION = "new_question"
    RESPONSE = "response"
    RESULT = "result"


@dataclass
class NewQuestionMessage(WebSocketMessage):
    question: str
    answers: List[str]
    type: str = RaceMessageType.NEW_QUESTION


@dataclass
class AnswerMessage(WebSocketMessage):
    answer: str
    type: str = RaceMessageType.RESPONSE


@dataclass
class ResultMessage(WebSocketMessage):
    correct: str
    points: int
    type: str = RaceMessageType.RESULT


class RaceConsumer(WaitListConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.race_session = None

    async def on_game_init(self, players):
        return (await self.create_race_active_game(players)).pk

    @database_sync_to_async
    def create_race_active_game(self, players):
        race_rounds = get_race_rounds(get_words_for_play())
        game_session = RaceActiveGame.objects.create(
            rounds=json.dumps([asdict(r) for r in race_rounds])
        )
        game_session.users.set(players)
        game_session.save()
        return game_session

    async def on_start(self, session_id):
        self.state = SocketGameState.BEFORE_GAME
        await self.get_race_session(session_id)
        message = await self.create_starting_message()
        await self.send(message)

        await asyncio.sleep(1)

        self.state = SocketGameState.IN_GAME
        await self.send(await self.create_question_message())

    async def on_message(self, message):
        message = AnswerMessage(answer=message["answer"])

        if await self.handle_answer(message):
            await self.channel_layer.group_send(
                self.group_name, {"type": "send.results"}
            )

    async def on_disconnected(self):
        pass

    async def send_results(self, event):
        await self.send(await self.create_result_message())
        await asyncio.sleep(1)
        await self.send(await self.create_question_message())

    @database_sync_to_async
    def create_question_message(self):
        rounds = json.loads(self.race_session.rounds)
        if self.race_session.round_count < len(rounds):
            round = rounds[self.race_session.round_count]
            return NewQuestionMessage(
                question=round["question"], answers=round["options"]
            ).to_json()
        else:
            print("end")

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
        return ResultMessage(correct=round["answer"], points=points).to_json()

    @database_sync_to_async
    def get_race_session(self, session_id):
        self.race_session = RaceActiveGame.objects.get(pk=session_id)

    @database_sync_to_async
    def handle_answer(self, message: AnswerMessage):
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


def get_race_rounds(words) -> List[RaceRound]:
    rounds = []
    for _ in range(5):
        shuffle(words)
        word = words.pop(0)
        correct_translation = word["polish"]

        incorrect_translations = sample([w["polish"] for w in words], 3)

        rounds.append(
            RaceRound(
                answer=correct_translation,
                question=word["english"],
                options=incorrect_translations + [correct_translation],
            )
        )
    return rounds


def get_words_for_play():
    word_set = WordSet.objects.order_by("?")[0]
    return list(word_set.words.all().values("polish", "english"))
