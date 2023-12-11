# views.py
import json

import uuid
from django.core.files.storage import default_storage
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.http import HttpResponseBadRequest
from rest_framework import viewsets, permissions
from rest_framework.decorators import action, api_view, permission_classes, parser_classes
from rest_framework.exceptions import ValidationError
from api.consumers.updates_consumer import FriendStatusUpdate, send_update
from api.helpers import calculate_current_week_start
from django.db.models import OuterRef, Subquery, Sum, Value, IntegerField, ExpressionWrapper
from api.serializers import (
    TranslationSerializer,
    MemoryGameSessionSerializer, FallingWordsGameSessionSerializer, FriendRequestSerializer,
    FriendshipSerializer, WordSetSerializer, WordSetWithTranslationSerializer
)
from api.models import CustomUser, Translation, WordSet, MemoryGameSession, FallingWordsGameSession, FriendRequest, \
    Friendship, ScoreHistory, FindingWordsGameSession, RaceGameSession
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

        translation.refresh_from_db()

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

        return Response(serialized_data.get('words'))


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


def get_points_history_aggregate(agg):
    return ExpressionWrapper(
        Coalesce(Subquery(
            ScoreHistory.objects
            .filter(user=OuterRef('pk'))
            .values('user')
            .annotate(score=agg)
            .values('score')
        ), Value(0)),
        output_field=IntegerField()
    )


game_sessions_model_map = {
    "memory": MemoryGameSession,
    "race": RaceGameSession,
    "falling_words": FallingWordsGameSession,
    "finding_words": FindingWordsGameSession,
    # Add more games as needed
}


def get_game_sessions(user, game, start_date, end_date):
    if game in game_sessions_model_map.keys():
        game_model = game_sessions_model_map.get(game)
        if game_model:
            return game_model.objects.filter(user=user, timestamp__range=(start_date, end_date)) if start_date else game_model.objects.filter(user=user)
        else:
            return -1
    elif game == "all_games":
        # Sum all stats from all games
        game_sessions = []
        game_models = game_sessions_model_map.values()
        for model in game_models:
            game_sessions.extend(model.objects.filter(user=user, timestamp__range=(start_date, end_date)) if start_date else model.objects.filter(user=user))
        return game_sessions
    else:
        return -1


@api_view(['POST'])
@permission_classes((permissions.IsAuthenticated,))
def get_scoreboard(request):
    body = json.loads(request.body)
    period = body["period"]
    scoreboard_type = body.get("scoreboard_type", "global")  # Default to global if not provided

    if not period:
        return HttpResponseBadRequest(
            f"Body must contain 'period'. Body received: {body},"
        )

    objects = ScoreHistory.objects

    if period == "all_time":
        pass
    elif period == "this_week":
        start_of_the_week = calculate_current_week_start()
        objects = objects.filter(date__gte=start_of_the_week)
    else:
        return HttpResponseBadRequest("Unknown period type. Available periods: 'this_week', 'all_time'. ")

    agg = Sum("score_gained", default=0)

    all_scores = None
    if scoreboard_type == "global":
        all_scores = (
            CustomUser.objects
            .annotate(points=get_points_history_aggregate(agg))
            .values('username', 'points')
            .order_by("-points")
        )
    elif scoreboard_type == "friends":
        friends = Friendship.objects.filter(user=request.user).values_list('friend', flat=True)
        friends_and_user = list(friends) + [request.user.id]

        all_scores = (
            CustomUser.objects
            .filter(pk__in=friends_and_user)
            .annotate(points=get_points_history_aggregate(agg))
            .values('username', 'points')
            .order_by("-points")
        )
    else:
        return HttpResponseBadRequest("Unknown scoreboard type. Available types: 'friends', 'global")

    ranked_scores = []
    current_place = 1
    previous_score = None
    for score in all_scores:
        if previous_score is not None and score["points"] < previous_score["points"]:
            current_place += 1
        ranked_scores.append({"place": current_place, **score})
        previous_score = score

    user_result = next((score for score in ranked_scores if score["username"] == request.user.username), None)
    if scoreboard_type == "friends":
        user_score = ScoreHistory.objects.filter(user=request.user).aggregate(score=agg)["score"]
        user_place = len(ranked_scores) + 1 if previous_score and user_score < previous_score[
            "points"] else current_place
        user_result = {"place": user_place, "username": request.user.username, "points": user_score}

    top_100_places = [ranked_score for ranked_score in ranked_scores if ranked_score["place"] <= 100]

    return Response(data={"user": user_result, "top_100": top_100_places})


