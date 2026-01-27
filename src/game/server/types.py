from pydantic import BaseModel, Field


class CreateGameRequest(BaseModel):
    game_id: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
