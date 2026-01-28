from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ClientMessageType(str, Enum):
    JOIN_GAME = "join_game"
    LEAVE_GAME = "leave_game"
    GAME_ACTION = "game_action"
    CHAT = "chat"


class ServerMessageType(str, Enum):
    GAME_JOINED = "game_joined"
    GAME_LEFT = "game_left"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    GAME_STATE = "game_state"
    GAME_EVENT = "game_event"
    CHAT = "chat"
    ERROR = "error"
    # mahjong-specific message types
    GAME_STARTED = "game_started"
    DRAW = "draw"
    DISCARD = "discard"
    MELD = "meld"
    RIICHI = "riichi"
    TURN = "turn"
    CALL_PROMPT = "call_prompt"
    ROUND_END = "round_end"
    GAME_END = "game_end"


class JoinGameMessage(BaseModel):
    type: Literal[ClientMessageType.JOIN_GAME] = ClientMessageType.JOIN_GAME
    game_id: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    player_name: str = Field(min_length=1, max_length=50)


class LeaveGameMessage(BaseModel):
    type: Literal[ClientMessageType.LEAVE_GAME] = ClientMessageType.LEAVE_GAME


class GameActionMessage(BaseModel):
    type: Literal[ClientMessageType.GAME_ACTION] = ClientMessageType.GAME_ACTION
    action: str = Field(min_length=1, max_length=100)
    data: dict = Field(default_factory=dict)


class ChatMessage(BaseModel):
    type: Literal[ClientMessageType.CHAT] = ClientMessageType.CHAT
    text: str = Field(min_length=1, max_length=1000)


ClientMessage = Annotated[
    JoinGameMessage | LeaveGameMessage | GameActionMessage | ChatMessage,
    Field(discriminator="type"),
]


class GameJoinedMessage(BaseModel):
    type: Literal[ServerMessageType.GAME_JOINED] = ServerMessageType.GAME_JOINED
    game_id: str
    players: list[str]


class GameLeftMessage(BaseModel):
    type: Literal[ServerMessageType.GAME_LEFT] = ServerMessageType.GAME_LEFT


class PlayerJoinedMessage(BaseModel):
    type: Literal[ServerMessageType.PLAYER_JOINED] = ServerMessageType.PLAYER_JOINED
    player_name: str


class PlayerLeftMessage(BaseModel):
    type: Literal[ServerMessageType.PLAYER_LEFT] = ServerMessageType.PLAYER_LEFT
    player_name: str


class GameStateMessage(BaseModel):
    type: Literal[ServerMessageType.GAME_STATE] = ServerMessageType.GAME_STATE
    state: dict


class GameEventMessage(BaseModel):
    type: Literal[ServerMessageType.GAME_EVENT] = ServerMessageType.GAME_EVENT
    event: str
    data: dict = Field(default_factory=dict)


class ServerChatMessage(BaseModel):
    type: Literal[ServerMessageType.CHAT] = ServerMessageType.CHAT
    player_name: str
    text: str


class ErrorMessage(BaseModel):
    type: Literal[ServerMessageType.ERROR] = ServerMessageType.ERROR
    code: str
    message: str


# mahjong-specific message types


class TileInfo(BaseModel):
    """Tile representation for messages."""

    tile: str  # notation like "1m", "9p", "E", "R"
    tile_id: int  # 136-format ID


class DiscardInfo(BaseModel):
    """Discard information for messages."""

    tile: str
    tile_id: int
    is_tsumogiri: bool = False
    is_riichi_discard: bool = False


class MeldInfo(BaseModel):
    """Meld information for messages."""

    type: str  # "chi", "pon", "kan", "chankan", "shouminkan"
    tiles: list[str]
    tile_ids: list[int]
    opened: bool
    from_who: int | None = None


class PlayerInfo(BaseModel):
    """Player information for messages."""

    seat: int
    name: str
    is_bot: bool
    score: int
    is_riichi: bool
    discards: list[DiscardInfo]
    melds: list[MeldInfo]
    tile_count: int
    # only included for the receiving player
    tiles: list[int] | None = None
    hand: str | None = None


