# views.py
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from api.serializers import (
    TranslationSerializer,
    WordSetSerializer,
    MemoryGameSessionSerializer,
)
from api.models import Translation, WordSet, MemoryGameSession, FallingWordsGameSession
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


class MemoryGameSessionViewSet(viewsets.ModelViewSet):
    queryset = MemoryGameSession.objects.all()
    serializer_class = MemoryGameSessionSerializer
    http_method_names = ["get", "post", "head", "options"]
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        wordset = self.request.query_params.get("wordset", None)

        if wordset:
            return MemoryGameSession.objects.filter(wordset=wordset)

        return MemoryGameSession.objects.all()


class FallingWordsSessionViewSet(viewsets.ModelViewSet):
    queryset = FallingWordsGameSession.objects.all()
    serializer_class = FallingWordsGameSessionSerializer
    http_method_names = ["get", "post", "head", "options"]
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        wordset = self.request.query_params.get("wordset", None)

        if wordset:
            return FallingWordsGameSession.objects.filter(wordset=wordset)

        return FallingWordsGameSession.objects.all()