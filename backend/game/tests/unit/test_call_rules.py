from __future__ import annotations

import pytest
from mahjong.tile import TilesConverter

from game.logic.action_handlers import handle_chi, handle_kan, handle_pass, handle_pon, handle_ron
from game.logic.action_result import ActionResult
from game.logic.enums import (
    GameAction,
    KanType,
    MeldCallType,
    MeldViewType,
    RoundResultType,
)
from game.logic.events import MeldEvent, RoundEndEvent, SeatTarget, TurnEvent
from game.logic.exceptions import InvalidDiscardError
from game.logic.meld_wrapper import FrozenMeld
from game.logic.melds import can_call_chi, can_call_open_kan, can_call_pon, get_kuikae_tiles
from game.logic.round import discard_tile
from game.logic.settings import GameSettings
from game.logic.state import Caller, Discard
from game.logic.tiles import tile_to_34
from game.logic.turn import process_discard_phase
from game.logic.types import ChiActionData, KanActionData, PonActionData, YakuInfo
from game.logic.win import get_waiting_tiles
from game.tests.conftest import create_dealt_game_state, create_player
from game.tests.helpers.hands import (
    PIN_3_TRIPLE_RON_CALLER_HANDS,
    PIN_3_TRIPLE_RON_DEALER_HAND,
    PIN_3_TRIPLE_RON_DISCARD,
    tile_copies,
)


def _yaku(*yaku_ids: int) -> list[YakuInfo]:
    return [YakuInfo(yaku_id=yid, han=1) for yid in yaku_ids]


_FOUR_MAN = tile_copies(0, man="4")[0]
_CHI_SEAT_SEVEN_MAN = tile_copies(0, man="7")[0]
_CHI_SEAT_NINE_SOU = tile_copies(0, sou="9")[0]
_FOUR_MAN_CALL_HANDS = (
    create_player(seat=0, tiles=(_FOUR_MAN, *tile_copies(0, pin="123456789", honors="1234"))),
    create_player(seat=1, tiles=tile_copies(0, man="567", sou="123456789", honors="5")),
    create_player(seat=2, tiles=(*tile_copies(1, man="44"), *tile_copies(1, sou="123456789", honors="56"))),
    create_player(seat=3, tiles=tile_copies(1, pin="123456789", honors="1234")),
)


def _call_four_man_discard(call: GameAction, *, settings: GameSettings | None = None) -> ActionResult:
    prompted, _events = process_discard_phase(
        create_dealt_game_state(_FOUR_MAN_CALL_HANDS, settings=settings), _FOUR_MAN
    )
    prompt = prompted.round_state.pending_call_prompt
    assert prompt is not None
    assert [(c.seat, [m.call_type for m in c.melds]) for c in prompt.callers] == [
        (2, [MeldCallType.PON]),
        (1, [MeldCallType.CHI]),
    ]

    if call == GameAction.CALL_PON:
        passed = handle_pass(prompted, seat=1)
        called = handle_pon(passed.state, seat=2, data=PonActionData(tile_id=_FOUR_MAN))
    else:
        passed = handle_pass(prompted, seat=2)
        chi_tiles = (tile_copies(0, man="5")[0], tile_copies(0, man="6")[0])
        called = handle_chi(passed.state, seat=1, data=ChiActionData(tile_id=_FOUR_MAN, sequence_tiles=chi_tiles))

    assert isinstance(called, ActionResult)
    assert called.state.round_state.is_after_meld_call
    return called


# ============================================================================
# Kuikae: Same-tile restriction
# ============================================================================


class TestKuikaeSameTileRestriction:
    def test_kuikae__when_pon__should_forbid_same_tile_type(self):
        round_state = _call_four_man_discard(GameAction.CALL_PON).state.round_state
        assert round_state.players[2].kuikae_tiles == (tile_to_34(_FOUR_MAN),)


class TestKuikaeDisabledSetting:
    @pytest.mark.parametrize(("call", "caller_seat"), [(GameAction.CALL_PON, 2), (GameAction.CALL_CHI, 1)])
    def test_kuikae__when_disabled__should_not_restrict_discard(self, call: GameAction, caller_seat: int):
        round_state = _call_four_man_discard(call, settings=GameSettings(has_kuikae=False)).state.round_state
        assert round_state.players[caller_seat].kuikae_tiles == ()


# ============================================================================
# Kuikae: Suji restriction
# ============================================================================


