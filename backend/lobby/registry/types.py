from pydantic import BaseModel


class GameServer(BaseModel):
    name: str
    url: str
    healthy: bool = False
