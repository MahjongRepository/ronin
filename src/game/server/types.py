from pydantic import BaseModel, Field


class CreateGameRequest(BaseModel):
    game_id: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    num_bots: int = Field(default=3, ge=0, le=3)
