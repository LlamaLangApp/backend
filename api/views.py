# views.py
import json

from rest_framework import generics
from django.db import models
from django.http import HttpResponseBadRequest
from rest_framework import viewsets, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError

from api.serializers import (
    TranslationSerializer,
    MemoryGameSessionSerializer, FallingWordsGameSessionSerializer, MyProfileSerializer, FriendRequestSerializer,
    FriendshipSerializer, TranslationUserAccuracyCounterSerializer, WordSetSerializer, WordSetWithTranslationSerializer
)
from api.models import Translation, WordSet, MemoryGameSession, FallingWordsGameSession, FriendRequest, \
    Friendship, TranslationUserAccuracyCounter
from rest_framework import status
from rest_framework.parsers import MultiPartParser
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

        serialized_data = WordSetWithTranslationSerializer(wordset,  context={'request': request}).data

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


class UpdateProfileView(generics.UpdateAPIView):
    serializer_class = MyProfileSerializer
    parser_classes = (MultiPartParser,)
    permission_classes = [permissions.IsAuthenticated]

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


class FriendRequestViewSet(viewsets.ModelViewSet):
    queryset = FriendRequest.objects.all()
    serializer_class = FriendRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=["get"])
    def received(self, request, *args, **kwargs):
        queryset = FriendRequest.objects.filter(receiver=self.request.user)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def sent(self, request, *args, **kwargs):
        queryset = FriendRequest.objects.filter(sender=self.request.user)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        if Friendship.objects.filter(user=self.request.user, friend=serializer.validated_data['receiver']).exists() \
                and Friendship.objects.filter(user=serializer.validated_data['receiver'],
                                              friend=self.request.user).exists():
            raise ValidationError('You are already friends')

        if FriendRequest.objects.filter(sender=self.request.user,
                                        receiver=serializer.validated_data['receiver']).exists():
            raise ValidationError('You have already sent a friend request to this user')

        if FriendRequest.objects.filter(sender=serializer.validated_data['receiver'],
                                        receiver=self.request.user).exists():
            raise ValidationError('This user has already sent you a friend request')

        if serializer.validated_data['receiver'] == self.request.user:
            raise ValidationError('You cannot send a friend request to yourself')

        serializer.save(sender=self.request.user)

    @action(detail=True, methods=['patch'])
    def accept(self, request, pk=None):
        # no body needed
        friend_request = self.get_object()

        if friend_request.receiver.id == request.user.id:
            Friendship.objects.create(user=friend_request.sender, friend=friend_request.receiver)
            Friendship.objects.create(user=friend_request.receiver, friend=friend_request.sender)
            friend_request.delete()
            return Response({'detail': 'Friend request accepted.'}, status=status.HTTP_200_OK)
        else:
            return Response({'detail': 'You do not have permission to accept this request.'},
                            status=status.HTTP_403_FORBIDDEN)

    @action(detail=True, methods=['patch'])
    def reject(self, request, pk=None):
        # no body needed
        friend_request = self.get_object()

        if friend_request.receiver == request.user:
            friend_request.delete()
            return Response({'detail': 'Friend request rejected.'}, status=status.HTTP_200_OK)
        else:
            return Response({'detail': 'You do not have permission to reject this request.'},
                            status=status.HTTP_403_FORBIDDEN)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.sender == request.user:  # Check if the requester is the creator
            instance.delete()
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