class TestKuikaeSujiRestriction:
    def test_kuikae_suji__when_called_lowest_of_sequence__should_forbid_suji_tile(self):
        man_tiles = TilesConverter.string_to_136_array(man="456")
        called_34 = tile_to_34(man_tiles[0])  # 4m
        sequence_34 = [tile_to_34(man_tiles[1]), tile_to_34(man_tiles[2])]  # 5m, 6m

        forbidden = get_kuikae_tiles(
            call_type=MeldCallType.CHI, called_tile_34=called_34, sequence_tiles_34=sequence_34
        )
        # 4m (called tile) and 7m (suji above 6m) should be forbidden
        assert called_34 in forbidden
        man_7m_34 = tile_to_34(TilesConverter.string_to_136_array(man="7")[0])
        assert man_7m_34 in forbidden

    def test_kuikae_suji__when_called_highest_of_sequence__should_forbid_suji_tile(self):
        man_tiles = TilesConverter.string_to_136_array(man="456")
        called_34 = tile_to_34(man_tiles[2])  # 6m
        sequence_34 = [tile_to_34(man_tiles[0]), tile_to_34(man_tiles[1])]  # 4m, 5m

        forbidden = get_kuikae_tiles(
            call_type=MeldCallType.CHI, called_tile_34=called_34, sequence_tiles_34=sequence_34
        )
        # 6m (called tile) and 3m (suji below 4m) should be forbidden
        assert called_34 in forbidden
        man_3m_34 = tile_to_34(TilesConverter.string_to_136_array(man="3")[0])
        assert man_3m_34 in forbidden

    def test_kuikae_suji__when_called_middle_of_sequence__should_forbid_only_called_tile(self):
        man_tiles = TilesConverter.string_to_136_array(man="456")
        called_34 = tile_to_34(man_tiles[1])  # 5m
        sequence_34 = [tile_to_34(man_tiles[0]), tile_to_34(man_tiles[2])]  # 4m, 6m

        forbidden = get_kuikae_tiles(
            call_type=MeldCallType.CHI, called_tile_34=called_34, sequence_tiles_34=sequence_34
        )
        # Only 5m should be forbidden (no suji for middle tile)
        assert forbidden == [called_34]

    def test_kuikae_suji__when_no_suji_tile_exists__should_forbid_only_called_tile(self):
        man_tiles = TilesConverter.string_to_136_array(man="789")
        called_34 = tile_to_34(man_tiles[0])  # 7m
        sequence_34 = [tile_to_34(man_tiles[1]), tile_to_34(man_tiles[2])]  # 8m, 9m

        forbidden = get_kuikae_tiles(
            call_type=MeldCallType.CHI, called_tile_34=called_34, sequence_tiles_34=sequence_34
        )
        # Only 7m should be forbidden (10m doesn't exist, no suji)
        assert forbidden == [called_34]

    @pytest.mark.parametrize(
        ("has_kuikae_suji", "forbidden"),
        [(False, (_FOUR_MAN,)), (True, (_FOUR_MAN, _CHI_SEAT_SEVEN_MAN))],
        ids=["suji_disabled", "suji_enabled"],
    )
    def test_kuikae_suji__when_chi_of_lowest_tile__should_forbid_the_suji_tile_only_when_enabled(
        self, has_kuikae_suji, forbidden
    ):
        settings = GameSettings(has_kuikae_suji=has_kuikae_suji)
        chi = _call_four_man_discard(GameAction.CALL_CHI, settings=settings)
        forbidden_34 = tuple(tile_to_34(t) for t in forbidden)
        assert chi.state.round_state.players[1].kuikae_tiles == forbidden_34
        assert [type(e) for e in chi.events] == [MeldEvent, TurnEvent]
        meld_event, turn_event = chi.events
        assert (meld_event.caller_seat, meld_event.meld_type) == (1, MeldViewType.CHI)
        assert (turn_event.target, turn_event.kuikae_tiles) == (SeatTarget(seat=1), list(forbidden_34))

    def test_kuikae_suji__when_discarding_the_suji_tile_after_chi__should_raise(self):
        round_state = _call_four_man_discard(GameAction.CALL_CHI).state.round_state

        with pytest.raises(InvalidDiscardError, match="not a legal discard"):
            discard_tile(round_state, seat=1, tile_id=_CHI_SEAT_SEVEN_MAN)


class TestChiOfferLeavesLegalDiscard:
    @pytest.mark.parametrize(
        ("hand", "called", "settings"),
        [
            pytest.param("1234", "1", GameSettings(), id="three_melds_1234m_chi_1m_leaves_1m_4m"),
            pytest.param(
                "1123",
                "1",
                GameSettings(has_kuikae_suji=False),
                id="three_melds_1123m_chi_1m_without_suji_leaves_1m_1m",
            ),
            pytest.param("1223", "2", GameSettings(), id="three_melds_1223m_chi_middle_2m_leaves_2m_2m"),
            pytest.param("1112344", "1", GameSettings(), id="two_melds_1112344m_chi_1m_leaves_1m_1m_1m_4m_4m"),
        ],
    )
    def test_can_call_chi__when_every_remaining_tile_would_be_kuikae_restricted__should_not_offer(
        self, hand: str, called: str, settings: GameSettings
    ):
        caller = create_player(seat=1, tiles=TilesConverter.string_to_136_array(man=hand))
        called_tile = TilesConverter.string_to_136_array(man=called * 4)[3]

        options = can_call_chi(caller, discarded_tile=called_tile, discarder_seat=0, caller_seat=1, settings=settings)
        assert options == []

    def test_can_call_chi__when_a_remaining_tile_stays_discardable__should_offer(self):
        man_1, man_2, man_3, man_5 = TilesConverter.string_to_136_array(man="1235")
        caller = create_player(seat=1, tiles=(man_1, man_2, man_3, man_5))
        called_1m = TilesConverter.string_to_136_array(man="1111")[3]

        options = can_call_chi(
            caller, discarded_tile=called_1m, discarder_seat=0, caller_seat=1, settings=GameSettings()
        )
        assert options == [(man_2, man_3)]


