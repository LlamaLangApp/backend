# views.py
import json
from datetime import datetime, timezone

from rest_framework import viewsets, permissions, status, generics
from rest_framework.decorators import action

from api.serializers import (
    TranslationSerializer,
    WordSetSerializer,
    MemoryGameSessionSerializer, FallingWordsGameSessionSerializer, MyProfileSerializer
)
from api.models import Translation, WordSet, MemoryGameSession, FallingWordsGameSession, CustomUser
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response


class TranslationReadOnlySet(viewsets.ReadOnlyModelViewSet):
    queryset = Translation.objects.all()
    serializer_class = TranslationSerializer
    permission_classes = [permissions.IsAuthenticated]


class WordSetReadOnlySet(viewsets.ReadOnlyModelViewSet):
    queryset = WordSet.objects.all()
    serializer_class = WordSetSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=["get"])
    def translations(self, request, pk=None):
        limit = request.query_params.get("limit")
        wordset = self.get_object()

        if limit:
            translations = wordset.words.order_by("?")[: int(limit)]
            serializer = TranslationSerializer(translations, many=True)
            return Response(serializer.data)
        return Response(TranslationSerializer(wordset.words.all(), many=True).data)


class BaseGameSessionViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "head", "options"]
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        wordset = self.request.query_params.get("wordset", None)
        if wordset:
            return self.queryset.filter(wordset=wordset)
        return self.queryset.all()

    def create(self, request):
        user = request.user

        body = json.loads(request.body)
        wordset = WordSet.objects.get(pk=body["wordset"])

        timestamp = datetime.fromtimestamp(
            int(body["timestamp"]) / 1000.0, tz=timezone.utc
        )

        session_data = {
            "user": user,
            "wordset": wordset,
            "score": body["score"],
            "accuracy": body["accuracy"],
            "duration": body["duration"],
            "timestamp": timestamp,
        }

        instance = self.queryset.model(**session_data)
        instance.save()

        serializer = self.serializer_class(instance)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class MemoryGameSessionViewSet(BaseGameSessionViewSet):
    queryset = MemoryGameSession.objects.all()
    serializer_class = MemoryGameSessionSerializer


class FallingWordsSessionViewSet(BaseGameSessionViewSet):
    queryset = FallingWordsGameSession.objects.all()
    serializer_class = FallingWordsGameSessionSerializer


class UpdateProfileView(generics.UpdateAPIView):
    serializer_class = MyProfileSerializer
    parser_classes = (MultiPartParser,)

    def put(self, request, *args, **kwargs):
        instance = self.request.user
        serializer = self.get_serializer(instance, data=request.data, partial=True)

        if serializer.is_valid():
            avatar = request.data.get('avatar')
            if avatar:
                user_id = instance.id
                new_avatar_name = f'user_{user_id}.jpg'

                avatar.name = new_avatar_name

            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)