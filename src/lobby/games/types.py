from pydantic import BaseModel


class CreateGameResponse(BaseModel):
    room_id: str
    websocket_url: str
    server_name: str
