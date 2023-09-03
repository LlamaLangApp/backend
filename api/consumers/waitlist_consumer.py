import json
from typing import List
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from api.consumers.helpers import SocketGameState
from api.consumers.messages import JoinedWaitroomMessage, WaitroomRequestMessage
from api.models import WaitingRoom
from django.contrib.auth import get_user_model

User = get_user_model()


class WaitListConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for managing game waitlist and game initialization.
    """

    EVENT_START_GAME = "event_start_game"

    # Websocket functions
    async def connect(self):
        if self.scope["user"].is_authenticated:
            self.user = self.scope["user"]
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
        try:
            message = json.loads(text_data)
        except json.JSONDecodeError:
            print("Message is not a valid json!")

        # TODO: security
        if self.__state == SocketGameState.JUST_CONNECTED:
            await self.handle_just_connected(message)
        elif self.__state == SocketGameState.IN_WAITROOM:
            pass
        elif self.__state == SocketGameState.IN_GAME:
            await self.on_message(message)

    async def handle_just_connected(self, message):
        message = WaitroomRequestMessage(game=message["game"])

        await self.join_game_waitlist(message.game)
        await self.try_init_game(message)

    async def join_game_waitlist(self, game):
        room_pk = await self.add_user_to_waitroom(game)

        self.__group_name = str(room_pk)
        await self.channel_layer.group_add(self.__group_name, self.channel_name)

        await self.send(JoinedWaitroomMessage().to_json())
        self.__state = SocketGameState.IN_WAITROOM

    async def try_init_game(self, message):
        '''
        If waitroom is full, init game and send start game events to players.
        '''

        is_full, players = await self.is_waitroom_full(message.game)

        if is_full:
            session_id = await self.on_game_init(players)
            await self.send_start_game_event(session_id)

    # Group events
    async def send_start_game_event(self, session_id):
        '''
        Send start game event to all connected users.
        '''
        await self.group_send(self.EVENT_START_GAME, {"session_id": session_id})

    async def event_start_game(self, event):
        '''
        Start game for user.
        '''
        self.__state = SocketGameState.IN_GAME
        await self.on_start(event["session_id"])

    # Group Utils
    async def group_send(self, event_name, args):
        '''
        Broadcasts messages to every connected user in group (waitroom).
        Triggers event handler method.
        '''
        await self.channel_layer.group_send(
            self.__group_name,
            {"type": event_name.replace("_", "."), **args},
        )

    # Virtual functions, implementation depends on game type
    @staticmethod
    async def on_game_init(players: List[User]) -> int:
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
    def is_waitroom_full(self, game):
        """
        First result value is True if the waitroom is full, False otherwise
        If the waitroom is full it's deleted and the second result is
        a list of the player ids, otherwise it's None
        """
        if self.room.is_full():
            players = list(self.room.users.all())
            self.room.delete()
            self.room = None
            return True, players

        return False, None

    @database_sync_to_async
    def remove_user_from_waitroom(self):
        self.room.remove_user(self.user)
        self.room = None

    @database_sync_to_async
    def add_user_to_waitroom(self, game):
        self.get_waitroom(game)
        self.room.add_user(self.user)

        return self.room.pk

    def get_waitroom(self, game):
        room, _ = WaitingRoom.objects.filter(game=game).get_or_create(game=game)
        self.room = room



