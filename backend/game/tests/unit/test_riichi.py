from game.logic.ai_player_controller import AIPlayerController
from game.logic.meld_wrapper import FrozenMeld
from game.logic.riichi import can_declare_riichi, riichi_discards
from game.logic.runtime import GameRuntime
from game.logic.settings import GameSettings
from game.logic.state import Discard, MahjongPlayer, MahjongRoundState
from game.logic.tiles import tile_to_34
from game.logic.wall import tiles_remaining
from game.logic.win import get_waiting_tiles, is_furiten
from game.tests.conftest import create_dealt_game_state, create_player
from game.tests.helpers.hands import tile_copies
from game.tests.unit.helpers import _update_round_state

_TENPAI_ON_ONE_AND_NINE_MAN = tuple(tile_copies(0, man="1123456788899"))
_DRAWN_EAST = tile_copies(0, honors="1")[0]
_OTHER_HANDS = {seat: tuple(tile_copies(seat - 1, pin="123456789", sou="1234")) for seat in (1, 2, 3)}


def _dealer_after_draw(
    dealer: MahjongPlayer,
    *,
    seat_3_discards: tuple[Discard, ...] = (),
    live_tiles_left: int | None = None,
) -> tuple[MahjongPlayer, MahjongRoundState]:
    players = (
        dealer,
        create_player(seat=1, tiles=_OTHER_HANDS[1]),
        create_player(seat=2, tiles=_OTHER_HANDS[2]),
        create_player(seat=3, tiles=_OTHER_HANDS[3], discards=seat_3_discards),
    )
    runtime = GameRuntime(game_id="game", state=create_dealt_game_state(players), ai=AIPlayerController({}))
    if live_tiles_left is not None:
        wall = runtime.state.round_state.wall
        _update_round_state(runtime, wall=wall.model_copy(update={"live_tiles": wall.live_tiles[:live_tiles_left]}))
        assert tiles_remaining(runtime.state.round_state.wall) == live_tiles_left

    round_state = runtime.state.round_state
    return round_state.players[0], round_state


def _tenpai_dealer_after_draw(**updates: object) -> MahjongPlayer:
    return create_player(seat=0, tiles=(*_TENPAI_ON_ONE_AND_NINE_MAN, _DRAWN_EAST)).model_copy(update=updates)


class TestCanDeclareRiichi:
    def test_can_declare_riichi__when_closed_hand_tempai__should_allow(self):
        player, round_state = _dealer_after_draw(_tenpai_dealer_after_draw())

        result = can_declare_riichi(player, round_state, settings=GameSettings())
        assert result is True

    def test_can_declare_riichi__when_already_riichi__should_reject(self):
        riichi_discard = Discard(tile_id=tile_copies(1, honors="1")[0], is_riichi_discard=True)
        player, round_state = _dealer_after_draw(
            _tenpai_dealer_after_draw(is_riichi=True, discards=(riichi_discard,), score=24000)
        )

        result = can_declare_riichi(player, round_state, settings=GameSettings())
        assert result is False

    def test_can_declare_riichi__when_score_999__should_reject(self):
        player, round_state = _dealer_after_draw(_tenpai_dealer_after_draw(score=999))

        result = can_declare_riichi(player, round_state, settings=GameSettings())
        assert result is False

    def test_can_declare_riichi__when_score_exactly_1000__should_allow(self):
        player, round_state = _dealer_after_draw(_tenpai_dealer_after_draw(score=1000))

        result = can_declare_riichi(player, round_state, settings=GameSettings())
        assert result is True

    def test_can_declare_riichi__when_hand_has_open_meld__should_reject(self):
        one_man_pon_tiles = tile_copies(0, man="111")
        open_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(one_man_pon_tiles),
            opened=True,
            called_tile=one_man_pon_tiles[0],
            who=0,
            from_who=3,
        )
        tenpai_hand_with_meld = tuple(tile_copies(1, man="2345678889"))
        dealer = create_player(
            seat=0,
            tiles=(*tenpai_hand_with_meld, _DRAWN_EAST),
            melds=(open_meld,),
            discards=tuple(Discard(tile_id=t) for t in tile_copies(0, honors="23")),
        )
        player, round_state = _dealer_after_draw(dealer, seat_3_discards=(Discard(tile_id=one_man_pon_tiles[0]),))
        assert get_waiting_tiles(create_player(seat=0, tiles=tenpai_hand_with_meld, melds=(open_meld,))) == {
            tile_to_34(t) for t in tile_copies(3, man="1479")
        }

        result = can_declare_riichi(player, round_state, settings=GameSettings())
        assert result is False

    def test_can_declare_riichi__when_hand_has_closed_kan_and_drew__should_allow_the_tenpai_keeping_discards(self):
        closed_kan = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(tile_copies(0, man="1111")),
            opened=False,
            who=0,
            from_who=0,
        )
        man_nine = tile_copies(0, man="9")[0]
        drawn_hand_with_kan = (*tile_copies(0, man="2345678889"), _DRAWN_EAST)
        player, round_state = _dealer_after_draw(create_player(seat=0, tiles=drawn_hand_with_kan, melds=(closed_kan,)))

        assert can_declare_riichi(player, round_state, settings=GameSettings()) is True
        assert riichi_discards(player) == [man_nine, _DRAWN_EAST]

    def test_can_declare_riichi__when_not_tempai__should_reject(self):
        far_from_tenpai = (*tile_copies(3, man="13579", pin="2468", sou="1357"), _DRAWN_EAST)
        player, round_state = _dealer_after_draw(create_player(seat=0, tiles=far_from_tenpai))

        result = can_declare_riichi(player, round_state, settings=GameSettings())
        assert result is False

    def test_can_declare_riichi__when_wall_has_3_tiles__should_reject(self):
        player, round_state = _dealer_after_draw(_tenpai_dealer_after_draw(), live_tiles_left=3)

        result = can_declare_riichi(player, round_state, settings=GameSettings())
        assert result is False

    def test_can_declare_riichi__when_wall_has_4_tiles__should_allow(self):
        player, round_state = _dealer_after_draw(_tenpai_dealer_after_draw(), live_tiles_left=4)

        result = can_declare_riichi(player, round_state, settings=GameSettings())
        assert result is True

    def test_can_declare_riichi__when_player_discard_furiten__should_allow(self):
        discarded_one_man = tile_copies(2, man="1")[0]
        waiting_dealer = create_player(
            seat=0, tiles=_TENPAI_ON_ONE_AND_NINE_MAN, discards=(Discard(tile_id=discarded_one_man),)
        )
        assert tile_to_34(discarded_one_man) in get_waiting_tiles(waiting_dealer)
        assert is_furiten(waiting_dealer) is True
        player, round_state = _dealer_after_draw(
            waiting_dealer.model_copy(update={"tiles": (*_TENPAI_ON_ONE_AND_NINE_MAN, _DRAWN_EAST)})
        )

        assert can_declare_riichi(player, round_state, settings=GameSettings()) is True

    def test_can_declare_riichi__when_player_temporary_furiten__should_allow(self):
        player, round_state = _dealer_after_draw(_tenpai_dealer_after_draw(is_temporary_furiten=True))

        assert can_declare_riichi(player, round_state, settings=GameSettings()) is True
