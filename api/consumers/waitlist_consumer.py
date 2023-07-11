import json
from typing import List, Tuple

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from api.consumers.helpers import SocketGameState
from api.consumers.messages import JoinedWaitroomMessage, WaitroomRequestMessage
from api.models import WaitingRoom
from django.contrib.auth import get_user_model

User = get_user_model()


class WaitListConsumer(AsyncWebsocketConsumer):
    # Utils
    async def group_send(self, function_name: str, args):
        await self.channel_layer.group_send(
            self.__group_name,
            {"type": function_name.replace("_", "."), **args},
        )

    # Websocket functions

    async def connect(self):
        if self.scope["user"].is_authenticated:
            self.user: User = self.scope["user"]
            self.__state = SocketGameState.JUST_CONNECTED
            await self.accept()
        else:
            self.user = None
            self.__state = None
            await self.close()

    async def disconnect(self, close_code):
        if not self.__state:
            return

        await self.channel_layer.group_discard(self.__group_name, self.channel_name)
        if self.__state == SocketGameState.IN_WAITROOM:
            await self.remove_user_from_waitroom()
        elif self.__state == SocketGameState.IN_GAME:
            await self.on_disconnected()

        self.__state = None
        self.__group_name = None
        self.user = None

    async def receive(self, text_data):
        message = json.loads(text_data)

        # TODO: security
        if self.__state == SocketGameState.JUST_CONNECTED:
            message = WaitroomRequestMessage(game=message["game"])

            room_pk = await self.add_user_to_waitroom(message.game)
            self.__group_name = str(room_pk)
            await self.channel_layer.group_add(self.__group_name, self.channel_name)

            await self.send(JoinedWaitroomMessage().to_json())
            self.__state = SocketGameState.IN_WAITROOM

            is_full, players = await self.is_waitroom_full(message.game)
            if is_full:
                session_id = await self.on_game_init(players)
                await self.group_send("event_start_game", {"session_id": session_id})
        elif self.__state == SocketGameState.IN_WAITROOM:
            pass
        elif self.__state == SocketGameState.IN_GAME:
            await self.on_message(message)

    # Group events

    async def event_start_game(self, event):
        self.__state = SocketGameState.IN_GAME
        await self.on_start(event["session_id"])

    # Virtual functions

    @staticmethod
    async def on_game_init(players: List[int]) -> int:
        """Should return the pk of the game session"""
        raise NotImplementedError()

    async def on_start(self, session_id):
        raise NotImplementedError()

    async def on_message(self, message):
        raise NotImplementedError()

    async def on_disconnected(self):
        raise NotImplementedError()


    # Database functions

    @database_sync_to_async
    def remove_user_from_waitroom(self):
        room = WaitingRoom.objects.filter(users__pk__contains=self.user.pk).get()
        room.users.remove(self.user)
        room.save()

    @database_sync_to_async
    def add_user_to_waitroom(self, game) -> str:
        room, _ = WaitingRoom.objects.filter(game=game).get_or_create(game=game)
        room.users.add(self.user)
        room.save()

        return room.pk

    @database_sync_to_async
    def is_waitroom_full(self, game) -> Tuple[bool, List[int]]:
        """
        First result is boolean that means if the waitroom is full
        If the waitroom is full it's deleted and the second result is
        a list of the player ids, otherwise it's None
        """
        room = WaitingRoom.objects.filter(game=game).get()
        if len(room.users.all()) == 2:
            players = list(room.users.all().values_list("pk", flat=True))
            room.delete()
            return True, players
        return False, None
