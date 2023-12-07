import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model

User = get_user_model()


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope["user"].is_anonymous:
            await self.close()
        else:
            await self.accept()
            user_id = self.scope["user"].id
            await self.channel_layer.group_add(
                f"user_{user_id}",
                self.channel_name
            )

    async def disconnect(self, close_code):
        user_id = self.scope["user"].id
        await self.channel_layer.group_discard(
            f"user_{user_id}",
            self.channel_name
        )

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json['message']

        print(f"Received message: {message}")

        # TESTS:
        # await self.user_notification("Hello")
        # await self.send(text_data=json.dumps({ 'message': message }))

    async def user_notification(self, event):
        await self.send(text_data=json.dumps({
            'notification': event
        }))

    @database_sync_to_async
    def get_user(self, user_id):
        return User.objects.get(pk=user_id)
