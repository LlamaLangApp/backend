# serializers.py
from django.db.models import Sum
from rest_framework import serializers

from api.helpers import calculate_current_week_start
from api.models import Translation, WordSet, MemoryGameSession, FallingWordsGameSession, CustomUser, ScoreHistory, \
    Friendship, FriendRequest
from djoser.serializers import UserCreateSerializer, UserSerializer


class CustomUserCreateSerializer(UserCreateSerializer):
    class Meta(UserCreateSerializer.Meta):
        model = CustomUser
        fields = ('id', 'username', 'email', 'password', 'avatar')


class CustomUserSerializer(UserSerializer):
    class Meta(UserSerializer.Meta):
        model = CustomUser
        read_only_fields = ('level', 'avatar')
        fields = ('id', 'username', 'level', 'avatar', 'llama')


class MyProfileSerializer(serializers.ModelSerializer):
    current_week_points = serializers.SerializerMethodField()
    points_to_next_level = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        read_only_fields = ('level', 'current_week_points', 'score')
        fields = (
            'id', 'username', 'email', 'score', 'level', 'llama', 'avatar', 'current_week_points',
            'points_to_next_level')

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

    @staticmethod
    def get_points_to_next_level(obj):
        return obj.get_points_to_next_level()


class TranslationSerializer(serializers.ModelSerializer):
    star = serializers.SerializerMethodField()

    class Meta:
        model = Translation
        read_only_fields = ('id', 'english', 'polish')
        fields = ('id', 'english', 'polish', 'star')

    def get_star(self, obj):
        request = self.context.get('request')
        print(obj)
        return obj.get_starred_by_user(request.user)


class WordSetSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = WordSet
        fields = ('id', 'english', 'polish', 'category', 'difficulty')


class WordSetSerializer(serializers.ModelSerializer):
    locked = serializers.SerializerMethodField()
    points = serializers.SerializerMethodField()
    depends_on = WordSetSummarySerializer(many=True, source='get_easier_wordsets_from_category')

    class Meta:
        model = WordSet
        fields = ('id', 'english', 'polish', 'category', 'difficulty', 'locked',
                  'points', 'depends_on'
                  )

    def get_points(self, obj):
        request = self.context.get('request')
        user = request.user

        return obj.get_total_points_for_user(user)

    def get_locked(self, obj):
        request = self.context.get('request')
        user = request.user

        return obj.is_locked_for_user(user)


class WordSetWithTranslationSerializer(WordSetSerializer):
    words = TranslationSerializer(many=True)

    class Meta:
        model = WordSet
        fields = ('words',)


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
