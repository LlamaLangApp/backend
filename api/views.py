# views.py
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from rest_framework import viewsets
from rest_framework.response import Response

from .serializers import UserSerializer


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        user.is_active = False
        user.save()
        return Response({"result": "user deleted"})
