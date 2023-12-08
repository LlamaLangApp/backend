# views.py
import json

import uuid
from django.core.files.storage import default_storage
from django.db.models import Subquery, OuterRef
from django.db.models.functions import Coalesce
from rest_framework import generics
from django.db import models
from django.http import HttpResponseBadRequest
from rest_framework import viewsets, permissions
from rest_framework.decorators import action, api_view, permission_classes, parser_classes
from rest_framework.exceptions import ValidationError
from api.consumers.updates_consumer import FriendStatusUpdate, send_update
from api.helpers import calculate_current_week_start
from django.db.models import OuterRef, Subquery, Sum, Value, IntegerField, F, ExpressionWrapper
from api.serializers import (
    TranslationSerializer,
    MemoryGameSessionSerializer, FallingWordsGameSessionSerializer, MyProfileSerializer, FriendRequestSerializer,
    FriendshipSerializer, TranslationUserAccuracyCounterSerializer, WordSetSerializer, WordSetWithTranslationSerializer
)
from api.models import CustomUser, Translation, WordSet, MemoryGameSession, FallingWordsGameSession, FriendRequest, \
    Friendship, TranslationUserAccuracyCounter, RaceGameSession, ScoreHistory
from rest_framework import status
from rest_framework.parsers import FileUploadParser
from rest_framework.response import Response
from datetime import datetime, timezone, timedelta


