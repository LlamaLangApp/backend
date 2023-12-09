from datetime import date, timedelta
from django.utils import timezone

from backend.settings import POINTS_TO_2_LEVEL


def calculate_current_week_start():
    today = timezone.now().date()
    start_of_the_week = today - timedelta(days=today.weekday())
    return start_of_the_week


def get_score_goal_for_level(level):
    return POINTS_TO_2_LEVEL * (2 ** level)

