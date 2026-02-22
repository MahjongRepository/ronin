from pydantic import BaseModel


class GameServer(BaseModel):
    name: str
    url: str
    public_url: str | None = None
    healthy: bool = False

    @property
    def client_url(self) -> str:
        """URL exposed to browser clients (for WebSocket connections)."""
        return self.public_url or self.url
