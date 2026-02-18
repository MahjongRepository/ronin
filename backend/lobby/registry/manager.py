from http import HTTPStatus
from pathlib import Path

import httpx
import yaml

from lobby.registry.types import GameServer


def _get_default_config_path() -> Path:  # pragma: no cover — production default, tests always provide config_path
    """Return the file-relative default path to servers.yaml."""
    backend_root = Path(__file__).parent.parent.parent
    return backend_root / "config" / "servers.yaml"


class RegistryManager:
    def __init__(self, config_path: Path | None = None) -> None:
        self._servers: list[GameServer] = []
        self._config_path = config_path or _get_default_config_path()
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
                except httpx.RequestError:
                    server.healthy = False
