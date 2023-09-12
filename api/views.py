# views.py
import json
from django.db import models
from django.http import HttpResponseBadRequest
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action, api_view, permission_classes

from api.serializers import (
    TranslationSerializer,
    WordSetSerializer,
    MemoryGameSessionSerializer,
    FallingWordsGameSessionSerializer,
)
from api.models import Translation, WordSet, MemoryGameSession, FallingWordsGameSession
from rest_framework.response import Response
from datetime import datetime, timezone, timedelta


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

@api_view(["POST"])
@permission_classes((permissions.IsAuthenticated,))
def get_statistics(request):
    body = json.loads(request.body)
    game, period, statistic, aggregate = (
        body["game"],
        body["period"],
        body["statistic"],
        body["aggregate"],
    )

    if not game or not period or not statistic:
        return HttpResponseBadRequest(
            "Body must contains 'game', 'period' and 'statistic'"
        )

    objects = None
    if game == "memory":
        objects = MemoryGameSession.objects

    if not objects:
        return HttpResponseBadRequest("Unknown game")

    if period == "all_time":
        pass
    elif period == "this_week":
        current_time = datetime.utcnow()
        start_of_week = current_time - timedelta(days=current_time.weekday())
        end_of_week = start_of_week + timedelta(weeks=1)
        objects = objects.filter(timestamp__range=(start_of_week, end_of_week))
    else:
        return HttpResponseBadRequest("Unknown period")

    agg = None
    if aggregate == "sum":
        # TODO: I think this is an sql injection
        agg = models.Sum(statistic)
    elif aggregate == "avg":
        agg = models.Avg(statistic)
    elif aggregate == "min":
        agg = models.Min(statistic)
    elif aggregate == "count":
        agg = models.Count("id")
    else:
        return HttpResponseBadRequest("Unknown aggregate")

    result = objects.values(username=models.F("user__username")).annotate(stat=agg)

    return Response(data=list(result))
