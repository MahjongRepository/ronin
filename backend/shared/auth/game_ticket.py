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
import math
import time
from dataclasses import asdict, dataclass

import structlog

logger = structlog.get_logger()

_TOKEN_PARTS = 2  # base64url(payload).base64url(signature)

TICKET_TTL_SECONDS = 86400  # 24 hours
CLOCK_SKEW_SECONDS = 60


@dataclass
class GameTicket:
    """Payload carried inside a signed game ticket."""

    user_id: str
    username: str
    room_id: str
    issued_at: float
    expires_at: float


def create_signed_ticket(
    user_id: str,
    username: str,
    room_id: str,
    game_ticket_secret: str,
) -> str:
    """Create and sign a game ticket, returning the signed token string."""
    now = time.time()
    ticket = GameTicket(
        user_id=user_id,
        username=username,
        room_id=room_id,
        issued_at=now,
        expires_at=now + TICKET_TTL_SECONDS,
    )
    return sign_game_ticket(ticket, game_ticket_secret)


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
        logger.debug("game ticket signature mismatch")
        return None

    try:
        data = json.loads(payload_bytes)
        ticket = GameTicket(**data)
    except json.JSONDecodeError, TypeError, KeyError:
        logger.debug("game ticket malformed payload")
        return None

    if not _validate_ticket_timestamps(ticket):
        return None

    return ticket


def _is_finite_number(value: object) -> bool:
    """Check that a value is a finite int or float (excluding bool)."""
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def _validate_ticket_timestamps(ticket: GameTicket) -> bool:
    """Validate temporal claims on a game ticket.

    Checks: both timestamps are finite numbers, issued_at is not in the future
    (with clock skew tolerance), expires_at is after issued_at, the ticket
    lifetime does not exceed the allowed TTL, and the ticket has not expired.
    """
    if not _is_finite_number(ticket.issued_at) or not _is_finite_number(ticket.expires_at):
        logger.debug("game ticket non-finite timestamp")
        return False

    now = time.time()

    if ticket.issued_at > now + CLOCK_SKEW_SECONDS:
        logger.debug("game ticket issued in the future")
        return False

    if ticket.expires_at <= ticket.issued_at:
        logger.debug("game ticket expires_at <= issued_at")
        return False

    lifetime = ticket.expires_at - ticket.issued_at
    if lifetime > TICKET_TTL_SECONDS + CLOCK_SKEW_SECONDS:
        logger.debug("game ticket lifetime too long")
        return False

    if now > ticket.expires_at:
        logger.debug("game ticket expired")
        return False

    return True
