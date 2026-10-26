import pytest

from game.logic.action_handlers import handle_riichi
from game.logic.action_result import ActionResult
from game.logic.meld_wrapper import FrozenMeld
from game.logic.state import Discard, MahjongPlayer, MahjongRoundState
from game.logic.types import RiichiActionData
from game.tests.conftest import create_dealt_game_state, create_player
from game.tests.helpers.hands import tile_copies

_RIICHI_DISCARD = tile_copies(0, honors="7")[0]
_TENPAI_ON_ONE_AND_NINE_MAN_AFTER_DRAW = (*tile_copies(0, man="1123456788899"), _RIICHI_DISCARD)
_EAST = tuple(tile_copies(0, honors="1111"))
_SOUTH = tuple(tile_copies(0, honors="2222"))


def _hand(copy: int, sou: str = "1234") -> tuple[int, ...]:
    return tuple(tile_copies(copy, pin="123456789", sou=sou))


def _discards(*tiles: int) -> tuple[Discard, ...]:
    return tuple(Discard(tile_id=t) for t in tiles)


def _declare_riichi(players: tuple[MahjongPlayer, ...], *, seat: int) -> MahjongRoundState:
    game_state = create_dealt_game_state(players, current_player_seat=seat)

    riichi = handle_riichi(game_state, seat=seat, data=RiichiActionData(tile_id=_RIICHI_DISCARD))
    assert isinstance(riichi, ActionResult)
    assert riichi.state.round_state.pending_call_prompt is None
    assert riichi.state.round_state.players[seat].is_riichi is True
    return riichi.state.round_state


def _first_turn_after_a_call(call: str) -> tuple[MahjongPlayer, ...]:
    if call == "pon":
        south_pon = FrozenMeld(
            meld_type=FrozenMeld.PON, tiles=_SOUTH[:3], opened=True, called_tile=_SOUTH[0], who=2, from_who=0
        )
        return (
            create_player(seat=0, tiles=_hand(0), discards=_discards(_SOUTH[0], _EAST[0])),
            create_player(seat=1, tiles=_TENPAI_ON_ONE_AND_NINE_MAN_AFTER_DRAW),
            create_player(seat=2, tiles=_hand(1, sou="1"), melds=(south_pon,), discards=_discards(_EAST[2])),
            create_player(seat=3, tiles=_hand(2), discards=_discards(_EAST[3])),
        )

    east_closed_kan = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=_EAST, opened=False, who=0, from_who=0)
    return (
        create_player(seat=0, tiles=_hand(0, sou="1"), melds=(east_closed_kan,), discards=_discards(_SOUTH[0])),
        create_player(seat=1, tiles=_TENPAI_ON_ONE_AND_NINE_MAN_AFTER_DRAW),
        create_player(seat=2, tiles=_hand(1)),
        create_player(seat=3, tiles=_hand(2)),
    )


class TestDeclareRiichiDaburi:
    def test_declare_riichi__when_riichi_discard_is_first_discard__should_set_daburi_and_ippatsu_for_the_declarer(self):
        players = (
            create_player(seat=0, tiles=_TENPAI_ON_ONE_AND_NINE_MAN_AFTER_DRAW),
            *(create_player(seat=seat, tiles=_hand(seat)) for seat in (1, 2, 3)),
        )

        round_state = _declare_riichi(players, seat=0)
        assert [(p.is_daburi, p.is_ippatsu) for p in round_state.players] == [
            (True, True),
            (False, False),
            (False, False),
            (False, False),
        ]

    def test_declare_riichi__when_player_already_discarded__should_not_set_daburi(self):
        players = (
            create_player(seat=0, tiles=_TENPAI_ON_ONE_AND_NINE_MAN_AFTER_DRAW, discards=_discards(_EAST[0])),
            *(create_player(seat=seat, tiles=_hand(seat), discards=_discards(_EAST[seat])) for seat in (1, 2, 3)),
        )

        round_state = _declare_riichi(players, seat=0)
        assert (round_state.players[0].is_daburi, round_state.players[0].is_ippatsu) == (False, True)

    @pytest.mark.parametrize("call", ["pon", "closed_kan"])
    def test_declare_riichi__when_first_discard_follows_a_call__should_not_set_daburi(self, call):
        round_state = _declare_riichi(_first_turn_after_a_call(call), seat=1)
        assert [d.tile_id for d in round_state.players[1].discards] == [_RIICHI_DISCARD]
        assert (round_state.players[1].is_daburi, round_state.players[1].is_ippatsu) == (False, True)
