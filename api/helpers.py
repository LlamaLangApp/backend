from datetime import timedelta
from django.utils import timezone


def calculate_current_week_start():
    today = timezone.now().date()
    start_of_the_week = today - timedelta(days=today.weekday())
    return start_of_the_week


def get_score_goal_for_level(level):
    return 300 * (2 ** level)


