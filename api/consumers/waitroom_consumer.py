import asyncio
import json
from typing import Optional, List
from channels.db import database_sync_to_async
from channels.consumer import AsyncConsumer
from channels.generic.websocket import AsyncWebsocketConsumer
from api.consumers.helpers import SocketGameState
from api.consumers.messages import GameStartingMessage, JoinedWaitroomMessage, PlayerInvitationMessage, PlayerJoinedMessage, PlayerLeftMessage, StartGameMessage, WaitroomCanceledMessage, WaitroomMessageType, WaitroomRequestMessage
from api.consumers.updates_consumer import WaitroomInvitation, send_update_async
from api.models import ActiveMultiplayerGame, CustomUser, WaitingRoom, WordSet
from django.contrib.auth import get_user_model

User = get_user_model()

DEFAULT_TIMEOUT = 10

class WaitListConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for managing game wait-list and game initialization.
    """

    # Websocket functions
    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.user: CustomUser = None
        self.state: SocketGameState = None
        self.group_name: str = None
        # Valid only when self.state == SocketGameState.IN_WAITROOM
        self.waitroom: WaitingRoom = None
        self.active_game: ActiveMultiplayerGame = None
        self.background_tasks = set()

    async def connect(self):
        if self.scope["user"].is_authenticated:
            self.user = self.scope["user"]
            self.state = SocketGameState.JUST_CONNECTED
            await self.accept()
        else:
            self.user = None
            self.state = None
            await self.close()

    async def disconnect(self, close_code):
        if not self.state or not self.group_name:
            return

        if self.state == SocketGameState.IN_WAITROOM:
            was_owner: bool = await remove_user_from_waitroom(self.user, self.waitroom)
            if was_owner:
                await self.group_send(self.owner_left_event)
        elif self.state == SocketGameState.IN_GAME:
            await self.handle_disconnection()
            await self.check_if_round_ended()
        
        await self.group_send(self.player_left_event, username=self.user.username)
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            if self.state == SocketGameState.JUST_CONNECTED:
                message = WaitroomRequestMessage.from_json(text_data)
                await self.handle_waitroom_request(message)
            elif self.state == SocketGameState.IN_WAITROOM:
                try:
                    message = PlayerInvitationMessage.from_json(text_data)
                except:
                    pass
                try:
                    message = StartGameMessage.from_json(text_data)
                except:
                    pass
                
                if message is None:
                    raise RuntimeError()
                
                if self.waitroom.owner != self.user:
                    await self.send_error("Only waitroom owner can send invitations")
                    return
                
                if message.type == WaitroomMessageType.PLAYER_INVITATION:
                    await send_update_async(str(message.user_id), 
                                            WaitroomInvitation(game=self.game_name(), 
                                                               waitroom=self.waitroom.pk,
                                                               username=self.user.username,
                                                               wordset_id=self.waitroom.wordset.pk))
                elif message.type == WaitroomMessageType.START_GAME:
                    await self.run_in_background(self.check_if_game_should_start(True))
                else:
                    raise RuntimeError()
            elif self.state == SocketGameState.IN_GAME:
                await self.on_message(text_data)
        except RuntimeError:
            await self.send_error("Invalid message")


    async def handle_waitroom_request(self, message: WaitroomRequestMessage) -> None:
        if message.owned_room and (message.as_owner or message.wordset_id):
            await self.send_error("Other fields can't be set if owned_room is set")
            return
        elif not message.owned_room and not message.wordset_id:
            await self.send_error("You must set wordset_id or owned_room")
            return

        if message.owned_room:
            self.waitroom = await get_owned_waitroom_for_user(self.user, message.owned_room)
            if not self.waitroom:
                await self.send_error("Owned waitroom doesn't exist")
                return
        else:
            try:
                wordset: WordSet = await get_wordset(message.wordset_id)
            except ValueError:
                await self.send_error("Wordset does not exist")
                return

            locked = await is_wordset_locked_for_user(self.user, wordset)

            if locked:
                await self.send_error("Wordset is locked for you")
                return
            
            self.waitroom = await get_waitroom_for_user(self.user, self.game_name(), 
                                                        wordset, message.as_owner)
    
        self.group_name = "WaitListConsumer_" + str(self.waitroom.pk)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        joined_message = JoinedWaitroomMessage(
            usernames=await get_usernames_in_waitroom(self.waitroom),
            waitroom=self.waitroom.pk,
        )
        await self.send(joined_message.to_json())
        await self.group_send(self.player_joined_event, username=self.user.username)
        self.state = SocketGameState.IN_WAITROOM
        
        await self.run_in_background(self.check_if_game_should_start(False))

    async def player_joined_event(self, event):
        username = event["username"]
        if username == self.user.username:
            return
        await self.send(PlayerJoinedMessage(username=username).to_json())
    
    async def player_left_event(self, event):
        username = event["username"]
        if username == self.user.username:
            return
        await self.send(PlayerLeftMessage(username=username).to_json())

    async def owner_left_event(self, event):
        await self.send(WaitroomCanceledMessage().to_json())
        await self.close()
        self.state = None

    async def game_started_event(self, event):
        self.state = SocketGameState.IN_GAME
        self.waitroom = None
        await self.load_active_game(event["session_id"])
        await self.send(GameStartingMessage().to_json())
        await self.on_game_started()

    async def check_if_round_ended(self):
        if not await have_all_players_answered(self.active_game):
            return
        await self.run_in_background(self.progress_round(1 + await get_current_round(self.active_game)))

    async def check_if_game_should_start(self, triggered_by_owner):
        if not await is_waitroom_full(self.waitroom.pk, triggered_by_owner):
            return
        await asyncio.sleep(1)
        if not await is_waitroom_full(self.waitroom.pk, triggered_by_owner):
            return

        session_id = await self.create_session_from_waiting_room(self.waitroom)
        await self.group_send(self.game_started_event, session_id=session_id)
        await asyncio.sleep(DEFAULT_TIMEOUT)
        await self.run_in_background(self.progress_round(1))
    
    async def progress_round(self, next_round):
        if not await is_valid_round_progression(self.active_game.pk, next_round):
            return
        
        await self.group_send(self.end_round_event)
        await asyncio.sleep(1)
        await self.group_send(self.new_round_event)
        await asyncio.sleep(DEFAULT_TIMEOUT)
        await self.run_in_background(self.progress_round(next_round + 1))

    # Virtual functions, implementation depends on game type
    @staticmethod
    def game_name() -> str:
        raise NotImplementedError()
    
    @staticmethod
    @database_sync_to_async
    def create_session_from_waiting_room(room: WaitingRoom) -> str:
        raise NotImplementedError()

    @database_sync_to_async
    def load_active_game(self, session_id):
        raise NotImplementedError()

    async def on_game_started(self):
        raise NotImplementedError()

    async def on_message(self, message):
        raise NotImplementedError()
    
    async def handle_disconnection(self):
        raise NotImplementedError()

    async def end_round_event(self, event):
        raise NotImplementedError()

    async def new_round_event(self, event):
        raise NotImplementedError()

    # Utils
    async def group_send(self, event_handler, **kwargs):
        """
        Broadcasts messages to every connected user in group (wait-room).
        Triggers event handler method.
        """
        await self.channel_layer.group_send(
            self.group_name,
            {"type": event_handler.__name__.replace("_", "."), **kwargs},
        )
    
    async def send_error(self, error_message):
        await self.send(json.dumps({"error": error_message}))
    
    async def run_in_background(self, coroutine):
        """
        Runs an async function in the background. Useful in cases where
        a function sleeps, because a websocket only starts processing
        more messages when it finishes processing a message.
        So if the message handler sleeps we can't process more message.
        """
        task = asyncio.create_task(coroutine)
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)

# Database helpers
@database_sync_to_async
def is_waitroom_full(room_pk: str, triggered_by_owner: bool) -> bool:
    try:
        room = WaitingRoom.objects.get(pk=room_pk)
    except:
        return False
    # We wait for the owner to start the game
    if room.owner and not triggered_by_owner:
        return False
    return room.users.count() == 2

@database_sync_to_async
def is_valid_round_progression(active_game_pk, next_round):
    active_game = ActiveMultiplayerGame.objects.get(pk=active_game_pk)
    if active_game.all_rounds_played():
        return False
    
    if active_game.round_count + 1 == next_round:
        active_game.progress_round()
        return True
    
    return False

@database_sync_to_async
def get_usernames_in_waitroom(room: WaitingRoom) -> List[str]:
    return [user.username for user in room.users.all()]

@database_sync_to_async
def get_waitroom_for_user(user: CustomUser, game: str, wordset: WordSet, as_owner: bool) -> WaitingRoom:
    if as_owner:
        room = WaitingRoom.objects.create(game=game, wordset=wordset, owner=user)
    else:
        room, _ = WaitingRoom.objects.filter(game=game, wordset=wordset, owner=None) \
            .get_or_create(game=game, wordset=wordset)
    room.users.add(user)
    room.save()
    return room

@database_sync_to_async
def get_owned_waitroom_for_user(user: CustomUser, room_id: str) -> Optional[WaitingRoom]:
    try:
        room = WaitingRoom.objects.get(pk=int(room_id))
    except:
        return None
    room.users.add(user)
    room.save()
    return room

@database_sync_to_async
def remove_user_from_waitroom(user: CustomUser, waitroom: WaitingRoom) -> bool:
    waitroom.users.remove(user)
    waitroom.save()

    if waitroom.owner == user:
        waitroom.delete()
        return True

    return False

@database_sync_to_async
def get_wordset(wordset_id: str):
    try:
        wordset = WordSet.objects.get(id=wordset_id)
        return wordset
    except WordSet.DoesNotExist:
        raise ValueError("Wordset does not exist")

@database_sync_to_async
def is_wordset_locked_for_user(user: CustomUser, wordset: WordSet) -> bool:
    return wordset.is_locked_for_user(user)

@database_sync_to_async
def have_all_players_answered(game: ActiveMultiplayerGame) -> int:
    return game.have_all_players_answered()

@database_sync_to_async
def get_current_round(game: ActiveMultiplayerGame) -> int:
    return game.round_count