class TranslationViewSet(viewsets.ModelViewSet):
    queryset = Translation.objects.all()
    serializer_class = TranslationSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=["put"])
    def toggle_star(self, request, pk=None):
        translation = self.get_object()
        user = request.user

        if translation.starred_by.filter(id=user.id).exists():
            translation.starred_by.remove(user)
        else:
            translation.starred_by.add(user)
        translation.save()

        star = translation.starred_by.filter(id=user.id).exists()

        return Response({
            'id': translation.id,
            'english': translation.english,
            'polish': translation.polish,
            'star': star
        })

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        user = request.user

        serialized_data = []
        for translation in queryset:
            star = translation.starred_by.filter(id=user.id).exists()
            serialized_data.append({
                'id': translation.id,
                'english': translation.english,
                'polish': translation.polish,
                'star': star,
            })

        return Response(serialized_data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user

        star = instance.starred_by.filter(id=user.id).exists()

        return Response({
            'id': instance.id,
            'english': instance.english,
            'polish': instance.polish,
            'star': star,
        })


class WordSetReadOnlySet(viewsets.ReadOnlyModelViewSet):
    queryset = WordSet.objects.all()
    serializer_class = WordSetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = WordSetSerializer(instance, context={'request': request})
        return Response(serializer.data)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = WordSetSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def translations(self, request, pk=None):
        limit = request.query_params.get("limit")
        wordset = self.get_object()

        if not wordset:
            return Response(status=status.HTTP_404_NOT_FOUND, data={'message': "Wordset not found."})

        serialized_data = WordSetWithTranslationSerializer(wordset, context={'request': request}).data

        if serialized_data.get('locked'):
            return Response(status=status.HTTP_403_FORBIDDEN, data={'message': "Wordset is locked."})

        if limit:
            serialized_data['words'] = serialized_data['words'][:int(limit)]

        return Response(TranslationSerializer(serialized_data['words'], many=True).data)


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
    permission_classes = [permissions.IsAuthenticated]


class FallingWordsSessionViewSet(BaseGameSessionViewSet):
    queryset = FallingWordsGameSession.objects.all()
    serializer_class = FallingWordsGameSessionSerializer
    permission_classes = [permissions.IsAuthenticated]


@api_view(["POST"])
@permission_classes((permissions.IsAuthenticated,))
@parser_classes((FileUploadParser,))
def uploadAvatar(request):
    file = request.FILES["file"]
    extension = file.name.split(".")[-1]

    path = f"user/avatars/{str(uuid.uuid4())}.{extension}"

    with default_storage.open(path, "wb+") as destination:
        for chunk in file.chunks():
            destination.write(chunk)

    default_image_path = CustomUser._meta.get_field('avatar').get_default()
    current_url = request.user.avatar.url.removeprefix('/media/')
    if default_image_path != current_url:
        default_storage.delete(current_url)

    request.user.avatar = path
    request.user.save()

    return Response(status=status.HTTP_200_OK)

@api_view(['POST'])
def get_scoreboard(request):
    body = json.loads(request.body)
    period = body["period"]
    scoreboard_type = body.get("scoreboard_type", "global")  # Default to global if not provided

    if not period:
        return HttpResponseBadRequest(
            f"Body must contain 'period'. Body received: {body}"
        )

    objects = ScoreHistory.objects

    if period == "all_time":
        pass
    elif period == "this_week":
        start_of_the_week = calculate_current_week_start()
        objects = objects.filter(timestamp__gte=start_of_the_week)
    else:
        return HttpResponseBadRequest("Unknown period")

    agg = Sum("score_gained", default=0)

    all_scores = None
    if scoreboard_type == "global":
        all_scores = (
            CustomUser.objects
            .annotate(
                points=ExpressionWrapper(
                    Coalesce(Subquery(
                        ScoreHistory.objects
                        .filter(user=OuterRef('pk'))
                        .values('user')
                        .annotate(score=agg)
                        .values('score')
                    ), Value(0)),
                    output_field=IntegerField()
                )
            )
            .values('username', 'points')
            .order_by("-points")
        )
    elif scoreboard_type == "friends":
        friends = Friendship.objects.filter(user=request.user).values_list('friend', flat=True)
        all_scores = (
            CustomUser.objects
            .filter(pk__in=friends)
            .annotate(
                points=ExpressionWrapper(
                    Coalesce(Subquery(
                        ScoreHistory.objects
                        .filter(user=OuterRef('pk'))
                        .values('user')
                        .annotate(score=agg)
                        .values('score')
                    ), Value(0)),
                    output_field=IntegerField()
                )
            )
            .values('username', 'points')
            .order_by("-points")
        )
    else:
        return HttpResponseBadRequest("Unknown scoreboard type")

    ranked_scores = []
    current_place = 1
    previous_score = None
    for score in all_scores:
        if previous_score is not None and score["points"] < previous_score["points"]:
            current_place += 1
        ranked_scores.append({"place": current_place, **score})
        previous_score = score

    user_result = None
    if request.user.is_authenticated:
        user_result = next((score for score in ranked_scores if score["username"] == request.user.username), None)

    top_100_places = [ranked_score for ranked_score in ranked_scores if ranked_score["place"] <= 100]

    return Response(data={"user": user_result, "top_100": top_100_places})

@api_view(["POST"])
@permission_classes((permissions.IsAuthenticated,))
def get_user_statistics(request):
    user = request.user
    body = json.loads(request.body)
    game, start, end = (
        body["game"],
        body["start"],
        body["end"],
    )

    if not game or not start or not end:
        return HttpResponseBadRequest(
            "Body must contains 'game', 'start' and 'end'"
        )

    objects = None
    if game == "memory":
        objects = MemoryGameSession.objects
    elif game == "race":
        objects = RaceGameSession.object
    elif game == "falling_words":
        objects = FallingWordsGameSession.objects

    if not objects:
        return HttpResponseBadRequest("Unknown game")

    objects = objects.filter(user=user, timestamp__range=(start, end))
    objects = objects.extra({'created_day': "date(timestamp)"})
    results = objects.values('created_day').annotate(count=models.Count('id'))

    return Response(data=list(results))


class FriendRequestViewSet(viewsets.ModelViewSet):
    queryset = FriendRequest.objects.all()
    serializer_class = FriendRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=["get"])
    def received(self, request, *args, **kwargs):
        queryset = FriendRequest.objects.filter(receiver=self.request.user)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def sent(self, request, *args, **kwargs):
        queryset = FriendRequest.objects.filter(sender=self.request.user)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        user = self.request.user
        receiver = serializer.validated_data['receiver']
        if Friendship.objects.filter(user=user, friend=receiver).exists() \
                and Friendship.objects.filter(user=receiver, friend=user).exists():
            raise ValidationError('You are already friends')

        if FriendRequest.objects.filter(sender=user, receiver=receiver).exists():
            raise ValidationError('You have already sent a friend request to this user')

        if FriendRequest.objects.filter(sender=receiver, receiver=user).exists():
            raise ValidationError('This user has already sent you a friend request')

        if receiver == user:
            raise ValidationError('You cannot send a friend request to yourself')

        serializer.save(sender=self.request.user)
        send_update(receiver, FriendStatusUpdate())

    @action(detail=True, methods=['patch'])
    def accept(self, request, pk=None):
        # no body needed
        friend_request = self.get_object()

        if friend_request.receiver.id == request.user.id:
            friendship_one_side = Friendship.objects.create(user=friend_request.sender, friend=friend_request.receiver)
            Friendship.objects.create(user=friend_request.receiver, friend=friend_request.sender)
            friend_request.delete()
            send_update(friend_request.sender, FriendStatusUpdate())
            return Response({'detail': 'Friend request accepted.', 'friendship_id': friendship_one_side.pk},
                            status=status.HTTP_200_OK)
        else:
            return Response({'detail': 'You do not have permission to accept this request.'},
                            status=status.HTTP_403_FORBIDDEN)

    @action(detail=True, methods=['patch'])
    def reject(self, request, pk=None):
        # no body needed
        friend_request = self.get_object()

        if friend_request.receiver == request.user:
            friend_request.delete()
            send_update(friend_request.sender, FriendStatusUpdate())
            return Response({'detail': 'Friend request rejected.'}, status=status.HTTP_200_OK)
        else:
            return Response({'detail': 'You do not have permission to reject this request.'},
                            status=status.HTTP_403_FORBIDDEN)

    def destroy(self, request, *args, **kwargs):
        friend_request = self.get_object()

        # Check if the requester is the creator
        if friend_request.sender == request.user:
            friend_request.delete()
            send_update(friend_request.receiver, FriendStatusUpdate())
            return Response({'detail': 'Friend request deleted.'}, status=status.HTTP_204_NO_CONTENT)
        else:
            return Response({'detail': 'You do not have permission to delete this request.'},
                            status=status.HTTP_403_FORBIDDEN)


