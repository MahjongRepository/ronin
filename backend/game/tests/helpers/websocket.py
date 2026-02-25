"""Shared WebSocket test helpers for game integration tests."""

from game.logic.events import EventType
from game.messaging.encoder import decode, encode
from game.messaging.event_payload import EVENT_TYPE_INT
from game.messaging.wire_enums import WireClientMessageType
from game.tests.helpers.auth import make_test_game_ticket


def send_ws(ws, data: dict) -> None:
    """Send a MessagePack-encoded message over a test WebSocket."""
    ws.send_bytes(encode(data))


def recv_ws(ws) -> dict:
    """Receive and decode a MessagePack message from a test WebSocket."""
    return decode(ws.receive_bytes())


def create_pending_game(client, game_id: str, num_ai_players: int = 3) -> list[str]:
    """Create a pending game via POST /games. Return the list of game tickets."""
    num_humans = 4 - num_ai_players
    players = []
    tickets = []
    for i in range(num_humans):
        ticket = make_test_game_ticket(f"Player{i + 1}", game_id, user_id=f"user-{i}")
        players.append({"name": f"Player{i + 1}", "user_id": f"user-{i}", "game_ticket": ticket})
        tickets.append(ticket)
    response = client.post(
        "/games",
        json={"game_id": game_id, "players": players, "num_ai_players": num_ai_players},
    )
    assert response.status_code == 201
    return tickets


def join_game_and_start(ws, ticket: str) -> list[dict]:
    """Join a pending game via JOIN_GAME and drain startup messages."""
    send_ws(ws, {"t": WireClientMessageType.JOIN_GAME, "game_ticket": ticket})
    messages = []
    while True:
        msg = recv_ws(ws)
        messages.append(msg)
        if msg.get("t") in (EVENT_TYPE_INT[EventType.ROUND_STARTED], EVENT_TYPE_INT[EventType.DRAW]):
            break
    return messages
