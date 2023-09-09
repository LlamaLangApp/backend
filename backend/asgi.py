"""
ASGI config for backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.middleware import BaseMiddleware
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import AnonymousUser
from channels.db import database_sync_to_async
from django.core.asgi import get_asgi_application
from django.urls import path

from api.consumers import race_consumer


@database_sync_to_async
def returnUser(auth_token):
    try:
        user = Token.objects.get(key=auth_token).user
    except:
        user = AnonymousUser()
    return user


class TokenAuthMiddleWare(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        scope = dict(scope)

        try:
            auth_token = str(
                dict(scope["headers"])[b"authorization"], encoding="UTF-8"
            ).removeprefix("Token ")
        except:
            auth_token = None

        scope["user"] = await returnUser(auth_token)

        return await super().__call__(scope, receive, send)


urlpatterns = [
    path("race/", race_consumer.RaceConsumer.as_asgi()),
]

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": TokenAuthMiddleWare(URLRouter(urlpatterns)),
    }
)
