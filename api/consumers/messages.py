import json
from dataclasses import dataclass, asdict
from enum import Enum
from typing import List, Dict, Optional

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

@dataclass
class GameFinalResultMessage(WebSocketMessage):
    winner: str
    winner_points: int
    scoreboard: List[Dict[str, str]]
    type: str = WaitroomMessageType.FINAL_RESULT

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
    points: int
    type: str = FindingWordsMessageType.RESULT

