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


@dataclass
class GameTicket:
    """
    Payload carried inside a signed game ticket.
    """

    user_id: str
    username: str
    room_id: str
    expires_at: float


def create_signed_ticket(
    *,
    user_id: str,
    username: str,
    room_id: str,
    game_ticket_secret: str,
) -> str:
    """
    Create and sign a game ticket, returning the signed token string.
    """
    ticket = GameTicket(
        user_id=user_id,
        username=username,
        room_id=room_id,
        expires_at=time.time() + TICKET_TTL_SECONDS,
    )
    return sign_game_ticket(ticket, game_ticket_secret)


def sign_game_ticket(ticket: GameTicket, secret: str) -> str:
    """
    Serialize ticket to JSON, compute HMAC-SHA256, return base64url(payload).base64url(sig).
    """
    payload_bytes = json.dumps(asdict(ticket), sort_keys=True).encode()
    sig = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).digest()

    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode()
    sig_b64 = base64.urlsafe_b64encode(sig).decode()
    return f"{payload_b64}.{sig_b64}"


def verify_game_ticket(token: str, secret: str) -> GameTicket | None:
    """
    Verify HMAC signature and expiry.

    Returns GameTicket or None on any failure.
    """
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

    if not _is_unexpired(ticket.expires_at):
        return None

    return ticket


def _is_unexpired(expires_at: object) -> bool:
    """
    Check that expires_at is a finite float that has not passed yet.
    """
    if not isinstance(expires_at, float) or not math.isfinite(expires_at):
        logger.debug("game ticket invalid expires_at")
        return False

    if time.time() > expires_at:
        logger.debug("game ticket expired")
        return False

    return True
