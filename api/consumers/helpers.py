from dataclasses import dataclass
from enum import Enum, auto
from random import shuffle, sample
from typing import List

class SocketGameState(Enum):
    JUST_CONNECTED: int = auto()
    IN_WAITROOM: int = auto()
    IN_GAME: int = auto()
    ENDING_GAME: int = auto()


@dataclass
class RaceRound:
    options: List[str]
    answer: str
    answer_id: int
    question: str


def get_race_rounds(words) -> List[RaceRound]:
    rounds = []
    for _ in range(5):
        shuffle(words)
        word = words.pop(0)
        correct_translation = word["polish"]
        correct_translation_id = word["id"]

        incorrect_translations = sample([w["polish"] for w in words], 3)

        rounds.append(
            RaceRound(
                answer=correct_translation,
                answer_id=correct_translation_id,
                question=word["english"],
                options=incorrect_translations + [correct_translation],
            )
        )
    return rounds


def get_words_for_play(wordset):
    return list(wordset.words.all().values("polish", "english", "id"))

@dataclass
class FindingWordsRound:
    letters: List[str]
    answer: str
    
def get_finding_words_rounds(words: List[str], round_count: int) -> List[FindingWordsRound]:
    LETTER_COUNT = 8
    ADD_ADDITIONAL_LETTERS = False
    rounds = []

    all_letters = list(set([letter for word in words for letter in word]))

    shuffle(words)
    for _ in range(round_count):
        shuffle(all_letters)

        word = words.pop()
        letters = list(word)

        remaining_letters = LETTER_COUNT - len(letters)
        if remaining_letters > 0 and ADD_ADDITIONAL_LETTERS:
            letters += all_letters[:remaining_letters]

        shuffle(letters)

        rounds.append(FindingWordsRound(letters, word))

    return rounds

def get_points(position: int):
    POINTS_PER_POSITION = [25, 20, 15, 10, 5]
    if position < len(POINTS_PER_POSITION):
        return POINTS_PER_POSITION[position]
    return POINTS_PER_POSITION[-1]