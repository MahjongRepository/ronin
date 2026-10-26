import pytest

from game.logic.action_handlers import handle_tsumo
from game.logic.actions import get_available_actions
from game.logic.enums import AIPlayerType, PlayerAction
from game.logic.exceptions import InvalidGameActionError
from game.logic.game import init_game
from game.logic.meld_wrapper import FrozenMeld
from game.logic.round import draw_tile
from game.logic.state import Discard, MahjongGameState
from game.logic.types import SeatConfig
from game.tests.conftest import create_dealt_game_state, create_player
from game.tests.helpers.hands import tile_copies
from game.tests.unit.helpers import _string_to_34_tile, _string_to_34_tiles


def _default_seat_configs() -> list[SeatConfig]:
    return [
        SeatConfig(name="Player"),
        SeatConfig(name="Tsumogiri 1", ai_player_type=AIPlayerType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 2", ai_player_type=AIPlayerType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 3", ai_player_type=AIPlayerType.TSUMOGIRI),
    ]


class TestGetAvailableActions:
    def _create_game_state(self):
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
        # draw a tile for the dealer
        new_round_state, _tile = draw_tile(game_state.round_state)
        return game_state.model_copy(update={"round_state": new_round_state})

    def test_get_available_actions__should_not_include_discard(self):
        game_state = self._create_game_state()

        actions = get_available_actions(game_state, seat=0)
        discard_actions = [a for a in actions if a.action == PlayerAction.DISCARD]
        assert len(discard_actions) == 0

    def test_get_available_actions__when_closed_hand_can_riichi__should_list_only_tenpai_keeping_discards(self):
        pin_ones = tile_copies(0, pin="11")
        stray_tile = tile_copies(0, sou="9")[0]
        hand = (*tile_copies(0, man="123456789"), *pin_ones, *tile_copies(0, pin="23"), stray_tile)
        game_state = _dealer_after_draw(hand)

        actions = get_available_actions(game_state, seat=0)
        riichi_actions = [a for a in actions if a.action == PlayerAction.RIICHI]
        assert len(riichi_actions) == 1
        assert riichi_actions[0].tiles == [*pin_ones, stray_tile]

    def test_get_available_actions__when_kan_available__should_list_kan_tiles(self):
        game_state = _dealer_after_draw(tuple(tile_copies(0, man="11112222333344")))

        actions = get_available_actions(game_state, seat=0)
        kan_actions = [a for a in actions if a.action == PlayerAction.KAN]
        assert len(kan_actions) == 1
        assert kan_actions[0].tiles == _string_to_34_tiles(man="123")


def _dealer_after_draw(hand: tuple[int, ...]) -> MahjongGameState:
    players = (
        create_player(seat=0, tiles=hand),
        *(create_player(seat=seat, tiles=tile_copies(seat, sou="123456789", honors="1234")) for seat in (1, 2, 3)),
    )
    return create_dealt_game_state(players)


def _dealer_with_pon_after_draw(*, pon_tiles: list[int], tiles: tuple[int, ...]) -> MahjongGameState:
    pon = FrozenMeld(
        meld_type=FrozenMeld.PON, tiles=tuple(pon_tiles), opened=True, called_tile=pon_tiles[0], who=0, from_who=3
    )
    players = (
        create_player(seat=0, tiles=tiles, melds=(pon,), discards=(Discard(tile_id=tile_copies(0, honors="1")[0]),)),
        create_player(seat=1, tiles=tile_copies(1, pin="123456789", honors="1234")),
        create_player(seat=2, tiles=tile_copies(2, pin="123456789", honors="1234")),
        create_player(
            seat=3, tiles=tile_copies(3, pin="123456789", honors="1234"), discards=(Discard(tile_id=pon_tiles[0]),)
        ),
    )
    return create_dealt_game_state(players)


class TestTsumoAfterOwnCall:
    def test_tsumo__when_hand_complete_right_after_own_pon__should_be_neither_offered_nor_accepted(self):
        complete_hand = tuple(tile_copies(0, man="234567", sou="23455"))
        drawn_game = _dealer_with_pon_after_draw(pon_tiles=tile_copies(0, honors="555"), tiles=complete_hand)
        after_pon_game = drawn_game.model_copy(
            update={"round_state": drawn_game.round_state.model_copy(update={"is_after_meld_call": True})}
        )

        drawn_actions = get_available_actions(drawn_game, seat=0)
        assert PlayerAction.TSUMO in [a.action for a in drawn_actions]

        after_pon_actions = get_available_actions(after_pon_game, seat=0)
        assert PlayerAction.TSUMO not in [a.action for a in after_pon_actions]
        with pytest.raises(InvalidGameActionError, match="cannot declare tsumo"):
            handle_tsumo(after_pon_game, seat=0)


class TestAddedKanAction:
    def test_added_kan_action__when_pon_and_fourth_tile_in_hand__should_be_offered(self):
        one_man = tile_copies(0, man="1111")
        drawn_hand = (one_man[3], *tile_copies(0, sou="1234", honors="234567"))
        game_state = _dealer_with_pon_after_draw(pon_tiles=one_man[:3], tiles=drawn_hand)

        actions = get_available_actions(game_state, seat=0)
        added_kan_actions = [a for a in actions if a.action == PlayerAction.ADDED_KAN]
        assert len(added_kan_actions) == 1
        assert added_kan_actions[0].tiles == [_string_to_34_tile(man="1")]
