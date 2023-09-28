# serializers.py
from django.db.models import Sum
import base64
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
    avatar = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        model = CustomUser
        read_only_fields = ('level', 'avatar')
        fields = ('id', 'username', 'level', 'avatar')

    def get_avatar(self, obj):
        if obj.avatar:
            with open(obj.avatar.path, "rb") as image_file:
                image_data = base64.b64encode(image_file.read()).decode("utf-8")
            return image_data
        return None


class MyProfileSerializer(serializers.ModelSerializer):
    avatar = serializers.SerializerMethodField()
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

    def get_avatar(self, obj):
        request = self.context.get('request')
        user = request.user

        if user.avatar:
            with open(user.avatar.path, "rb") as image_file:
                image_data = base64.b64encode(image_file.read()).decode("utf-8")
            return image_data
        return None


class TranslationSerializer(serializers.ModelSerializer):
    star = serializers.BooleanField(required=False)

    class Meta:
        model = Translation
        read_only_fields = ('id', 'english', 'polish')
        fields = ('id', 'english', 'polish', 'star')

    def get_star(self, obj):
        request = self.context.get('request')
        if request:
            return obj.starred_by.filter(id=request.user.id).exists()
        return False


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