class TestRiichiSeatMeldOffers:
    def test_meld_offers__when_riichi_seat_holds_a_triplet_of_the_discard__should_offer_neither_pon_nor_open_kan(self):
        five_pin = tile_copies(0, pin="5555")
        riichi_seat_with_five_pin_triplet = create_player(
            seat=1,
            tiles=(*tile_copies(0, man="123456"), *five_pin[:3], *tile_copies(1, sou="7899")),
            discards=(Discard(tile_id=tile_copies(0, honors="7")[0], is_riichi_discard=True),),
            is_riichi=True,
        )
        players = (
            create_player(seat=0, tiles=(five_pin[3], *tile_copies(0, sou="123456789", honors="1234"))),
            riichi_seat_with_five_pin_triplet,
            create_player(seat=2, tiles=tile_copies(1, man="123456789", honors="1234")),
            create_player(seat=3, tiles=tile_copies(2, man="123456789", honors="1234")),
        )
        game_state = create_dealt_game_state(players)
        same_hand_out_of_riichi = riichi_seat_with_five_pin_triplet.model_copy(update={"is_riichi": False})
        assert tile_to_34(five_pin[3]) not in get_waiting_tiles(riichi_seat_with_five_pin_triplet)
        assert can_call_pon(same_hand_out_of_riichi, five_pin[3])
        assert can_call_open_kan(
            same_hand_out_of_riichi,
            discarded_tile=five_pin[3],
            round_state=game_state.round_state,
            settings=game_state.settings,
        )

        discarded, _events = process_discard_phase(game_state, five_pin[3])
        assert discarded.round_state.pending_call_prompt is None


class TestKuikaeClearedAfterDiscard:
    def test_kuikae__when_player_discards__should_clear_restriction(self):
        round_state = _call_four_man_discard(GameAction.CALL_CHI).state.round_state

        new_state, discard = discard_tile(round_state, seat=1, tile_id=_CHI_SEAT_NINE_SOU)
        assert discard.tile_id == _CHI_SEAT_NINE_SOU
        assert new_state.players[1].kuikae_tiles == ()


# ============================================================================
# Double Ron: Settings and Atamahane (Head Bump) fallback
# ============================================================================


class TestHeadBumpWhenDoubleRonDisabled:
    def test_head_bump__when_double_ron_disabled__should_pick_closest_counter_clockwise_winner(self):
        players = (
            create_player(seat=0, tiles=(*PIN_3_TRIPLE_RON_DEALER_HAND, PIN_3_TRIPLE_RON_DISCARD)),
            *(create_player(seat=seat, tiles=hand) for seat, hand in enumerate(PIN_3_TRIPLE_RON_CALLER_HANDS, start=1)),
        )
        game_state = create_dealt_game_state(players, settings=GameSettings(has_double_ron=False))
        prompted, _events = process_discard_phase(game_state, PIN_3_TRIPLE_RON_DISCARD)

        passed = handle_pass(prompted, seat=1)
        first = handle_ron(passed.state, seat=2)
        result = handle_ron(first.state, seat=3)
        round_ends = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert [(e.result.type, e.result.winner_seat) for e in round_ends] == [(RoundResultType.RON, 2)]

    def test_head_bump__when_chankan_robbed_by_two_seats__should_pick_closest_counter_clockwise_to_kan_caller(self):
        one_man = tuple(tile_copies(copy, man="1")[0] for copy in range(4))
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=one_man[:3],
            opened=True,
            called_tile=one_man[0],
            who=2,
            from_who=1,
        )
        players = (
            create_player(seat=0, tiles=tile_copies(0, man="23456789", pin="456", sou="55")),
            create_player(
                seat=1,
                tiles=(*tile_copies(0, honors="1234567"), *tile_copies(2, man="234567")),
                discards=(Discard(tile_id=one_man[0]),),
            ),
            create_player(
                seat=2,
                tiles=(one_man[3], *tile_copies(0, sou="1236789", pin="999")),
                melds=(pon_meld,),
            ),
            create_player(seat=3, tiles=(*tile_copies(1, man="23456789", pin="456"), *tile_copies(2, sou="55"))),
        )
        game_state = create_dealt_game_state(
            players,
            current_player_seat=2,
            settings=GameSettings(has_double_ron=False),
        )

        kan = handle_kan(game_state, seat=2, data=KanActionData(tile_id=one_man[3], kan_type=KanType.ADDED))
        prompt = kan.state.round_state.pending_call_prompt
        assert prompt is not None
        assert prompt.callers == (Caller(seat=3, can_ron=True), Caller(seat=0, can_ron=True))

        first = handle_ron(kan.state, seat=0)
        result = handle_ron(first.state, seat=3)
        round_ends = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert [(e.result.type, e.result.winner_seat) for e in round_ends] == [(RoundResultType.RON, 3)]
