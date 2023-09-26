# serializers.py
from django.db.models import Sum
from rest_framework import serializers

from api.helpers import calculate_current_week_start
from api.models import Translation, WordSet, MemoryGameSession, FallingWordsGameSession, CustomUser, ScoreHistory, \
    Friendship, FriendRequest, AnswerCounter
from djoser.serializers import UserCreateSerializer, UserSerializer


class CustomUserCreateSerializer(UserCreateSerializer):
    class Meta(UserCreateSerializer.Meta):
        model = CustomUser
        fields = ('id', 'username', 'email', 'password', 'avatar')


class AnswerCounterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnswerCounter
        fields = ("translation", "user")


class CustomUserSerializer(UserSerializer):
    class Meta(UserSerializer.Meta):
        model = CustomUser
        read_only_fields = ('level', 'avatar')
        fields = ('id', 'username', 'level', 'avatar')


class MyProfileSerializer(serializers.ModelSerializer):
    avatar = serializers.ImageField(required=False)
    current_week_points = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        read_only_fields = ('level', 'current_week_points', 'score')
        fields = ('id', 'username', 'email', 'score', 'level', 'avatar', 'current_week_points')

    def get_current_week_points(self, obj):
        request = self.context.get('request')
        if request:
            current_week_start = calculate_current_week_start()
            current_week_points = ScoreHistory.objects.filter(
                user=request.user,
                date__gte=current_week_start
            ).aggregate(total_points=Sum('score_gained'))['total_points'] or 0

            return current_week_points
        return 0


class TranslationSerializer(serializers.ModelSerializer):
    star = serializers.SerializerMethodField()

    class Meta:
        model = Translation
        read_only_fields= ('id', 'english', 'polish')
        fields = ('id', 'english', 'polish', 'star')


class WordSetSerializer(serializers.ModelSerializer):
    class Meta:
        model = WordSet
        fields = '__all__'


class MemoryGameSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MemoryGameSession
        fields = '__all__'


class FallingWordsGameSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FallingWordsGameSession
        fields = '__all__'


class FriendAccountSerializer(UserSerializer):
    class Meta(UserSerializer.Meta):
        fields = ('id', 'username', 'email', 'level', 'avatar')


class FriendshipSerializer(serializers.ModelSerializer):
    friendship_id = serializers.IntegerField(source='id', read_only=True)
    friend = FriendAccountSerializer()

    class Meta:
        model = Friendship
        fields = ['friendship_id', 'friend']


class FriendRequestSerializer(serializers.ModelSerializer):
    accepted = serializers.BooleanField(required=False)

    class Meta:
        model = FriendRequest
        fields = '__all__'
