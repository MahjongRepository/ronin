from pydantic import BaseModel, ConfigDict, Field

# Mahjong has 4 total seats; at most 3 can be AI players.
MAX_AI_PLAYERS = 3


class CreateRoomRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    num_ai_players: int = Field(default=MAX_AI_PLAYERS, ge=0, le=MAX_AI_PLAYERS, strict=True)


class CreateRoomResponse(BaseModel):
    room_id: str
    websocket_url: str
    server_name: str
