import json
from dataclasses import dataclass, asdict
from enum import Enum
from typing import List, Dict


@dataclass
class WebSocketMessage:
    def to_json(self):
        return json.dumps(asdict(self))


class WaitroomMessageType(str, Enum):
    WAITROOM_REQUEST = "waitroom_request"
    JOINED_WAITROOM = "joined_waitroom"
    GAME_STARTING = "game_starting"


@dataclass
class WaitroomRequestMessage(WebSocketMessage):
    game: str
    type: str = WaitroomMessageType.WAITROOM_REQUEST


@dataclass
class JoinedWaitroomMessage(WebSocketMessage):
    type: str = WaitroomMessageType.JOINED_WAITROOM


@dataclass
class GameStartingMessage(WebSocketMessage):
    players: List[str]
    type: str = WaitroomMessageType.GAME_STARTING


class RaceMessageType(str, Enum):
    NEW_QUESTION = "new_question"
    RESPONSE = "response"
    RESULT = "result"
    FINAL_RESULT = "final_result"


@dataclass
class NewQuestionMessage(WebSocketMessage):
    question: str
    answers: List[str]
    type: str = RaceMessageType.NEW_QUESTION


@dataclass
class AnswerMessage(WebSocketMessage):
    answer: str
    type: str = RaceMessageType.RESPONSE


@dataclass
class ResultMessage(WebSocketMessage):
    correct: str
    points: int
    type: str = RaceMessageType.RESULT


@dataclass
class GameResultMessage(WebSocketMessage):
    winner: str
    points: int
    type: str = RaceMessageType.RESULT


@dataclass
class GameFinalResultMessage(WebSocketMessage):
    winner: str
    winner_points: int
    scoreboard: List[Dict[str, str]]
    type: str = RaceMessageType.FINAL_RESULT

    @classmethod
    def create_from_players(cls, players_with_scores):
        tie = False
        if players_with_scores:
            highest_score_player = players_with_scores[0]
            winner_username = highest_score_player['user__username']
            winner_points = highest_score_player['score']

            if len(players_with_scores) > 0:
                tie = winner_points == players_with_scores[1]['score']

        if tie:
            winner_username = None
            winner_points = None

        scoreboard = [{'username': player['user__username'], 'points': player['score']} for player in
                      players_with_scores]

        return cls(winner=winner_username, winner_points=winner_points, scoreboard=scoreboard)




