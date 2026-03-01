"""Shared game transition logic for creating games on the game server."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

import httpx

from shared.auth.game_ticket import create_signed_ticket

if TYPE_CHECKING:
    from lobby.registry.manager import RegistryManager


class GameTransitionError(Exception):
    pass


_HTTP_CREATED = HTTPStatus.CREATED


async def create_game_on_server(
    game_id: str,
    players: list[dict],
    num_ai_players: int,
    registry: RegistryManager,
) -> str:
    """Call POST /games on a game server. Return the game server WebSocket URL."""
    await registry.check_health()
    healthy_servers = registry.get_healthy_servers()
    if not healthy_servers:
        raise GameTransitionError("No healthy game servers available")

    server = healthy_servers[0]
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                f"{server.url}/games",
                json={
                    "game_id": game_id,
                    "players": players,
                    "num_ai_players": num_ai_players,
                },
            )
            if response.status_code != _HTTP_CREATED:
                raise GameTransitionError(
                    f"Game server returned {response.status_code}: {response.text}",
                )
        except httpx.RequestError as e:
            raise GameTransitionError(f"Failed to connect to game server: {e}") from e

    ws_url = server.client_url.replace("http://", "ws://").replace("https://", "wss://")
    return f"{ws_url}/ws/{game_id}"


def sign_player_tickets(
    players: list[tuple[str, str, str]],
    game_id: str,
    ticket_secret: str,
) -> tuple[list[dict], dict[str, str]]:
    """Sign game tickets for a list of players.

    Args:
        players: List of (user_id, username, connection_id) tuples.
        game_id: The game ID to include in the ticket.
        ticket_secret: HMAC secret for signing.

    Returns:
        (player_specs, ticket_map) where ticket_map is connection_id -> signed_ticket.
    """
    player_specs = []
    ticket_map: dict[str, str] = {}
    for user_id, username, conn_id in players:
        signed_ticket = create_signed_ticket(user_id, username, game_id, ticket_secret)
        player_specs.append({"name": username, "user_id": user_id, "game_ticket": signed_ticket})
        ticket_map[conn_id] = signed_ticket
    return player_specs, ticket_map
