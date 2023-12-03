from dataclasses import asdict, dataclass
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import async_to_sync
from django.contrib.auth.models import AbstractUser
from channels.layers import get_channel_layer

class UpdatesConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope["user"].is_authenticated:
            await self.channel_layer.group_add(self.group_name(), self.channel_name)
            await self.accept()
        else:
            await self.close()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group_name(), self.channel_name)

    def group_name(self):
        return group_name_for_user(self.scope["user"])
    
    async def update(self, event):
        await self.send(event["payload"])
    

def group_name_for_user(user: AbstractUser):
    return str(user.pk)

async def _send_update_async(user: AbstractUser, payload: any):
    """Payload must be a dataclass"""
    channel_layer = get_channel_layer()
    print(asdict(payload))
    payload_str = json.dumps(asdict(payload))
    await channel_layer.group_send(
        group_name_for_user(user),
        {"type": "update", "payload": payload_str},
    )

@dataclass
class FriendStatusUpdate:
    type: str = "friend_status_update"

def send_update(user: AbstractUser, payload: any):
    async_to_sync(_send_update_async)(user, payload)