@api_view(["POST"])
@permission_classes((permissions.IsAuthenticated,))
def get_calendar_stats(request):
    user = request.user
    body = json.loads(request.body)
    game, month, year = body.get("game", None), body.get("month", datetime.today().month), body.get("year",
                                                                                                    datetime.today().year)

    if not all(isinstance(arg, int) for arg in [month, year]):
        return HttpResponseBadRequest("Invalid data types in the request body. All values should be integers.")

    start_date = datetime(year, month, 1)

    if start_date > datetime.now():
        return HttpResponseBadRequest("Future dates are not allowed.")

    end_date = start_date.replace(day=1, month=start_date.month % 12 + 1,
                                  year=start_date.year + start_date.month // 12) - timedelta(days=1)

    game_sessions = get_game_sessions(user, game, start_date, end_date)
    if game_sessions == -1:
        return HttpResponseBadRequest(
            "Invalid game name. Valid game names are: " + ", ".join(game_sessions_model_map.keys()) + "or 'all_games'.")

    all_days = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
    all_days_str = [day.strftime("%d").lstrip('0') for day in all_days]

    results = {day: 0 for day in all_days_str}
    for session in game_sessions:
        created_day = session.timestamp.date()
        created_day_str = created_day.strftime("%d").lstrip('0')
        results[created_day_str] += 1

    return Response(data={"calendar": results, "month": month, "year": year})


@api_view(["POST"])
@permission_classes((permissions.IsAuthenticated,))
def get_longest_streak(request):
    user = request.user
    body = json.loads(request.body)
    game = body.get("game", None)

    # Set the date range to the last year
    end_date = datetime.today()

    game_sessions = get_game_sessions(user, game, None, end_date)
    if game_sessions == -1:
        return HttpResponseBadRequest(
            "Invalid game name. Valid game names are: " + ", ".join(game_sessions_model_map.keys()) + "or 'all_games'.")

    if game_sessions:
        game_sessions = sorted(game_sessions, key=lambda session: session.timestamp)
        current_streak = 0
        longest_streak = 0
        current_streak_start = None
        longest_streak_start = None
        previous_date = None

        for session in game_sessions:
            current_date = session.timestamp.date()
            if previous_date is None or (current_date - previous_date).days == 1:
                if current_streak == 0:
                    current_streak_start = current_date
                current_streak += 1
            else:
                current_streak = 1
                current_streak_start = current_date

            if current_streak > longest_streak:
                longest_streak = current_streak
                longest_streak_start = current_streak_start

            previous_date = current_date

        longest_streak_end = longest_streak_start + timedelta(days=longest_streak - 1)

        return Response({
            "longest_streak": longest_streak,
            "start_date": longest_streak_start.strftime("%Y-%m-%d"),
            "end_date": longest_streak_end.strftime("%Y-%m-%d")
        })
    else:
        return HttpResponseBadRequest("Invalid input")


@api_view(["POST"])
@permission_classes((permissions.IsAuthenticated,))
def get_current_streak(request):
    user = request.user
    body = json.loads(request.body)
    game = body.get("game", None)

    end_date = datetime.today()

    game_sessions = get_game_sessions(user, game, None, end_date)
    if game_sessions == -1:
        return HttpResponseBadRequest(
            "Invalid game name. Valid game names are: " + ", ".join(game_sessions_model_map.keys()))

    if game_sessions:
        game_sessions = sorted(game_sessions, key=lambda session: session.timestamp)
        current_streak = 1 if game_sessions[-1].timestamp.date() == datetime.today().date() else 0

        for i in range(len(game_sessions) - 1, -1, -1):
            current_session = game_sessions[i]
            previous_session = game_sessions[i - 1]

            current_date = current_session.timestamp.date()
            previous_date = previous_session.timestamp.date()

            if (current_date - previous_date).days == 1:
                current_streak += 1
            else:
                break

        return Response({"current_streak": current_streak})
    else:
        return Response({"current_streak": 0})


@api_view(["POST"])
@permission_classes((permissions.IsAuthenticated,))
def get_game_points(request):
    user = request.user
    body = json.loads(request.body)
    game = body.get("game", None)

    end_date = datetime.today()

    game_sessions = get_game_sessions(user, game, None, end_date)
    if game_sessions == -1:
        return HttpResponseBadRequest(
            "Invalid game name. Valid game names are: " + ", ".join(game_sessions_model_map.keys()) + "or 'all_games'.")

    total_points = 0
    if game_sessions:
        for session in game_sessions:
            total_points += session.score

    return Response({"total_points": total_points})


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
