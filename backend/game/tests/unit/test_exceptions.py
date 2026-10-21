from game.logic.exceptions import (
    InvalidGameActionError,
)


class TestInvalidGameActionError:
    def test_invalid_game_action_error__should_format_message_with_action_seat_and_reason(self):
        err = InvalidGameActionError(action="declare_riichi", seat=0, reason="not tenpai")
        assert str(err) == "invalid declare_riichi from seat 0: not tenpai"
