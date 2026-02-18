"""Tests for lobby handler utility functions."""

from lobby.views.handlers import build_websocket_url


class TestBuildWebsocketUrl:
    def test_http_to_ws(self):
        assert build_websocket_url("http://localhost:8711", "room1") == "ws://localhost:8711/ws/room1"

    def test_https_to_wss(self):
        assert build_websocket_url("https://example.com", "room1") == "wss://example.com/ws/room1"
