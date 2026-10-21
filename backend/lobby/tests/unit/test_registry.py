from unittest.mock import AsyncMock, patch

import httpx
import pytest

from lobby.registry.manager import RegistryManager


class TestRegistryManagerLoadConfig:
    def test_registry_load_config__should_load_servers_from_yaml(self, tmp_path):
        config = tmp_path / "servers.yaml"
        config.write_text(
            "servers:\n"
            '  - name: "alpha"\n'
            '    url: "http://alpha:8001"\n'
            '  - name: "beta"\n'
            '    url: "http://beta:8002"\n',
        )
        manager = RegistryManager(config_path=config)
        servers = manager.get_servers()
        assert len(servers) == 2
        assert servers[0].name == "alpha"
        assert servers[1].url == "http://beta:8002"

    def test_registry_load_config__should_load_public_url_from_yaml(self, tmp_path):
        config = tmp_path / "servers.yaml"
        config.write_text(
            'servers:\n  - name: "game-1"\n    url: "http://game:8711"\n    public_url: "https://example.com"\n',
        )
        manager = RegistryManager(config_path=config)
        server = manager.get_servers()[0]
        assert server.url == "http://game:8711"
        assert server.client_url == "https://example.com"

    def test_registry_load_config__when_no_public_url__should_fall_back_to_url_for_client_url(self, tmp_path):
        config = tmp_path / "servers.yaml"
        config.write_text('servers:\n  - name: "s1"\n    url: "http://s1:8001"\n')
        manager = RegistryManager(config_path=config)
        server = manager.get_servers()[0]
        assert server.client_url == "http://s1:8001"

    def test_registry_load_config__when_file_missing__should_have_no_servers(self, tmp_path):
        manager = RegistryManager(config_path=tmp_path / "nonexistent.yaml")
        assert manager.get_servers() == []

    def test_registry_load_config__when_servers_list_empty__should_have_no_servers(self, tmp_path):
        config = tmp_path / "servers.yaml"
        config.write_text("servers: []\n")
        manager = RegistryManager(config_path=config)
        assert manager.get_servers() == []


class TestRegistryManagerGetServers:
    def test_registry_get_servers__should_return_copy(self, tmp_path):
        config = tmp_path / "servers.yaml"
        config.write_text('servers:\n  - name: "s1"\n    url: "http://s1:8001"\n')
        manager = RegistryManager(config_path=config)
        copy = manager.get_servers()
        copy.clear()
        assert len(manager.get_servers()) == 1


class TestRegistryManagerGetHealthyServers:
    def test_registry_get_healthy_servers__should_exclude_unhealthy_servers(self, tmp_path):
        config = tmp_path / "servers.yaml"
        config.write_text(
            'servers:\n  - name: "up"\n    url: "http://up:8001"\n  - name: "down"\n    url: "http://down:8002"\n',
        )
        manager = RegistryManager(config_path=config)
        manager.get_servers()  # all unhealthy by default
        assert manager.get_healthy_servers() == []

        # Mark one as healthy
        manager._servers[0].healthy = True
        healthy = manager.get_healthy_servers()
        assert len(healthy) == 1
        assert healthy[0].name == "up"


class TestRegistryManagerCheckHealth:
    @pytest.mark.asyncio
    async def test_registry_check_health__when_status_200__should_mark_server_healthy(self, tmp_path):
        config = tmp_path / "servers.yaml"
        config.write_text('servers:\n  - name: "s1"\n    url: "http://s1:8001"\n')
        manager = RegistryManager(config_path=config)

        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = mock_response

            await manager.check_health()

        assert manager._servers[0].healthy is True

    @pytest.mark.asyncio
    async def test_registry_check_health__when_status_not_200__should_mark_server_unhealthy(self, tmp_path):
        config = tmp_path / "servers.yaml"
        config.write_text('servers:\n  - name: "s1"\n    url: "http://s1:8001"\n')
        manager = RegistryManager(config_path=config)
        manager._servers[0].healthy = True  # pre-set to healthy

        mock_response = AsyncMock()
        mock_response.status_code = 500

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = mock_response

            await manager.check_health()

        assert manager._servers[0].healthy is False

    @pytest.mark.asyncio
    async def test_registry_check_health__when_connection_fails__should_mark_server_unhealthy(self, tmp_path):
        config = tmp_path / "servers.yaml"
        config.write_text('servers:\n  - name: "s1"\n    url: "http://s1:8001"\n')
        manager = RegistryManager(config_path=config)

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.side_effect = httpx.RequestError("Connection refused")

            await manager.check_health()

        assert manager._servers[0].healthy is False
