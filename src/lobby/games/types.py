from pydantic import BaseModel


class CreateGameResponse(BaseModel):
    game_id: str
    websocket_url: str
    server_name: str
