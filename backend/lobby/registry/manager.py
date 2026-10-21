from http import HTTPStatus
from typing import TYPE_CHECKING

import httpx
import structlog
import yaml

from lobby.registry.types import GameServer

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger()


class RegistryManager:
    def __init__(self, config_path: Path) -> None:
        self._servers: list[GameServer] = []
        self._config_path = config_path
        self._load_config()

    def _load_config(self) -> None:
        if not self._config_path.exists():
            return

        with self._config_path.open() as f:
            config = yaml.safe_load(f)

        for server_data in config.get("servers", []):
            self._servers.append(
                GameServer(
                    name=server_data["name"],
                    url=server_data["url"],
                    public_url=server_data.get("public_url"),
                ),
            )

    def get_servers(self) -> list[GameServer]:
        return self._servers.copy()

    def get_healthy_servers(self) -> list[GameServer]:
        return [s for s in self._servers if s.healthy]

    async def check_health(self) -> None:
        async with httpx.AsyncClient(timeout=5.0) as client:
            for server in self._servers:
                try:
                    response = await client.get(f"{server.url}/health")
                    if response.status_code == HTTPStatus.OK:
                        server.healthy = True
                    else:
                        server.healthy = False
                except httpx.RequestError as e:
                    logger.warning("health check failed", server_name=server.name, error=str(e))
                    server.healthy = False
