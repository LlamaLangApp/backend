from dataclasses import asdict, dataclass
import json
from typing import List, Union, TYPE_CHECKING
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from asgiref.sync import async_to_sync
from django.contrib.auth.models import AbstractUser
from channels.layers import get_channel_layer
if TYPE_CHECKING:
    from api.models import WaitingRoom

class UpdatesConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope["user"].is_authenticated:
            await self.accept()
            await self.channel_layer.group_add(self.group_name(), self.channel_name)
            await self.trigger_sending_invitations(None)
        else:
            await self.close()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group_name(), self.channel_name)

    def group_name(self):
        return group_name_for_user(str(self.scope["user"].pk))
    
    async def trigger_friend_update(self, event):
        await self.send(FriendStatusUpdate().to_json())

    async def trigger_sending_invitations(self, event):
        message: WaitroomInvitations = await get_invites_for_a_user(self.scope["user"])
        await self.send(message.to_json())
        for invite in message.invitations:
            await self.channel_layer.group_add(
                group_name_for_waitroom(str(invite.waitroom)), self.channel_name)
    
    async def trigger_cancel_invitations(self, event):
        await self.channel_layer.group_discard(
                group_name_for_waitroom(str(event["waitroom"])), self.channel_name)
        await self.send(CancelWaitroomInvitations(waitroom=event["waitroom"]).to_json())


@database_sync_to_async
def get_invites_for_a_user(user: AbstractUser) -> "WaitroomInvitations":
    def waitingroom_to_invitation(room: "WaitingRoom") -> WaitroomInvitation:
        return WaitroomInvitation(username=room.owner.username,
                                  wordset_id=room.wordset.pk,
                                  game=room.game,
                                  waitroom=room.pk)
    
    invites = map(waitingroom_to_invitation, user.invited_to.all())
    return WaitroomInvitations(invitations=list(invites)) 

@dataclass
class UpdateMessage:
    def to_json(self):
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, text: str):
        return cls(**json.loads(text))

@dataclass
class FriendStatusUpdate(UpdateMessage):
    type: str = "friend_status_update"

@dataclass
class WaitroomInvitation:
    username: str
    wordset_id: str
    game: str
    waitroom: str

@dataclass
class WaitroomInvitations(UpdateMessage):
    invitations: List[WaitroomInvitation]
    type: str = "waitroom_invitation"

@dataclass 
class CancelWaitroomInvitations(UpdateMessage):
    waitroom: str
    type: str = "cancel_waitroom_invitation"

def group_name_for_user(user_id: str):
    return "UpdatesConsumer" + user_id

def group_name_for_waitroom(room_id: str):
    return "UpdatesForWaitingRoom" + room_id

async def send_update_async(user: Union[AbstractUser, str], event_handler, **kwargs):
    channel_layer = get_channel_layer()
    await channel_layer.group_send(
        group_name_for_user(user) if isinstance(user, str) else group_name_for_user(str(user.pk)),
        {"type": event_handler.__name__.replace("_", "."), **kwargs},
    )

def send_update(user: Union[AbstractUser, str], event_handler, **kwargs):
    async_to_sync(send_update_async)(user, event_handler, **kwargs)

async def send_waitroom_invitations_cancelation_async(waitroom: "WaitingRoom"):
    channel_layer = get_channel_layer()
    await channel_layer.group_send(
        group_name_for_waitroom(str(waitroom.pk)),
        {
            "type": UpdatesConsumer.trigger_cancel_invitations.__name__.replace("_", "."),
            "waitroom": waitroom.pk
        }
    )

def send_waitroom_invitations_cancelation(waitroom: "WaitingRoom"):
    async_to_sync(send_waitroom_invitations_cancelation_async)(waitroom)