# serializers.py
from django.core.files.base import ContentFile
from django.db.models import Sum
from rest_framework import serializers

from api.helpers import calculate_current_week_start
from api.models import Translation, WordSet, MemoryGameSession, FallingWordsGameSession, CustomUser, ScoreHistory
from djoser.serializers import UserCreateSerializer, UserSerializer


class CustomUserCreateSerializer(UserCreateSerializer):
    class Meta(UserCreateSerializer.Meta):
        model = CustomUser
        fields = ('id', 'username', 'email', 'password', 'avatar')


class CustomUserSerializer(UserSerializer):
    class Meta(UserSerializer.Meta):
        model = CustomUser
        read_only_fields = ('level', 'avatar')
        fields = ('id', 'username', 'email', 'level', 'avatar')


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
    class Meta:
        model = Translation
        fields = '__all__'


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


