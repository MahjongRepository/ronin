from pydantic import BaseModel, ConfigDict, Field


class CreateRoomRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_id: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    num_ai_players: int = Field(default=3, ge=0, le=3, strict=True)
