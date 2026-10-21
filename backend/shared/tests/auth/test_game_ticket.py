import base64
import hashlib
import hmac
import json
import time

from shared.auth.game_ticket import (
    CLOCK_SKEW_SECONDS,
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
    def test_game_ticket__when_signed_and_verified__should_return_same_ticket(self):
        ticket = _make_ticket()
        token = sign_game_ticket(ticket, SECRET)
        result = verify_game_ticket(token, SECRET)
        assert result is not None
        assert result.user_id == ticket.user_id
        assert result.username == ticket.username
        assert result.room_id == ticket.room_id


class TestExpiredTicket:
    def test_game_ticket__when_expired__should_reject(self):
        past = time.time() - TICKET_TTL_SECONDS - 1
        ticket = _make_ticket(issued_at=past, expires_at=past + TICKET_TTL_SECONDS)
        token = sign_game_ticket(ticket, SECRET)
        assert verify_game_ticket(token, SECRET) is None

    def test_game_ticket__when_expiring_at_full_ttl__should_accept(self):
        now = time.time()
        ticket = _make_ticket(issued_at=now, expires_at=now + TICKET_TTL_SECONDS)
        token = sign_game_ticket(ticket, SECRET)
        assert verify_game_ticket(token, SECRET) is not None


class TestTamperedTicket:
    def test_game_ticket__when_payload_tampered__should_reject(self):
        ticket = _make_ticket()
        token = sign_game_ticket(ticket, SECRET)
        payload_b64, sig_b64 = token.split(".")
        # Decode, tamper, re-encode
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        payload["username"] = "evil"
        tampered_payload = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode()).decode()
        tampered_token = f"{tampered_payload}.{sig_b64}"
        assert verify_game_ticket(tampered_token, SECRET) is None

    def test_game_ticket__when_signature_tampered__should_reject(self):
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
    def test_game_ticket__when_secret_wrong__should_reject(self):
        ticket = _make_ticket()
        token = sign_game_ticket(ticket, SECRET)
        assert verify_game_ticket(token, "wrong-secret") is None


class TestMalformedToken:
    def test_game_ticket__when_token_has_no_dot__should_reject(self):
        assert verify_game_ticket("nodot", SECRET) is None

    def test_game_ticket__when_token_has_too_many_dots__should_reject(self):
        assert verify_game_ticket("a.b.c", SECRET) is None

    def test_game_ticket__when_payload_not_base64__should_reject(self):
        assert verify_game_ticket("!!!invalid.AAAA", SECRET) is None

    def test_game_ticket__when_signature_not_base64__should_reject(self):
        ticket = _make_ticket()
        token = sign_game_ticket(ticket, SECRET)
        payload_b64 = token.split(".")[0]
        assert verify_game_ticket(f"{payload_b64}.!!!invalid", SECRET) is None

    def test_game_ticket__when_fields_missing__should_reject(self):
        incomplete_payload = json.dumps({"user_id": "x"}, sort_keys=True).encode()
        sig = hmac.new(SECRET.encode(), incomplete_payload, hashlib.sha256).digest()
        payload_b64 = base64.urlsafe_b64encode(incomplete_payload).decode()
        sig_b64 = base64.urlsafe_b64encode(sig).decode()
        assert verify_game_ticket(f"{payload_b64}.{sig_b64}", SECRET) is None

    def test_game_ticket__when_expires_at_not_numeric__should_reject(self):
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


def _sign_raw_payload(payload: dict) -> str:
    payload_bytes = json.dumps(payload, sort_keys=True).encode()
    sig = hmac.new(SECRET.encode(), payload_bytes, hashlib.sha256).digest()
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode()
    sig_b64 = base64.urlsafe_b64encode(sig).decode()
    return f"{payload_b64}.{sig_b64}"


class TestTemporalValidation:
    def test_game_ticket__when_issued_in_future_beyond_skew__should_reject(self):
        future = time.time() + CLOCK_SKEW_SECONDS + 100
        ticket = _make_ticket(issued_at=future, expires_at=future + 3600)
        token = sign_game_ticket(ticket, SECRET)
        assert verify_game_ticket(token, SECRET) is None

    def test_game_ticket__when_expires_at_equals_issued_at__should_reject(self):
        now = time.time()
        ticket = _make_ticket(issued_at=now, expires_at=now)
        token = sign_game_ticket(ticket, SECRET)
        assert verify_game_ticket(token, SECRET) is None

    def test_game_ticket__when_expires_before_issued__should_reject(self):
        now = time.time()
        ticket = _make_ticket(issued_at=now, expires_at=now - 100)
        token = sign_game_ticket(ticket, SECRET)
        assert verify_game_ticket(token, SECRET) is None

    def test_game_ticket__when_lifetime_exceeds_ttl_plus_skew__should_reject(self):
        now = time.time()
        ticket = _make_ticket(
            issued_at=now,
            expires_at=now + TICKET_TTL_SECONDS + CLOCK_SKEW_SECONDS + 1,
        )
        token = sign_game_ticket(ticket, SECRET)
        assert verify_game_ticket(token, SECRET) is None

    def test_game_ticket__when_issued_within_clock_skew__should_accept(self):
        now = time.time()
        slight_future = now + CLOCK_SKEW_SECONDS - 1
        ticket = _make_ticket(issued_at=slight_future, expires_at=slight_future + 3600)
        token = sign_game_ticket(ticket, SECRET)
        assert verify_game_ticket(token, SECRET) is not None

    def test_game_ticket__when_issued_at_infinite__should_reject(self):
        token = _sign_raw_payload(
            {
                "user_id": "u1",
                "username": "alice",
                "room_id": "room-1",
                "issued_at": float("inf"),
                "expires_at": time.time() + 3600,
            },
        )
        assert verify_game_ticket(token, SECRET) is None

    def test_game_ticket__when_expires_at_nan__should_reject(self):
        token = _sign_raw_payload(
            {
                "user_id": "u1",
                "username": "alice",
                "room_id": "room-1",
                "issued_at": time.time(),
                "expires_at": float("nan"),
            },
        )
        assert verify_game_ticket(token, SECRET) is None

    def test_game_ticket__when_issued_at_not_numeric__should_reject(self):
        token = _sign_raw_payload(
            {
                "user_id": "u1",
                "username": "alice",
                "room_id": "room-1",
                "issued_at": "not-a-number",
                "expires_at": time.time() + 3600,
            },
        )
        assert verify_game_ticket(token, SECRET) is None

    def test_game_ticket__when_issued_at_boolean__should_reject(self):
        token = _sign_raw_payload(
            {
                "user_id": "u1",
                "username": "alice",
                "room_id": "room-1",
                "issued_at": True,
                "expires_at": time.time() + 3600,
            },
        )
        assert verify_game_ticket(token, SECRET) is None
