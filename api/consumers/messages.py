import json
from dataclasses import dataclass, asdict
from enum import Enum
from typing import List, Dict, Optional, TypedDict

@dataclass
class WebSocketMessage:
    def to_json(self):
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, text: str):
        return cls(**json.loads(text))


class WaitroomMessageType(str, Enum):
    WAITROOM_REQUEST = "waitroom_request"
    JOINED_WAITROOM = "joined_waitroom"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    PLAYER_INVITATION = "player_invitation"
    START_GAME = "start_game"
    WAITROOM_CANCELED = "waitroom_canceled"
    GAME_STARTING = "game_starting"
    FINAL_RESULT = "final_result"


@dataclass
class WaitroomRequestMessage(WebSocketMessage):
    wordset_id: Optional[str] = None
    as_owner: Optional[bool] = None
    owned_room: Optional[str] = None
    type: str = WaitroomMessageType.WAITROOM_REQUEST

@dataclass
class JoinedWaitroomMessage(WebSocketMessage):
    usernames: List[str]
    waitroom: str
    type: str = WaitroomMessageType.JOINED_WAITROOM

@dataclass
class PlayerJoinedMessage(WebSocketMessage):
    username: str
    type: str = WaitroomMessageType.PLAYER_JOINED

@dataclass
class PlayerLeftMessage(WebSocketMessage):
    username: str
    type: str = WaitroomMessageType.PLAYER_LEFT

@dataclass
class PlayerInvitationMessage(WebSocketMessage):
    user_id: str
    type: str = WaitroomMessageType.PLAYER_INVITATION

@dataclass
class StartGameMessage(WebSocketMessage):
    type: str = WaitroomMessageType.START_GAME

@dataclass
class WaitroomCanceledMessage(WebSocketMessage):
    type: str = WaitroomMessageType.WAITROOM_CANCELED

@dataclass
class GameStartingMessage(WebSocketMessage):
    type: str = WaitroomMessageType.GAME_STARTING

class PlayerResult(TypedDict):
    user__username: str
    score: int

class PlayerResultDisplay(TypedDict):
    username: str
    score: int
    place: int

@dataclass
class GameFinalResultMessage(WebSocketMessage):
    scoreboard: List[PlayerResultDisplay]
    type: str = WaitroomMessageType.FINAL_RESULT

    @classmethod
    def create_from_players(cls, players_with_scores: List[PlayerResult]):
        players_with_scores.sort(key=lambda r: r["score"], reverse=True)

        place = 0
        place_score = None

        scoreboard: List[PlayerResultDisplay] = []

        for player_result in players_with_scores:
            if player_result["score"] != place_score:
                place += 1
                place_score = player_result["score"]
            
            scoreboard.append({
                "username": player_result["user__username"],
                "score": player_result["score"],
                "place": place
            })

        return cls(scoreboard=scoreboard)



class RaceMessageType(str, Enum):
    NEW_QUESTION = "new_question"
    RESPONSE = "response"
    RESULT = "result"


@dataclass
class RaceNewQuestionMessage(WebSocketMessage):
    question: str
    answers: List[str]
    timeout: int
    type: str = RaceMessageType.NEW_QUESTION


@dataclass
class RaceAnswerMessage(WebSocketMessage):
    answer: str
    round: int
    type: str = RaceMessageType.RESPONSE


@dataclass
class RaceRoundResultMessage(WebSocketMessage):
    correct: str
    user_answer: str
    points: int
    type: str = RaceMessageType.RESULT

class FindingWordsMessageType(str, Enum):
    NEW_QUESTION = "new_question"
    RESPONSE = "response"
    RESULT = "result"


@dataclass
class FindingWordsNewQuestionMessage(WebSocketMessage):
    letters: List[str]
    timeout: int
    round: int
    type: str = FindingWordsMessageType.NEW_QUESTION


@dataclass
class FindingWordsAnswerMessage(WebSocketMessage):
    answer: str
    round: int
    type: str = FindingWordsMessageType.RESPONSE


@dataclass
class FindingWordsRoundResultMessage(WebSocketMessage):
    word: str
    user_answer: str
    points: int
    type: str = FindingWordsMessageType.RESULT

