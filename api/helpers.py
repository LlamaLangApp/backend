from datetime import date, timedelta

from api.models import WordSet
from backend.settings import POINTS_TO_2_LEVEL


def calculate_current_week_start():
    today = date.today()
    # (0: Monday, 1: Tuesday, ..., 6: Sunday)
    days_until_monday = today.weekday() % 7
    current_week_start = today - timedelta(days=days_until_monday)
    return current_week_start


def get_score_goal_for_level(level):
    return POINTS_TO_2_LEVEL * (2 ** level)
