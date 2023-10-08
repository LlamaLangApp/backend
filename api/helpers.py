from datetime import date, timedelta

from api.models import WordSet


def calculate_current_week_start():
    today = date.today()
    # (0: Monday, 1: Tuesday, ..., 6: Sunday)
    days_until_monday = today.weekday() % 7
    current_week_start = today - timedelta(days=days_until_monday)
    return current_week_start

#
# def wordset_accuracy_check(user, wordset):
#     if wordset.difficulty == 1:
#         return True
#
#     if wordset:
#         easier_wordsets_from_category = WordSet.objects.filter(category=wordset.category,
#                                                               difficulty__lt=wordset.difficulty)
#
#         for wordset in easier_wordsets_from_category:
#             if wordset.calculate_average_accuracy(user) < 0.7:
#                 return False
#     return False