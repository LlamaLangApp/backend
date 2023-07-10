import asyncio
from dataclasses import dataclass, asdict
from enum import Enum, auto
import json
from random import shuffle, sample
from typing import List

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
            await self.accept()
            self.user: User = self.scope["user"]
            self.state = SocketGameState.JUST_CONNECTED
        else:
            await self.close()

    async def disconnect(self, close_code):
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
            group_name = str(room_pk)
            await self.channel_layer.group_add(group_name, self.channel_name)

            await self.send(JoinedWaitroomMessage().to_json())
            self.state = SocketGameState.IN_WAITROOM

            players = await self.is_waitroom_full(message.game)

            if players:
                session_id = await self.on_game_init(players)
                await self.channel_layer.group_send(group_name, {"type": "start.game", "session_id": session_id})
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
    def is_waitroom_full(self, game) -> bool:
        room = WaitingRoom.objects.filter(game=game).get()
        if len(room.users.all()) == 2:
            players = room.users.all()
            room.delete()
            return players
        return False

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


@dataclass
class NewQuestionMessage(WebSocketMessage):
    question: str
    answers: List[str]
    type: str = RaceMessageType.NEW_QUESTION


@dataclass
class AnswerMessage(WebSocketMessage):
    answer: str
    type: str = RaceMessageType.RESPONSE


class RaceConsumer(WaitListConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.race_session = None

    async def on_game_init(self, players):
        race_rounds = get_race_rounds(await database_sync_to_async(get_words_for_play)())
        game_session = RaceActiveGame.objects.create(users=players, rounds=race_rounds)
        return game_session.pk

    async def on_start(self, session_id):
        self.state = SocketGameState.BEFORE_GAME
        await self.get_race_session(session_id)
        message = await self.create_starting_message()
        await self.send(message)

        await asyncio.sleep(5)

        self.state = SocketGameState.IN_GAME
        await self.send(self.get_new_question_message().to_json())

    async def on_message(self, message):
        if message.type == RaceMessageType.RESPONSE:
            self.handle_answer(message)

    async def on_disconnected(self):
        pass

    def get_new_question_message(self):
        return NewQuestionMessage(question="B", answers=["a", "b", "c", "d"])

    @database_sync_to_async
    def create_starting_message(self):
        players = self.race_session.users.all().values_list("username", flat=True)
        GameStartingMessage(players=players).to_json()

    @database_sync_to_async
    def get_race_session(self, session_id):
        self.race_session = RaceActiveGame.objects.get(pk=session_id)

    def handle_answer(self, message):
        user_id, answer = message["user_id"], message["answer"]
        self.race_session.answers_count += 1



def get_race_rounds(words):
    rounds = []
    for _ in range(10):
        shuffle(words)
        word = words.pop(0)
        correct_translation = word["polish"]

        incorrect_translations = sample([w["polish"] for w in words], 3)

        rounds.append(RaceRound(answer=correct_translation,
                                question=word["english"],
                                options=incorrect_translations + [correct_translation]))
    return rounds


def get_words_for_play():
    word_set = WordSet.objects.order_by("?")[0]
    return list(word_set.words.all().values("polish", "english"))
