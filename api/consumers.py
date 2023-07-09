import asyncio
from dataclasses import dataclass, asdict
from enum import Enum, auto
import json
from typing import List

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import async_to_sync

from api.models import WaitingRoom
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
            self.state == SocketGameState.IN_WAITROOM

            if await self.is_waitroom_full(message.game):
                await self.channel_layer.group_send(group_name, {"type": "start.game"})
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
            room.delete()
            return True
        return False

    async def start_game(self, event):
        self.state = SocketGameState.BEFORE_GAME
        # TODO: fetch from db
        await self.send(GameStartingMessage(players=["alice", "bob"]).to_json())
        await asyncio.sleep(5)
        self.state = SocketGameState.IN_GAME
        await self.on_start()

    async def on_start(self):
        raise NotImplementedError()

    async def on_message(self):
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
    async def on_start(self):
        await self.send(self.get_new_question_message().to_json())

    async def on_message(self):
        pass

    async def on_disconnected(self):
        pass

    def get_new_question_message(self):
        return NewQuestionMessage(question="B", answers=["a", "b", "c", "d"])
