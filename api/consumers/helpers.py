from enum import Enum, auto
from random import shuffle, sample
from typing import List

from api.models import RaceRound, WordSet


class SocketGameState(Enum):
    JUST_CONNECTED: int = auto()
    IN_WAITROOM: int = auto()
    IN_GAME: int = auto()


def get_race_rounds(words) -> List[RaceRound]:
    rounds = []
    for _ in range(5):
        shuffle(words)
        word = words.pop(0)
        correct_translation = word["polish"]

        incorrect_translations = sample([w["polish"] for w in words], 3)

        rounds.append(
            RaceRound(
                answer=correct_translation,
                question=word["english"],
                options=incorrect_translations + [correct_translation],
            )
        )
    return rounds


def get_words_for_play():
    word_set = WordSet.objects.order_by("?")[0]
    return list(word_set.words.all().values("polish", "english"))
