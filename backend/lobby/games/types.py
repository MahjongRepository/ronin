from pydantic import BaseModel, ConfigDict, Field


class CreateRoomRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    num_ai_players: int = Field(default=3, ge=0, le=3)


class CreateRoomResponse(BaseModel):
    room_id: str
    websocket_url: str
    server_name: str
