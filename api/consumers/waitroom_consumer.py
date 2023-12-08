import json
from typing import List
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from api.consumers.helpers import SocketGameState
from api.consumers.messages import JoinedWaitroomMessage, WaitroomRequestMessage
from api.models import WaitingRoom, WordSet
from django.contrib.auth import get_user_model

User = get_user_model()


class WaitListConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for managing game wait-list and game initialization.
    """

    EVENT_START_GAME = "event_start_game"

    # Websocket functions
    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.room = None
        self.user = None
        self.__group_name = None
        self.__state = None

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
            self.send_error_message("Invalid message format")

        # TODO: security
        if self.__state == SocketGameState.JUST_CONNECTED:
            await self.handle_just_connected(message)
        elif self.__state == SocketGameState.IN_WAITROOM:
            pass
        elif self.__state == SocketGameState.IN_GAME:
            await self.on_message(message)

    async def handle_just_connected(self, message):
        game = message["game"]
        wordset_id = message["wordset_id"]

        try:
            wordset = await self.check_if_wordset_exists(wordset_id)
        except ValueError:
            await self.send_error_message("Wordset does not exist")
            return

        locked = await self.is_wordset_locked_for_user(wordset)

        if locked:
            await self.send_error_message("Wordset is locked for you")
            return

        message = WaitroomRequestMessage(game=game, wordset=wordset.english)

        await self.join_game_waitroom(game, wordset)
        await self.try_init_game(message)

    @database_sync_to_async
    def check_if_wordset_exists(self, wordset_id):
        try:
            wordset = WordSet.objects.get(id=wordset_id)
            return wordset
        except WordSet.DoesNotExist:
            raise ValueError("Wordset does not exist")

    @database_sync_to_async
    def is_wordset_locked_for_user(self, wordset):
        return wordset.is_locked_for_user(self.user)

    async def join_game_waitroom(self, game, wordset):
        room_pk = await self.add_user_to_waitroom(game, wordset)

        self.__group_name = str(room_pk)
        await self.channel_layer.group_add(self.__group_name, self.channel_name)

        await self.send(JoinedWaitroomMessage().to_json())
        self.__state = SocketGameState.IN_WAITROOM

    async def try_init_game(self, message):
        """
        If wait-room is full, init game and send start game events to players.
        """

        is_full, players, wordset = await self.is_waitroom_full(message.game)

        if is_full:
            session_id = await self.on_game_init(players, wordset)
            await self.send_start_game_event(session_id)

    # Group events
    async def send_start_game_event(self, session_id):
        """
        Send start game event to all connected users.
        """
        await self.group_send(self.EVENT_START_GAME, {"session_id": session_id})

    async def event_start_game(self, event):
        """
        Start game for user.
        """
        self.__state = SocketGameState.IN_GAME
        await self.on_start(event["session_id"])

    # Group Utils
    async def group_send(self, event_name, args):
        """
        Broadcasts messages to every connected user in group (wait-room).
        Triggers event handler method.
        """
        await self.channel_layer.group_send(
            self.__group_name,
            {"type": event_name.replace("_", "."), **args},
        )

    # Virtual functions, implementation depends on game type
    @staticmethod
    async def on_game_init(players: List[User], wordset) -> int:
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
        First result value is True if the wait-room is full, False otherwise
        If the wait-room is full it's deleted and the second result is
        a list of the player ids, otherwise it's None
        """
        if self.room.is_full():
            players = list(self.room.users.all())
            wordset = self.room.wordset
            self.room.delete()
            self.room = None
            return True, players, wordset

        return False, None, None

    @database_sync_to_async
    def remove_user_from_waitroom(self):
        self.room.remove_user(self.user)
        self.room = None

    @database_sync_to_async
    def add_user_to_waitroom(self, game, wordset):
        self.get_waitroom(game, wordset)
        self.room.add_user(self.user)

        return self.room.pk

    def get_waitroom(self, game, wordset):
        room, _ = WaitingRoom.objects.filter(game=game, wordset=wordset).get_or_create(game=game, wordset=wordset)
        self.room = room

    async def send_error_message(self, error_message):
        await self.send(json.dumps({"error": error_message}))
        # close
        await self.disconnect(1000)
