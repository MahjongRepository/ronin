from pydantic import BaseModel


class GameServer(BaseModel):
    name: str
    url: str
    healthy: bool = False


class ServerStatus(BaseModel):
    status: str
    active_rooms: int = 0
    max_rooms: int = 100
