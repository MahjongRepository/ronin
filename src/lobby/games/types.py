from pydantic import BaseModel, Field


class CreateGameRequest(BaseModel):
    num_bots: int = Field(default=3, ge=0, le=3)


class CreateGameResponse(BaseModel):
    game_id: str
    websocket_url: str
    server_name: str
