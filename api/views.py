# views.py
from rest_framework import viewsets, permissions
from api.serializers import TranslationSerializer, WordSetSerializer, MemoryGameSessionSerializer
from api.models import Translation, WordSet, MemoryGameSession


class TranslationReadOnlySet(viewsets.ReadOnlyModelViewSet):
    queryset = Translation.objects.all()
    serializer_class = TranslationSerializer
    permission_classes = [permissions.IsAuthenticated]

class WordSetReadOnlySet(viewsets.ReadOnlyModelViewSet):
    queryset = WordSet.objects.all()
    serializer_class = WordSetSerializer
    permission_classes = [permissions.IsAuthenticated]


class MemoryGameSessionViewSet(viewsets.ModelViewSet):
    queryset = MemoryGameSession.objects.all()
    serializer_class = MemoryGameSessionSerializer
    http_method_names = ['get', 'post', 'head', 'options']
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        wordset = self.request.query_params.get('wordset', None)

        if wordset:
            return MemoryGameSession.objects.filter(wordset=wordset)

        return MemoryGameSession.objects.all()