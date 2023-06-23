# serializers.py

from rest_framework import serializers
from api.models import Translation, WordSet, MemoryGameSession


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