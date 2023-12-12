from dataclasses import asdict, dataclass
import json
from typing import List, Union
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from asgiref.sync import async_to_sync
from django.contrib.auth.models import AbstractUser
from channels.layers import get_channel_layer
from api.models import WaitingRoom

class UpdatesConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope["user"].is_authenticated:
            await self.channel_layer.group_add(self.group_name(), self.channel_name)
            await self.accept()
            for message in await get_invites_for_a_user(self.scope["user"]):
                await self.send(json.dumps(asdict(message)))
        else:
            await self.close()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group_name(), self.channel_name)

    def group_name(self):
        return group_name_for_user(self.scope["user"])
    
    async def update(self, event):
        await self.send(event["payload"])
    

def group_name_for_user(user: AbstractUser):
    return "UpdatesConsumer" + str(user.pk)

async def send_update_async(user: Union[AbstractUser, str], payload: any):
    """Payload must be a dataclass"""
    channel_layer = get_channel_layer()
    payload_str = json.dumps(asdict(payload))
    await channel_layer.group_send(
        ("UpdatesConsumer" + user) if isinstance(user, str) else group_name_for_user(user),
        {"type": "update", "payload": payload_str},
    )

@database_sync_to_async
def get_invites_for_a_user(user: AbstractUser) -> List["WaitroomInvitation"]:
    def waitingroom_to_invitation(room: WaitingRoom) -> WaitroomInvitation:
        return WaitroomInvitation(username=room.owner.username,
                                  wordset_id=room.wordset.pk,
                                  game=room.game,
                                  waitroom=room.pk)
    
    messages = map(waitingroom_to_invitation, user.invited_to.all())
    user.invited_to.clear()
    return list(messages)

@dataclass
class FriendStatusUpdate:
    type: str = "friend_status_update"

@dataclass
class WaitroomInvitation:
    username: str
    wordset_id: str
    game: str
    waitroom: str
    type: str = "waitroom_invitation"

def send_update(user: Union[AbstractUser, str], payload: any):
    async_to_sync(send_update_async)(user, payload)