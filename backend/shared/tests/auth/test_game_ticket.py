"""Tests for HMAC-SHA256 game ticket signing and verification."""

import base64
import hashlib
import hmac
import json
import time

from shared.auth.game_ticket import (
    TICKET_TTL_SECONDS,
    GameTicket,
    sign_game_ticket,
    verify_game_ticket,
)

SECRET = "test-hmac-secret"


def _make_ticket(
    user_id: str = "user-123",
    username: str = "alice",
    room_id: str = "room-abc",
    issued_at: float | None = None,
    expires_at: float | None = None,
) -> GameTicket:
    now = time.time()
    return GameTicket(
        user_id=user_id,
        username=username,
        room_id=room_id,
        issued_at=issued_at if issued_at is not None else now,
        expires_at=expires_at if expires_at is not None else now + TICKET_TTL_SECONDS,
    )


class TestSignAndVerifyRoundTrip:
    def test_valid_ticket_round_trips(self):
        ticket = _make_ticket()
        token = sign_game_ticket(ticket, SECRET)
        result = verify_game_ticket(token, SECRET)
        assert result is not None
        assert result.user_id == ticket.user_id
        assert result.username == ticket.username
        assert result.room_id == ticket.room_id

    def test_token_format_is_two_base64url_parts(self):
        ticket = _make_ticket()
        token = sign_game_ticket(ticket, SECRET)
        parts = token.split(".")
        assert len(parts) == 2
        # Both parts should be valid base64url
        base64.urlsafe_b64decode(parts[0])
        base64.urlsafe_b64decode(parts[1])

    def test_payload_contains_ticket_fields(self):
        ticket = _make_ticket(user_id="u1", username="bob", room_id="r1")
        token = sign_game_ticket(ticket, SECRET)
        payload_b64 = token.split(".")[0]
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        assert payload["user_id"] == "u1"
        assert payload["username"] == "bob"
        assert payload["room_id"] == "r1"
        assert "issued_at" in payload
        assert "expires_at" in payload


class TestExpiredTicket:
    def test_expired_ticket_rejected(self):
        past = time.time() - TICKET_TTL_SECONDS - 1
        ticket = _make_ticket(issued_at=past, expires_at=past + TICKET_TTL_SECONDS)
        token = sign_game_ticket(ticket, SECRET)
        assert verify_game_ticket(token, SECRET) is None

    def test_ticket_at_boundary_still_valid(self):
        now = time.time()
        ticket = _make_ticket(issued_at=now, expires_at=now + TICKET_TTL_SECONDS)
        token = sign_game_ticket(ticket, SECRET)
        assert verify_game_ticket(token, SECRET) is not None


class TestTamperedTicket:
    def test_tampered_payload_rejected(self):
        ticket = _make_ticket()
        token = sign_game_ticket(ticket, SECRET)
        payload_b64, sig_b64 = token.split(".")
        # Decode, tamper, re-encode
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        payload["username"] = "evil"
        tampered_payload = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode()).decode()
        tampered_token = f"{tampered_payload}.{sig_b64}"
        assert verify_game_ticket(tampered_token, SECRET) is None

    def test_tampered_signature_rejected(self):
        ticket = _make_ticket()
        token = sign_game_ticket(ticket, SECRET)
        payload_b64, sig_b64 = token.split(".")
        # Flip a byte in the signature
        sig_bytes = bytearray(base64.urlsafe_b64decode(sig_b64))
        sig_bytes[0] ^= 0xFF
        tampered_sig = base64.urlsafe_b64encode(bytes(sig_bytes)).decode()
        tampered_token = f"{payload_b64}.{tampered_sig}"
        assert verify_game_ticket(tampered_token, SECRET) is None


class TestWrongSecret:
    def test_wrong_secret_rejected(self):
        ticket = _make_ticket()
        token = sign_game_ticket(ticket, SECRET)
        assert verify_game_ticket(token, "wrong-secret") is None


class TestMalformedToken:
    def test_empty_string(self):
        assert verify_game_ticket("", SECRET) is None

    def test_no_dot_separator(self):
        assert verify_game_ticket("nodot", SECRET) is None

    def test_too_many_dots(self):
        assert verify_game_ticket("a.b.c", SECRET) is None

    def test_invalid_base64_payload(self):
        assert verify_game_ticket("!!!invalid.AAAA", SECRET) is None

    def test_invalid_base64_signature(self):
        ticket = _make_ticket()
        token = sign_game_ticket(ticket, SECRET)
        payload_b64 = token.split(".")[0]
        assert verify_game_ticket(f"{payload_b64}.!!!invalid", SECRET) is None

    def test_valid_base64_but_invalid_json_payload(self):
        bad_payload = base64.urlsafe_b64encode(b"not json").decode()
        bad_sig = base64.urlsafe_b64encode(b"x" * 32).decode()
        assert verify_game_ticket(f"{bad_payload}.{bad_sig}", SECRET) is None

    def test_valid_json_but_missing_fields(self):
        """A properly signed token whose payload lacks required GameTicket fields."""
        incomplete_payload = json.dumps({"user_id": "x"}, sort_keys=True).encode()
        sig = hmac.new(SECRET.encode(), incomplete_payload, hashlib.sha256).digest()
        payload_b64 = base64.urlsafe_b64encode(incomplete_payload).decode()
        sig_b64 = base64.urlsafe_b64encode(sig).decode()
        assert verify_game_ticket(f"{payload_b64}.{sig_b64}", SECRET) is None

    def test_non_numeric_expires_at_returns_none(self):
        """A signed token with non-numeric expires_at returns None instead of raising TypeError."""
        payload = json.dumps(
            {
                "expires_at": "not-a-number",
                "issued_at": time.time(),
                "room_id": "room-1",
                "user_id": "u1",
                "username": "alice",
            },
            sort_keys=True,
        ).encode()
        sig = hmac.new(SECRET.encode(), payload, hashlib.sha256).digest()
        payload_b64 = base64.urlsafe_b64encode(payload).decode()
        sig_b64 = base64.urlsafe_b64encode(sig).decode()
        assert verify_game_ticket(f"{payload_b64}.{sig_b64}", SECRET) is None
