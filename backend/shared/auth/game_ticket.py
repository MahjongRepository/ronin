"""HMAC-SHA256 signed game tickets for lobby-to-game-server authentication.

The lobby signs tickets when a user creates or joins a room. The game server
verifies the signature locally using a shared secret, avoiding a network call
on every WebSocket connection.

Token format: base64url(json_payload_bytes).base64url(hmac_sha256_signature)
"""

import base64
import binascii
import hashlib
import hmac
import json
import time
from dataclasses import asdict, dataclass

_TOKEN_PARTS = 2  # base64url(payload).base64url(signature)

TICKET_TTL_SECONDS = 86400  # 24 hours


@dataclass
class GameTicket:
    """Payload carried inside a signed game ticket."""

    user_id: str
    username: str
    room_id: str
    issued_at: float
    expires_at: float


def sign_game_ticket(ticket: GameTicket, secret: str) -> str:
    """Serialize ticket to JSON, compute HMAC-SHA256, return base64url(payload).base64url(sig)."""
    payload_bytes = json.dumps(asdict(ticket), sort_keys=True).encode()
    sig = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).digest()
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode()
    sig_b64 = base64.urlsafe_b64encode(sig).decode()
    return f"{payload_b64}.{sig_b64}"


def verify_game_ticket(token: str, secret: str) -> GameTicket | None:
    """Verify HMAC signature and expiry. Returns GameTicket or None on any failure."""
    parts = token.split(".")
    if len(parts) != _TOKEN_PARTS:
        return None

    try:
        payload_bytes = base64.urlsafe_b64decode(parts[0])
        provided_sig = base64.urlsafe_b64decode(parts[1])
    except ValueError, binascii.Error:
        return None

    expected_sig = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(provided_sig, expected_sig):
        return None

    try:
        data = json.loads(payload_bytes)
        ticket = GameTicket(**data)
    except json.JSONDecodeError, TypeError, KeyError:
        return None

    if not isinstance(ticket.expires_at, (int, float)) or time.time() > ticket.expires_at:
        return None

    return ticket
