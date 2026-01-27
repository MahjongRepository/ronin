from pydantic import BaseModel


class GameServer(BaseModel):
    name: str
    url: str
    healthy: bool = False


class ServerStatus(BaseModel):
    status: str
    active_games: int = 0
    max_games: int = 100