class AvailableAction(BaseModel):
    """An available action for the player."""

    action: str  # "discard", "riichi", "tsumo", "pon", "chi", "kan", "ron", "pass"
    tiles: list[int] | None = None  # tiles that can be used for this action


class GameStartedMessage(BaseModel):
    """
    Sent to each player when the game starts with their initial view.
    """

    type: Literal[ServerMessageType.GAME_STARTED] = ServerMessageType.GAME_STARTED
    seat: int
    round_wind: str  # "East", "South", etc.
    round_number: int
    dealer_seat: int
    wall_count: int
    dora_indicators: list[TileInfo]
    honba_sticks: int
    riichi_sticks: int
    players: list[PlayerInfo]


class DrawMessage(BaseModel):
    """
    Sent only to the player who drew a tile.
    """

    type: Literal[ServerMessageType.DRAW] = ServerMessageType.DRAW
    tile: str
    tile_id: int


class DiscardMessage(BaseModel):
    """
    Broadcast when any player discards a tile.
    """

    type: Literal[ServerMessageType.DISCARD] = ServerMessageType.DISCARD
    seat: int
    tile: str
    tile_id: int
    is_tsumogiri: bool
    is_riichi: bool


class MeldMessage(BaseModel):
    """
    Broadcast when a player calls a meld (pon, chi, kan).
    """

    type: Literal[ServerMessageType.MELD] = ServerMessageType.MELD
    caller_seat: int
    meld_type: str  # "chi", "pon", "kan"
    tiles: list[str]
    tile_ids: list[int]
    from_seat: int | None = None


class RiichiMessage(BaseModel):
    """
    Broadcast when a player declares riichi.
    """

    type: Literal[ServerMessageType.RIICHI] = ServerMessageType.RIICHI
    seat: int


class TurnMessage(BaseModel):
    """
    Sent to notify whose turn it is and available actions.
    """

    type: Literal[ServerMessageType.TURN] = ServerMessageType.TURN
    current_seat: int
    available_actions: list[AvailableAction]


class CallPromptMessage(BaseModel):
    """
    Sent to a player who can make an optional call (pon, chi, kan, ron).
    """

    type: Literal[ServerMessageType.CALL_PROMPT] = ServerMessageType.CALL_PROMPT
    available_calls: list[AvailableAction]
    timeout_seconds: int = 10


class YakuInfo(BaseModel):
    """Information about a yaku (winning condition)."""

    name: str
    han: int


class RoundEndMessage(BaseModel):
    """
    Sent when a round ends with results.
    """

    type: Literal[ServerMessageType.ROUND_END] = ServerMessageType.ROUND_END
    result_type: str  # "tsumo", "ron", "draw", "abortive"
    winner_seats: list[int] = Field(default_factory=list)
    loser_seat: int | None = None
    winning_hand: str | None = None
    yaku: list[YakuInfo] = Field(default_factory=list)
    han: int | None = None
    fu: int | None = None
    score_changes: dict[int, int] = Field(default_factory=dict)  # seat -> change
    final_scores: dict[int, int] = Field(default_factory=dict)  # seat -> score


class GameEndMessage(BaseModel):
    """
    Sent when the entire game ends.
    """

    type: Literal[ServerMessageType.GAME_END] = ServerMessageType.GAME_END
    final_scores: dict[int, int]  # seat -> score
    winner_seat: int
    placements: list[int]  # seats in order of placement (1st, 2nd, 3rd, 4th)


ServerMessage = (
    GameJoinedMessage
    | GameLeftMessage
    | PlayerJoinedMessage
    | PlayerLeftMessage
    | GameStateMessage
    | GameEventMessage
    | ServerChatMessage
    | ErrorMessage
    # mahjong-specific messages
    | GameStartedMessage
    | DrawMessage
    | DiscardMessage
    | MeldMessage
    | RiichiMessage
    | TurnMessage
    | CallPromptMessage
    | RoundEndMessage
    | GameEndMessage
)


def parse_client_message(data: dict) -> ClientMessage:
    from pydantic import TypeAdapter

    adapter = TypeAdapter(ClientMessage)
    return adapter.validate_python(data)
