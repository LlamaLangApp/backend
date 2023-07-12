import json
from dataclasses import dataclass
from enum import Enum
from typing import List


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Enum):
            return obj.value
        return super().default(obj)


@dataclass
class WebSocketMessage:
    def to_json(self):
        return json.dumps(self, cls=CustomJSONEncoder)


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

