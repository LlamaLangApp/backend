# views.py
from django.contrib.auth.models import User
from rest_framework import viewsets, status, permissions
from rest_framework.response import Response

from api.serializers import TranslationSerializer, UserSerializer, WordSetSerializer
from api.models import Translation, WordSet

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        user.is_active = False
        user.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

class TranslationReadOnlySet(viewsets.ReadOnlyModelViewSet):
    queryset = Translation.objects.all()
    serializer_class = TranslationSerializer
    permission_classes = [permissions.IsAuthenticated]

class WordSetReadOnlySet(viewsets.ReadOnlyModelViewSet):
    queryset = WordSet.objects.all()
    serializer_class = WordSetSerializer
    permission_classes = [permissions.IsAuthenticated]