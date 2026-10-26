import time

from shared.auth.game_ticket import TICKET_TTL_SECONDS, GameTicket, sign_game_ticket

TEST_TICKET_SECRET = "test-secret"


def make_test_game_ticket(
    *,
    username: str,
    room_id: str,
    user_id: str = "test-user-id",
) -> str:
    ticket = GameTicket(
        user_id=user_id,
        username=username,
        room_id=room_id,
        expires_at=time.time() + TICKET_TTL_SECONDS,
    )
    return sign_game_ticket(ticket, TEST_TICKET_SECRET)