class FriendshipViewSet(viewsets.ModelViewSet):
    queryset = Friendship.objects.all()
    serializer_class = FriendshipSerializer
    permission_classes = [permissions.IsAuthenticated]

    http_method_names = ['get', 'delete', 'head', 'options']

    def perform_create(self, serializer):
        if Friendship.objects.filter(user=self.request.user, friend=serializer.validated_data['friend']).exists():
            raise ValidationError('You are already friends')

        serializer.save(user=self.request.user)

    def perform_destroy(self, instance):
        if instance.user != self.request.user and instance.friend != self.request.user:
            raise ValidationError('You do not have permission to delete this friendship')

        if Friendship.objects.filter(user=instance.friend, friend=instance.user).exists():
            Friendship.objects.filter(user=instance.friend, friend=instance.user).delete()

        instance.delete()

    def list(self, request, *args, **kwargs):
        friendships = Friendship.objects.filter(user=self.request.user)
        serializer = FriendshipSerializer(friendships, many=True)

        return Response(serializer.data)


class TranslationUserAccuracyCounterViewSet(viewsets.ModelViewSet):
    queryset = TranslationUserAccuracyCounter.objects.all()
    serializer_class = TranslationUserAccuracyCounterSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post']

    @action(detail=False, methods=['POST'], url_path='good-answer')
    def good_answer(self, request):
        user = request.user
        translation_id = request.data.get('translation')
        TranslationUserAccuracyCounter.increment_good_answer(user=user, translation_id=translation_id)

        return Response({'message': 'Good answer counter incremented successfully.'})

    @action(detail=False, methods=['POST'], url_path='bad-answer')
    def bad_answer(self, request):
        user = request.user
        translation_id = request.data.get('translation')
        TranslationUserAccuracyCounter.increment_bad_answer(user=user, translation_id=translation_id)

        return Response({'message': 'Bad answer counter incremented successfully.'})
