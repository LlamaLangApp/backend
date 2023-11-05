"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from rest_framework import routers
from api import views


router = routers.DefaultRouter()
router.register("translation/answers", views.TranslationUserAccuracyCounterViewSet, basename="translation-answers")
router.register("translation", views.TranslationViewSet, basename="translation")
router.register("wordset", views.WordSetReadOnlySet, basename="wordset")
router.register("memory-game", views.MemoryGameSessionViewSet, basename="memory-game")
router.register(
    "falling-words", views.FallingWordsSessionViewSet, basename="falling-words"
)
router.register(
    "friend-request", views.FriendRequestViewSet, basename="friendship-request"
)
router.register("friendship", views.FriendshipViewSet, basename="friendship")

urlpatterns = [
    path("", include(router.urls)),
    path("statistics/", views.get_statistics),
    path("user-statistics/", views.get_user_statistics),
    path("admin/", admin.site.urls),
    path("avatar-upload/", views.uploadAvatar, name="avatar-upload"),
    path("auth/", include("djoser.urls")),
    path("auth/", include("djoser.urls.authtoken")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT, show_indexes=True)
