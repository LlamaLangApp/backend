from datetime import date, timedelta


def calculate_current_week_start():
    today = date.today()
    # (0: Monday, 1: Tuesday, ..., 6: Sunday)
    days_until_monday = today.weekday() % 7
    current_week_start = today - timedelta(days=days_until_monday)
    return current_week_start
