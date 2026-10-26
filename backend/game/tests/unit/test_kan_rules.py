from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from mahjong.tile import TilesConverter

from game.logic.abortive import check_four_kans
from game.logic.action_handlers import _handle_self_kan, handle_discard, handle_kan, handle_pass, handle_ron
from game.logic.action_result import ActionResult, Refusal
from game.logic.actions import get_available_actions
from game.logic.ai_player_controller import AIPlayerController
from game.logic.call_resolution import resolve_call_prompt
from game.logic.enums import (
    AbortiveDrawType,
    CallType,
    GameAction,
    KanType,
    MeldViewType,
    PlayerAction,
    PromptKind,
    RoundPhase,
    RoundResultType,
)
from game.logic.events import (
    CallPromptEvent,
    DiscardEvent,
    DoraRevealedEvent,
    DrawEvent,
    MeldEvent,
    RoundEndEvent,
)
from game.logic.exceptions import InvalidGameActionError
from game.logic.invariants import verify_tile_ownership
from game.logic.mahjong_service import MahjongGameService
from game.logic.meld_wrapper import FrozenMeld
from game.logic.melds import (
    call_added_kan,
    call_closed_kan,
    call_open_kan,
    can_call_pon,
    get_possible_added_kans,
    get_possible_closed_kans,
)
from game.logic.runtime import GameRuntime
from game.logic.settings import GameSettings
from game.logic.state import Caller, Discard, MahjongGameState, MahjongPlayer, PendingCallPrompt
from game.logic.tiles import NUM_TILES, tile_to_34
from game.logic.turn import _process_added_kan_call, _process_closed_kan_call
from game.logic.types import DiscardActionData, KanActionData
from game.logic.wall import DEAD_WALL_SIZE, DeadWall, TileStack, Wall
from game.logic.win import (
    get_waiting_tiles,
    is_kokushi_chankan_possible,
    is_kokushi_tenpai,
)
from game.tests.conftest import create_dealt_game_state, create_game_state, create_player, create_round_state
from game.tests.helpers.hands import tile_copies

if TYPE_CHECKING:
    from collections.abc import Sequence

_DEFAULT_DEAD_WALL = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
_DEFAULT_WALL = tuple(TilesConverter.string_to_136_array(man="1111222233334444"))


def _make_round_state(
    player0_tiles,
    *,
    player0_melds=(),
    player1_tiles=None,
    player1_melds=(),
    player2_tiles=None,
    player2_melds=(),
    player3_tiles=None,
    player3_melds=(),
    current_player_seat=0,
    wall=None,
    dead_wall=None,
    is_after_meld_call=False,
    pending_dora_count=0,
):
    players = [
        create_player(seat=0, tiles=player0_tiles, melds=player0_melds),
        create_player(
            seat=1,
            tiles=player1_tiles or TilesConverter.string_to_136_array(man="123", pin="123", sou="123456"),
            melds=player1_melds,
        ),
        create_player(
            seat=2,
            tiles=player2_tiles or TilesConverter.string_to_136_array(man="789", pin="789", sou="789", honors="1"),
            melds=player2_melds,
        ),
        create_player(
            seat=3,
            tiles=player3_tiles or TilesConverter.string_to_136_array(man="456", pin="456", sou="789", honors="2"),
            melds=player3_melds,
        ),
    ]
    rs = create_round_state(
        players=players,
        wall=wall or _DEFAULT_WALL,
        dead_wall=dead_wall or _DEFAULT_DEAD_WALL,
        dora_indicators=(dead_wall or _DEFAULT_DEAD_WALL)[2:3],
        current_player_seat=current_player_seat,
        pending_dora_count=pending_dora_count,
    )
    if is_after_meld_call:
        rs = rs.model_copy(update={"is_after_meld_call": True})

    return rs


# ---------------------------------------------------------------------------
# Minimum wall tiles for kan (configurable via settings.min_wall_for_kan)
# ---------------------------------------------------------------------------
class TestMinWallForKan:
    def test_closed_kan__when_min_wall_for_kan_setting_changes__should_require_that_many_wall_tiles(self):
        tiles_4m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player0_tiles = (*tiles_4m, *pin_tiles)
        round_state = _make_round_state(player0_tiles, wall=(10, 11))

        # default min_wall_for_kan=2: exactly 2 tiles → can kan
        settings = GameSettings()
        assert get_possible_closed_kans(round_state.players[0], round_state, settings=settings) == [
            tile_to_34(tiles_4m[0])
        ]

        # custom min_wall_for_kan=3: only 2 tiles → cannot kan
        settings_3 = GameSettings(min_wall_for_kan=3)
        assert get_possible_closed_kans(round_state.players[0], round_state, settings=settings_3) == []


# ---------------------------------------------------------------------------
# Kan after pon/chi on same turn: not allowed (fundamental)
# ---------------------------------------------------------------------------
class TestKanAfterMeldCallBlocked:
    def test_closed_kan__when_after_meld_call__should_not_be_possible(self):
        tiles_4m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="1234567")
        player0_tiles = (*tiles_4m, *pin_tiles)
        round_state = _make_round_state(player0_tiles, is_after_meld_call=True)

        settings = GameSettings()
        result = get_possible_closed_kans(round_state.players[0], round_state, settings=settings)
        assert result == []

    def test_added_kan__when_after_meld_call__should_not_be_possible(self):
        # player has a pon of 1m and the 4th copy in hand
        tiles_1m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        # 3 tiles in pon, 1 in hand
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(tiles_1m[:3]),
            opened=True,
            called_tile=tiles_1m[2],
            who=0,
            from_who=1,
        )
        player0_tiles = (tiles_1m[3], *pin_tiles)
        round_state = _make_round_state(
            player0_tiles,
            player0_melds=(pon_meld,),
            is_after_meld_call=True,
        )

        settings = GameSettings()
        result = get_possible_added_kans(round_state.players[0], round_state, settings=settings)
        assert result == []

    def test_closed_kan__when_not_after_meld_call__should_be_possible(self):
        tiles_4m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player0_tiles = (*tiles_4m, *pin_tiles)
        round_state = _make_round_state(player0_tiles, is_after_meld_call=False)

        settings = GameSettings()
        result = get_possible_closed_kans(round_state.players[0], round_state, settings=settings)
        assert result == [tile_to_34(tiles_4m[0])]


# ---------------------------------------------------------------------------
# Consecutive concealed quads: allowed, each reveals new dora (fundamental)
# ---------------------------------------------------------------------------
class TestConsecutiveClosedKans:
    def test_closed_kan__when_second_kan_follows_first__should_allow_it_and_reveal_new_dora(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        man_2m = TilesConverter.string_to_136_array(man="2222")
        pin_tiles = TilesConverter.string_to_136_array(pin="12345")
        player0_tiles = (*man_1m, *man_2m, *pin_tiles)
        round_state = _make_round_state(player0_tiles)
        settings = GameSettings()

        # first kan
        new_state, meld1 = call_closed_kan(round_state, seat=0, tile_id=man_1m[0], settings=settings)
        assert meld1.type == FrozenMeld.KAN
        dora_count_1 = len(new_state.wall.dora_indicators)

        # second kan should also be possible
        possible = get_possible_closed_kans(new_state.players[0], new_state, settings=settings)
        man_2m_34 = tile_to_34(man_2m[0])
        assert man_2m_34 in possible

        new_state2, meld2 = call_closed_kan(new_state, seat=0, tile_id=man_2m[0], settings=settings)
        assert meld2.type == FrozenMeld.KAN
        # each kan should reveal a new dora indicator (immediate for closed kan)
        assert len(new_state2.wall.dora_indicators) == dora_count_1 + 1


_FIVE_MAN = tuple(tile_copies(copy, man="5")[0] for copy in range(4))
_EIGHT_PIN = tuple(tile_copies(copy, pin="8")[0] for copy in range(4))
_SEAT_0_KANS = (
    FrozenMeld(meld_type=FrozenMeld.KAN, tiles=tuple(tile_copies(0, sou="1111")), opened=False, who=0, from_who=0),
    FrozenMeld(meld_type=FrozenMeld.KAN, tiles=tuple(tile_copies(0, sou="9999")), opened=False, who=0, from_who=0),
)
_SEAT_1 = create_player(
    seat=1,
    tiles=tile_copies(0, man="13", pin="579", sou="246", honors="12"),
    melds=(
        FrozenMeld(
            meld_type=FrozenMeld.KAN, tiles=tuple(tile_copies(0, honors="4444")), opened=False, who=1, from_who=1
        ),
    ),
)
_SEAT_2_TILES = tuple(tile_copies(0, man="679", pin="123", sou="3578", honors="356"))
_SEAT_3_TILES = (*tile_copies(2, man="234", pin="567", sou="345"), _EIGHT_PIN[0])
_RINSHAN_COMPLETING_SEAT_3 = _EIGHT_PIN[3]
_CHUN_TRIPLET = tuple(tile_copies(0, honors="777"))


def _game_with_three_kans_on_table(
    players: tuple[MahjongPlayer, ...],
    *,
    current_player_seat: int,
    all_discards: tuple[int, ...] = (),
    settings: GameSettings | None = None,
) -> MahjongGameState:
    in_play = {
        tile
        for player in players
        for tile in (*player.tiles, *(t for m in player.melds for t in m.tiles), *(d.tile_id for d in player.discards))
    }
    free = [tile for tile in range(NUM_TILES) if tile not in in_play and tile != _RINSHAN_COMPLETING_SEAT_3]
    dead = (_RINSHAN_COMPLETING_SEAT_3, *free[1 - DEAD_WALL_SIZE :])
    dead_wall = DeadWall(
        rinshan=(dead[0],),
        reserve=tuple(dead[1:4]),
        indicators=tuple(TileStack(top=dead[i], bottom=dead[i + 1]) for i in range(4, DEAD_WALL_SIZE, 2)),
        revealed_count=4,
    )
    round_state = create_round_state(
        players=players,
        wall_obj=Wall(live_tiles=tuple(free[: 1 - DEAD_WALL_SIZE]), dead_wall=dead_wall),
        current_player_seat=current_player_seat,
        all_discards=all_discards,
        phase=RoundPhase.PLAYING,
    )
    game_state = create_game_state(round_state, settings=settings)
    verify_tile_ownership(game_state)
    assert check_four_kans(round_state, game_state.settings) is False
    return game_state


def _declare_kan(game_state: MahjongGameState, *, seat: int, tile_id: int, kan_type: KanType) -> ActionResult:
    result = handle_kan(game_state, seat=seat, data=KanActionData(tile_id=tile_id, kan_type=kan_type))
    assert isinstance(result, ActionResult)
    assert result.state.round_state.phase == RoundPhase.PLAYING
    assert check_four_kans(result.state.round_state, result.state.settings) is True
    return result


def _discard(game_state: MahjongGameState, *, seat: int, tile_id: int) -> ActionResult:
    result = handle_discard(game_state, seat=seat, data=DiscardActionData(tile_id=tile_id))
    assert isinstance(result, ActionResult)
    return result


def _assert_four_kans_abort(result: ActionResult | Refusal) -> None:
    assert isinstance(result, ActionResult)
    assert result.state.round_state.phase == RoundPhase.FINISHED
    round_ends = [e for e in result.events if isinstance(e, RoundEndEvent)]
    assert len(round_ends) == 1
    assert round_ends[0].result.type == RoundResultType.ABORTIVE_DRAW
    assert round_ends[0].result.reason == AbortiveDrawType.FOUR_KANS


def _ronnable_replacement_discard() -> ActionResult:
    shanpon_on_eight_pin_with_chun = (_EIGHT_PIN[1], _EIGHT_PIN[2], *tile_copies(0, man="22"), *_CHUN_TRIPLET)
    players = (
        create_player(seat=0, tiles=shanpon_on_eight_pin_with_chun, melds=_SEAT_0_KANS),
        _SEAT_1,
        create_player(seat=2, tiles=_SEAT_2_TILES),
        create_player(seat=3, tiles=(*_SEAT_3_TILES, *_FIVE_MAN)),
    )
    game_state = _game_with_three_kans_on_table(players, current_player_seat=3)
    assert can_call_pon(players[0], _EIGHT_PIN[0])

    kan = _declare_kan(game_state, seat=3, tile_id=_FIVE_MAN[0], kan_type=KanType.CLOSED)
    assert [type(e) for e in kan.events] == [MeldEvent, DoraRevealedEvent, DrawEvent]

    discard = _discard(kan.state, seat=3, tile_id=_EIGHT_PIN[0])
    prompt = discard.state.round_state.pending_call_prompt
    assert prompt is not None
    assert prompt.callers == (Caller(seat=0, can_ron=True),)
    return discard


class TestFourKansAbortTiming:
    def test_four_kans_abort__when_open_fourth_kan_replacement_discard_passes__should_reveal_kan_dora_then_abort(self):
        pair_of_eight_pin_waiting_on_three_man = (
            _EIGHT_PIN[1],
            _EIGHT_PIN[2],
            *tile_copies(0, man="24"),
            *_CHUN_TRIPLET,
        )
        players = (
            create_player(seat=0, tiles=pair_of_eight_pin_waiting_on_three_man, melds=_SEAT_0_KANS),
            _SEAT_1,
            create_player(seat=2, tiles=(*_SEAT_2_TILES, _FIVE_MAN[0])),
            create_player(seat=3, tiles=(*_SEAT_3_TILES, *_FIVE_MAN[1:])),
        )
        game_state = _game_with_three_kans_on_table(players, current_player_seat=2)
        assert can_call_pon(players[0], _EIGHT_PIN[0])

        kan_offer = _discard(game_state, seat=2, tile_id=_FIVE_MAN[0])
        kan = _declare_kan(kan_offer.state, seat=3, tile_id=_FIVE_MAN[0], kan_type=KanType.OPEN)
        assert [type(e) for e in kan.events] == [MeldEvent, DrawEvent]
        rinshan_draw = kan.events[1]
        assert isinstance(rinshan_draw, DrawEvent)
        assert rinshan_draw.tile_id == _RINSHAN_COMPLETING_SEAT_3
        assert PlayerAction.TSUMO in {item.action for item in rinshan_draw.available_actions}
        assert kan.state.round_state.wall.pending_dora_count == 1

        replacement_discard = _discard(kan.state, seat=3, tile_id=_EIGHT_PIN[0])
        assert replacement_discard.state.round_state.pending_call_prompt is None
        assert [type(e) for e in replacement_discard.events] == [DiscardEvent, DoraRevealedEvent, RoundEndEvent]
        kan_dora = replacement_discard.events[1]
        assert isinstance(kan_dora, DoraRevealedEvent)
        assert kan_dora.tile_id == game_state.round_state.wall.dead_wall.indicators[4].top
        _assert_four_kans_abort(replacement_discard)

    def test_four_kans_abort__when_replacement_discard_is_ronned__should_score_the_ron(self):
        discard = _ronnable_replacement_discard()

        ron = handle_ron(discard.state, seat=0)
        assert isinstance(ron, ActionResult)
        round_ends = [e for e in ron.events if isinstance(e, RoundEndEvent)]
        assert len(round_ends) == 1
        assert round_ends[0].result.type == RoundResultType.RON
        assert round_ends[0].result.winner_seat == 0
        assert round_ends[0].result.loser_seat == 3

    def test_four_kans_abort__when_ron_caller_passes_replacement_discard__should_abort(self):
        discard = _ronnable_replacement_discard()

        _assert_four_kans_abort(handle_pass(discard.state, seat=0))

    def test_four_kans_abort__when_chankan_on_fourth_kan_is_declined__should_draw_replacement_then_abort(self):
        kanchan_on_five_man_with_chun = (*tile_copies(1, man="46"), _EIGHT_PIN[1], _EIGHT_PIN[2], *_CHUN_TRIPLET)
        five_man_pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=_FIVE_MAN[:3],
            opened=True,
            called_tile=_FIVE_MAN[0],
            who=3,
            from_who=2,
        )
        players = (
            create_player(seat=0, tiles=kanchan_on_five_man_with_chun, melds=_SEAT_0_KANS),
            _SEAT_1,
            create_player(seat=2, tiles=_SEAT_2_TILES, discards=(Discard(tile_id=_FIVE_MAN[0]),)),
            create_player(seat=3, tiles=(*_SEAT_3_TILES, _FIVE_MAN[3]), melds=(five_man_pon,)),
        )
        game_state = _game_with_three_kans_on_table(players, current_player_seat=3, all_discards=(_FIVE_MAN[0],))

        chankan_offer = handle_kan(game_state, seat=3, data=KanActionData(tile_id=_FIVE_MAN[3], kan_type=KanType.ADDED))
        assert isinstance(chankan_offer, ActionResult)
        prompt = chankan_offer.state.round_state.pending_call_prompt
        assert prompt is not None
        assert prompt.kind == PromptKind.CHANKAN
        assert prompt.callers == (Caller(seat=0, can_ron=True),)

        declined = handle_pass(chankan_offer.state, seat=0)
        assert isinstance(declined, ActionResult)
        assert declined.state.round_state.phase == RoundPhase.PLAYING
        assert [type(e) for e in declined.events] == [MeldEvent, DrawEvent]
        assert check_four_kans(declined.state.round_state, declined.state.settings) is True

        _assert_four_kans_abort(_discard(declined.state, seat=3, tile_id=_EIGHT_PIN[0]))


def _assert_play_continues_to_seat(result: ActionResult, seat: int) -> None:
    assert result.state.round_state.phase == RoundPhase.PLAYING
    assert [type(e) for e in result.events] == [DiscardEvent]
    assert result.state.round_state.current_player_seat == seat


class TestFourKansAbort:
    def test_four_kans_abort__when_one_player_declares_all_four_kans__should_not_abort(self):
        seat_0_third_kan = FrozenMeld(
            meld_type=FrozenMeld.KAN, tiles=tuple(tile_copies(0, honors="4444")), opened=False, who=0, from_who=0
        )
        lone_west = tile_copies(1, honors="6")[0]
        players = (
            create_player(seat=0, tiles=(*_FIVE_MAN, lone_west), melds=(*_SEAT_0_KANS, seat_0_third_kan)),
            create_player(seat=1, tiles=tile_copies(1, man="12346789", pin="12345")),
            create_player(seat=2, tiles=_SEAT_2_TILES),
            create_player(seat=3, tiles=(*_SEAT_3_TILES, *tile_copies(0, honors="111"))),
        )
        game_state = _game_with_three_kans_on_table(players, current_player_seat=0)

        kan = handle_kan(game_state, seat=0, data=KanActionData(tile_id=_FIVE_MAN[0], kan_type=KanType.CLOSED))
        assert isinstance(kan, ActionResult)
        assert len(kan.state.round_state.players[0].melds) == 4

        _assert_play_continues_to_seat(_discard(kan.state, seat=0, tile_id=lone_west), seat=1)

    def test_four_kans_abort__when_min_players_setting_is_3__should_not_abort_with_two_players(self):
        seat_3_kan = FrozenMeld(
            meld_type=FrozenMeld.KAN, tiles=tuple(tile_copies(0, honors="4444")), opened=False, who=3, from_who=3
        )
        lone_west = tile_copies(1, honors="6")[0]
        players = (
            create_player(
                seat=0,
                tiles=(_EIGHT_PIN[1], _EIGHT_PIN[2], *tile_copies(0, man="24"), *_CHUN_TRIPLET),
                melds=_SEAT_0_KANS,
            ),
            create_player(seat=1, tiles=tile_copies(1, man="12346789", pin="12345")),
            create_player(seat=2, tiles=_SEAT_2_TILES),
            create_player(
                seat=3,
                tiles=(*_FIVE_MAN, *tile_copies(2, man="234", pin="567"), lone_west),
                melds=(seat_3_kan,),
            ),
        )
        game_state = _game_with_three_kans_on_table(
            players,
            current_player_seat=3,
            settings=GameSettings(min_players_for_kan_abort=3),
        )

        kan = handle_kan(game_state, seat=3, data=KanActionData(tile_id=_FIVE_MAN[0], kan_type=KanType.CLOSED))
        assert isinstance(kan, ActionResult)
        assert check_four_kans(kan.state.round_state, GameSettings()) is True

        _assert_play_continues_to_seat(_discard(kan.state, seat=3, tile_id=lone_west), seat=0)


# ---------------------------------------------------------------------------
# Kan dora timing (configurable)
# ---------------------------------------------------------------------------
class TestKanDoraTiming:
    def test_kan_dora__when_closed_kan_by_default__should_reveal_dora_immediately(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player0_tiles = (*man_1m, *pin_tiles)
        round_state = _make_round_state(player0_tiles)
        settings = GameSettings()  # kandora_immediate_for_closed_kan=True

        initial_dora_count = len(round_state.wall.dora_indicators)
        new_state, _meld = call_closed_kan(round_state, seat=0, tile_id=man_1m[0], settings=settings)
        # dora immediately revealed
        assert len(new_state.wall.dora_indicators) == initial_dora_count + 1
        assert new_state.wall.pending_dora_count == 0

    def test_kan_dora__when_closed_kan_immediate_setting_off__should_defer_dora(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player0_tiles = (*man_1m, *pin_tiles)
        round_state = _make_round_state(player0_tiles)
        settings = GameSettings(kandora_immediate_for_closed_kan=False)

        initial_dora_count = len(round_state.wall.dora_indicators)
        new_state, _meld = call_closed_kan(round_state, seat=0, tile_id=man_1m[0], settings=settings)
        # dora not immediately revealed, pending instead
        assert len(new_state.wall.dora_indicators) == initial_dora_count
        assert new_state.wall.pending_dora_count == 1

    def test_kan_dora__when_open_kan_by_default__should_defer_dora(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        # player 0 has 3 copies, player 3 discards the 4th
        player0_tiles = (*man_1m[:3], *pin_tiles)
        round_state = _make_round_state(player0_tiles, current_player_seat=3)
        settings = GameSettings()  # kandora_deferred_for_open_kan=True

        initial_dora_count = len(round_state.wall.dora_indicators)
        new_state, _meld = call_open_kan(
            round_state,
            caller_seat=0,
            discarder_seat=3,
            tile_id=man_1m[3],
            settings=settings,
        )
        # dora deferred
        assert len(new_state.wall.dora_indicators) == initial_dora_count
        assert new_state.wall.pending_dora_count == 1

    def test_kan_dora__when_open_kan_deferred_setting_off__should_reveal_dora_immediately(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player0_tiles = (*man_1m[:3], *pin_tiles)
        round_state = _make_round_state(player0_tiles, current_player_seat=3)
        settings = GameSettings(kandora_deferred_for_open_kan=False)

        initial_dora_count = len(round_state.wall.dora_indicators)
        new_state, _meld = call_open_kan(
            round_state,
            caller_seat=0,
            discarder_seat=3,
            tile_id=man_1m[3],
            settings=settings,
        )
        # dora immediately revealed
        assert len(new_state.wall.dora_indicators) == initial_dora_count + 1
        assert new_state.wall.pending_dora_count == 0

    def test_kan_dora__when_added_kan_by_default__should_defer_dora(self):
        tiles_1m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(tiles_1m[:3]),
            opened=True,
            called_tile=tiles_1m[2],
            who=0,
            from_who=1,
        )
        player0_tiles = (tiles_1m[3], *pin_tiles)
        round_state = _make_round_state(player0_tiles, player0_melds=(pon_meld,))
        settings = GameSettings()  # kandora_deferred_for_open_kan=True

        initial_dora_count = len(round_state.wall.dora_indicators)
        new_state, _meld = call_added_kan(round_state, seat=0, tile_id=tiles_1m[3], settings=settings)
        # dora deferred
        assert len(new_state.wall.dora_indicators) == initial_dora_count
        assert new_state.wall.pending_dora_count == 1

    def test_kan_dora__when_kandora_disabled__should_not_reveal_dora(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player0_tiles = (*man_1m, *pin_tiles)
        round_state = _make_round_state(player0_tiles)
        settings = GameSettings(has_kandora=False)

        initial_dora_count = len(round_state.wall.dora_indicators)
        new_state, _meld = call_closed_kan(round_state, seat=0, tile_id=man_1m[0], settings=settings)
        assert len(new_state.wall.dora_indicators) == initial_dora_count
        assert new_state.wall.pending_dora_count == 0


# ---------------------------------------------------------------------------
# Kokushi tenpai detection
# ---------------------------------------------------------------------------
class TestIsKokushiTenpai:
    def test_is_kokushi_tenpai__when_12_types_with_pair__should_return_true(self):
        # missing chun (7z), pair of 1m → waiting for chun
        tiles = TilesConverter.string_to_136_array(man="119", pin="19", sou="19", honors="123456")
        player = create_player(seat=0, tiles=tiles)
        assert is_kokushi_tenpai(player) is True

    def test_is_kokushi_tenpai__when_all_13_types__should_return_true(self):
        tiles = TilesConverter.string_to_136_array(man="19", pin="19", sou="19", honors="1234567")
        player = create_player(seat=0, tiles=tiles)
        assert is_kokushi_tenpai(player) is True

    def test_is_kokushi_tenpai__when_player_has_meld__should_return_false(self):
        tiles = TilesConverter.string_to_136_array(man="19", pin="19", sou="19", honors="1234567")
        meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(TilesConverter.string_to_136_array(honors="111")),
            opened=True,
            who=0,
            from_who=1,
        )
        player = create_player(seat=0, tiles=tiles[:10], melds=(meld,))
        assert is_kokushi_tenpai(player) is False

    def test_is_kokushi_tenpai__when_hand_has_non_terminal_suited_tile__should_return_false(self):
        tiles = TilesConverter.string_to_136_array(man="15", pin="19", sou="19", honors="1234567")
        player = create_player(seat=0, tiles=tiles)
        assert is_kokushi_tenpai(player) is False

    def test_is_kokushi_tenpai__when_only_11_types__should_return_false(self):
        # missing 9s and 9p, extra 1m copies → 11 unique types
        tiles = TilesConverter.string_to_136_array(man="119", pin="1", sou="1", honors="12345677")
        player = create_player(seat=0, tiles=tiles)
        assert is_kokushi_tenpai(player) is False


# ---------------------------------------------------------------------------
# Chankan on ankan: only kokushi may rob (fundamental)
# ---------------------------------------------------------------------------
class TestKokushiChankanOnAnkan:
    def test_kokushi_chankan__when_kokushi_waits_on_closed_kan_tile__should_allow_robbing(self):
        # player 1 has kokushi tenpai, missing 1m (pair of 9m)
        kokushi_tiles = TilesConverter.string_to_136_array(man="99", pin="19", sou="19", honors="1234567")
        # player 0 declares closed kan on 1m
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player0_tiles = (*man_1m, *pin_tiles)

        round_state = _make_round_state(
            player0_tiles,
            player1_tiles=kokushi_tiles,
        )

        chankan_seats = is_kokushi_chankan_possible(round_state, caller_seat=0, kan_tile=man_1m[0])
        assert 1 in chankan_seats

    def test_kokushi_chankan__when_tenpai_hand_is_not_kokushi__should_not_allow_robbing_closed_kan(self):
        one_man = tile_copies(0, man="1111")
        regular_tenpai_on_one_man = create_player(seat=1, tiles=tile_copies(0, man="23456789", pin="12355"))
        players = (
            create_player(seat=0, tiles=(*one_man, *tile_copies(1, sou="123456789"), *tile_copies(0, honors="1"))),
            regular_tenpai_on_one_man,
            create_player(seat=2, tiles=(*tile_copies(2, pin="123456789"), *tile_copies(0, honors="2345"))),
            create_player(seat=3, tiles=(*tile_copies(3, pin="123456789"), *tile_copies(1, honors="2345"))),
        )
        round_state = create_dealt_game_state(players).round_state
        assert tile_to_34(one_man[0]) in get_waiting_tiles(regular_tenpai_on_one_man)

        assert is_kokushi_chankan_possible(round_state, caller_seat=0, kan_tile=one_man[0]) == []

    def test_kokushi_chankan__when_kokushi_is_permanent_furiten__should_not_allow_robbing(self):
        # kokushi tenpai missing 1m (pair of 9m)
        kokushi_tiles = TilesConverter.string_to_136_array(man="99", pin="19", sou="19", honors="1234567")
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player0_tiles = (*man_1m, *pin_tiles)

        players = [
            create_player(seat=0, tiles=player0_tiles),
            create_player(
                seat=1,
                tiles=kokushi_tiles,
                # discarded 1m previously → permanent furiten on 1m wait
                discards=(Discard(tile_id=TilesConverter.string_to_136_array(man="1")[0], is_tsumogiri=False),),
            ),
            create_player(
                seat=2,
                tiles=TilesConverter.string_to_136_array(man="789", pin="789", sou="789", honors="1"),
            ),
            create_player(
                seat=3,
                tiles=TilesConverter.string_to_136_array(man="456", pin="456", sou="789", honors="2"),
            ),
        ]
        round_state = create_round_state(
            players=players,
            wall=_DEFAULT_WALL,
            dead_wall=_DEFAULT_DEAD_WALL,
            dora_indicators=_DEFAULT_DEAD_WALL[2:3],
        )

        chankan_seats = is_kokushi_chankan_possible(round_state, caller_seat=0, kan_tile=man_1m[0])
        assert chankan_seats == []

    def test_process_closed_kan_call__when_kokushi_can_rob__should_create_chankan_prompt(self):
        # kokushi tenpai missing 1m (pair of 9m)
        kokushi_tiles = TilesConverter.string_to_136_array(man="99", pin="19", sou="19", honors="1234567")
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player0_tiles = (*man_1m, *pin_tiles)

        round_state = _make_round_state(
            player0_tiles,
            player1_tiles=kokushi_tiles,
        )
        game_state = create_game_state(round_state)

        new_gs, events = _process_closed_kan_call(game_state, caller_seat=0, tile_id=man_1m[0])
        new_rs = new_gs.round_state
        # should create a chankan prompt, not execute the kan
        chankan_events = [e for e in events if isinstance(e, CallPromptEvent) and e.call_type == CallType.CHANKAN]
        assert len(chankan_events) == 1
        assert new_rs.pending_call_prompt is not None
        assert new_rs.pending_call_prompt.kind == PromptKind.CHANKAN

    def test_process_closed_kan_call__when_no_kokushi_can_rob__should_execute_kan(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player0_tiles = (*man_1m, *pin_tiles)

        round_state = _make_round_state(player0_tiles)
        game_state = create_game_state(round_state)

        new_gs, events = _process_closed_kan_call(game_state, caller_seat=0, tile_id=man_1m[0])
        new_rs = new_gs.round_state
        # should execute the kan (MeldEvent, not CallPromptEvent)
        meld_events = [e for e in events if isinstance(e, MeldEvent) and e.meld_type == MeldViewType.CLOSED_KAN]
        assert len(meld_events) == 1
        assert new_rs.pending_call_prompt is None


# ---------------------------------------------------------------------------
# Chankan preservation: ippatsu not cleared, dora not flipped (fundamental)
# ---------------------------------------------------------------------------
class TestChankanPreservation:
    def test_chankan_prompt__when_added_kan_declared__should_preserve_ippatsu(self):
        # player 1 has ippatsu and is tenpai waiting on 3p
        tiles_p1 = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        pin_3 = TilesConverter.string_to_136_array(pin="3333")
        pin_other = TilesConverter.string_to_136_array(pin="6789", sou="12345")

        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pin_3[:3]),
            opened=True,
            called_tile=pin_3[2],
            who=0,
            from_who=3,
        )
        # player 0 has pon of 3p + 4th copy in hand, tries added kan
        player0_tiles = (pin_3[3], *pin_other)

        players = [
            create_player(seat=0, tiles=player0_tiles, melds=(pon_meld,)),
            create_player(seat=1, tiles=tiles_p1, is_riichi=True, is_ippatsu=True),
            create_player(
                seat=2,
                tiles=TilesConverter.string_to_136_array(man="789", pin="789", sou="789", honors="1"),
            ),
            create_player(
                seat=3,
                tiles=TilesConverter.string_to_136_array(man="456", pin="456", sou="789", honors="2"),
            ),
        ]
        round_state = create_round_state(
            players=players,
            wall=_DEFAULT_WALL,
            dead_wall=_DEFAULT_DEAD_WALL,
            dora_indicators=_DEFAULT_DEAD_WALL[2:3],
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        new_gs, events = _process_added_kan_call(game_state, caller_seat=0, tile_id=pin_3[3])
        new_rs = new_gs.round_state
        # chankan prompt should be created (not executing the kan)
        chankan_events = [e for e in events if isinstance(e, CallPromptEvent) and e.call_type == CallType.CHANKAN]
        assert len(chankan_events) == 1
        # ippatsu should be preserved (kan not executed yet)
        assert new_rs.players[1].is_ippatsu is True

    def test_chankan_prompt__when_added_kan_declared__should_not_reveal_dora(self):
        tiles_p1 = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        pin_3 = TilesConverter.string_to_136_array(pin="3333")
        pin_other = TilesConverter.string_to_136_array(pin="6789", sou="12345")

        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pin_3[:3]),
            opened=True,
            called_tile=pin_3[2],
            who=0,
            from_who=3,
        )
        player0_tiles = (pin_3[3], *pin_other)

        players = [
            create_player(seat=0, tiles=player0_tiles, melds=(pon_meld,)),
            create_player(seat=1, tiles=tiles_p1, is_riichi=True),
            create_player(
                seat=2,
                tiles=TilesConverter.string_to_136_array(man="789", pin="789", sou="789", honors="1"),
            ),
            create_player(
                seat=3,
                tiles=TilesConverter.string_to_136_array(man="456", pin="456", sou="789", honors="2"),
            ),
        ]
        round_state = create_round_state(
            players=players,
            wall=_DEFAULT_WALL,
            dead_wall=_DEFAULT_DEAD_WALL,
            dora_indicators=_DEFAULT_DEAD_WALL[2:3],
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        initial_dora_count = len(round_state.wall.dora_indicators)
        new_gs, _events = _process_added_kan_call(game_state, caller_seat=0, tile_id=pin_3[3])
        new_rs = new_gs.round_state
        # dora should not be revealed (kan not executed yet)
        assert len(new_rs.wall.dora_indicators) == initial_dora_count
        assert new_rs.wall.pending_dora_count == 0


# ---------------------------------------------------------------------------
# Action handler guard: kan after meld call raises error
# ---------------------------------------------------------------------------
class TestHandleSelfKanAfterMeld:
    def test_handle_self_kan__when_after_meld_call__should_raise(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player0_tiles = (*man_1m, *pin_tiles)

        round_state = _make_round_state(player0_tiles)
        round_state = round_state.model_copy(update={"is_after_meld_call": True})
        game_state = create_game_state(round_state)

        data = KanActionData(tile_id=man_1m[0], kan_type=KanType.CLOSED)
        with pytest.raises(InvalidGameActionError, match="cannot declare kan after a meld call"):
            _handle_self_kan(game_state, seat=0, data=data)


def _riichi_seat_after_draw(waiting_hand: Sequence[int], drawn_tile: int) -> GameRuntime:
    players = (
        create_player(
            seat=0,
            tiles=(*waiting_hand, drawn_tile),
            discards=(Discard(tile_id=tile_copies(0, honors="1")[0], is_riichi_discard=True),),
            is_riichi=True,
        ),
        create_player(
            seat=1,
            tiles=tile_copies(1, pin="123456789", honors="1567"),
            discards=(Discard(tile_id=tile_copies(0, honors="2")[0]),),
        ),
        create_player(
            seat=2,
            tiles=tile_copies(2, pin="123456789", honors="1567"),
            discards=(Discard(tile_id=tile_copies(0, honors="3")[0]),),
        ),
        create_player(
            seat=3,
            tiles=tile_copies(3, pin="123456789", honors="1567"),
            discards=(Discard(tile_id=tile_copies(0, honors="4")[0]),),
        ),
    )
    all_discards = tuple(player.discards[0].tile_id for player in players)
    dealt = {tile for player in players for tile in player.tiles} | set(all_discards)
    undealt = [tile for tile in range(NUM_TILES) if tile not in dealt]
    round_state = create_round_state(
        players=players,
        wall=undealt[:-DEAD_WALL_SIZE],
        dead_wall=undealt[-DEAD_WALL_SIZE:],
        phase=RoundPhase.PLAYING,
        all_discards=all_discards,
    )
    return GameRuntime(game_id="game1", state=create_game_state(round_state), ai=AIPlayerController({}))


def _declare_closed_kan(runtime: GameRuntime, tile_id: int) -> None:
    MahjongGameService().handle_action(
        runtime,
        seat=0,
        action=GameAction.CALL_KAN,
        data={"tile_id": tile_id, "kan_type": KanType.CLOSED},
    )


def _offered_closed_kans(runtime: GameRuntime) -> list[int] | None:
    offered = [item for item in get_available_actions(runtime.state, seat=0) if item.action == PlayerAction.KAN]
    return offered[0].tiles if offered else None


def _waits(player: MahjongPlayer, waiting_hand: Sequence[int]) -> set[int]:
    return get_waiting_tiles(player.model_copy(update={"tiles": tuple(waiting_hand)}))


class TestRiichiClosedKanValidation:
    def test_closed_kan__when_riichi_seat_holds_three_copies_of_drawn_tile__should_kick_seat(self):
        drawn_one_man = tile_copies(2, man="1")[0]
        runtime = _riichi_seat_after_draw(tile_copies(0, man="11", pin="123456789", sou="12"), drawn_one_man)
        game_state = runtime.state

        with pytest.raises(InvalidGameActionError, match="closed kan requires 4 tiles"):
            _declare_closed_kan(runtime, drawn_one_man)
        assert runtime.state is game_state

    def test_closed_kan__when_riichi_seat_quads_a_tile_held_before_the_draw__should_kick_seat(self):
        waiting_hand = tile_copies(0, man="111123", pin="456789", sou="5")
        runtime = _riichi_seat_after_draw(waiting_hand, tile_copies(0, sou="9")[0])
        game_state = runtime.state

        assert _offered_closed_kans(runtime) is None
        with pytest.raises(InvalidGameActionError, match="drawn tile must be the kan tile"):
            _declare_closed_kan(runtime, waiting_hand[0])
        assert runtime.state is game_state

    @pytest.mark.parametrize(
        ("waiting_hand", "drawn_tile", "waits_before", "waits_after"),
        [
            pytest.param(
                tile_copies(0, man="6888999", pin="123", sou="456"),
                tile_copies(3, man="8")[0],
                {tile_to_34(t) for t in tile_copies(0, man="67")},
                {tile_to_34(t) for t in tile_copies(0, man="6")},
                id="narrows_waits",
            ),
            pytest.param(
                tile_copies(0, man="1113444556779"),
                tile_copies(3, man="4")[0],
                {tile_to_34(t) for t in tile_copies(0, man="8")},
                set(),
                id="breaks_tenpai",
            ),
            pytest.param(
                tile_copies(0, man="1112344", pin="123", sou="456"),
                tile_copies(3, man="1")[0],
                {tile_to_34(t) for t in tile_copies(0, man="14")},
                {tile_to_34(t) for t in tile_copies(0, man="4")},
                id="kan_tile_is_a_wait",
            ),
        ],
    )
    def test_closed_kan__when_riichi_kan_changes_the_waits__should_not_offer_it_and_kick_seat(
        self, waiting_hand, drawn_tile, waits_before, waits_after
    ):
        runtime = _riichi_seat_after_draw(waiting_hand, drawn_tile)
        game_state = runtime.state
        player = game_state.round_state.players[0]
        kan_tile_34 = tile_to_34(drawn_tile)
        hand_without_quad = [t for t in waiting_hand if tile_to_34(t) != kan_tile_34]
        quad = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(t for t in player.tiles if tile_to_34(t) == kan_tile_34),
            opened=False,
            who=0,
        )
        assert _waits(player, waiting_hand) == waits_before
        assert _waits(player.model_copy(update={"melds": (quad,)}), hand_without_quad) == waits_after

        assert _offered_closed_kans(runtime) is None
        with pytest.raises(InvalidGameActionError, match="must not change waiting tiles"):
            _declare_closed_kan(runtime, drawn_tile)
        assert runtime.state is game_state

    def test_closed_kan__when_riichi_kan_keeps_the_waits_but_loses_ippeikou__should_declare_it(self):
        waiting_hand = tile_copies(0, man="111222333", pin="456", sou="5")
        drawn_one_man = tile_copies(3, man="1")[0]
        five_sou_wait = {tile_to_34(tile_copies(0, sou="5")[0])}
        runtime = _riichi_seat_after_draw(waiting_hand, drawn_one_man)
        assert _waits(runtime.state.round_state.players[0], waiting_hand) == five_sou_wait

        assert _offered_closed_kans(runtime) == [tile_to_34(drawn_one_man)]
        _declare_closed_kan(runtime, drawn_one_man)
        player = runtime.state.round_state.players[0]
        assert [(meld.type, meld.opened, tile_to_34(meld.tiles[0])) for meld in player.melds] == [
            (FrozenMeld.KAN, False, tile_to_34(drawn_one_man))
        ]
        assert _waits(player, player.tiles[:-1]) == five_sou_wait


# ---------------------------------------------------------------------------
# Resolve chankan decline for closed kan (kokushi chankan)
# ---------------------------------------------------------------------------
class TestResolveChankanDeclineClosedKan:
    def test_resolve_chankan_decline__when_closed_kan__should_complete_kan(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player0_tiles = (*man_1m, *pin_tiles)

        round_state = _make_round_state(player0_tiles)
        round_state = round_state.model_copy(update={"phase": RoundPhase.PLAYING})
        game_state = create_game_state(round_state)

        prompt = PendingCallPrompt(
            kind=PromptKind.CHANKAN,
            tile_id=man_1m[0],
            from_seat=0,
            pending_seats=frozenset(),
            callers=(Caller(seat=1, can_ron=True),),
            responses=(),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = resolve_call_prompt(game_state)
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.CLOSED_KAN


# ---------------------------------------------------------------------------
# Additional kokushi chankan edge cases for coverage
# ---------------------------------------------------------------------------
class TestKokushiChankanEdgeCases:
    def test_kokushi_chankan__when_kokushi_waits_on_other_tile__should_not_allow_robbing(self):
        # kokushi tenpai missing 1m (waiting on 1m), but kan tile is 2m
        kokushi_tiles = TilesConverter.string_to_136_array(man="99", pin="19", sou="19", honors="1234567")
        man_2m = TilesConverter.string_to_136_array(man="2222")
        pin_tiles = TilesConverter.string_to_136_array(pin="12345")
        player0_tiles = (*man_2m, *pin_tiles)

        players = [
            create_player(seat=0, tiles=player0_tiles),
            create_player(seat=1, tiles=kokushi_tiles),
            create_player(
                seat=2,
                tiles=TilesConverter.string_to_136_array(man="789", pin="789", sou="789", honors="1"),
            ),
            create_player(
                seat=3,
                tiles=TilesConverter.string_to_136_array(man="456", pin="456", sou="789", honors="2"),
            ),
        ]
        round_state = create_round_state(
            players=players,
            wall=_DEFAULT_WALL,
            dead_wall=_DEFAULT_DEAD_WALL,
            dora_indicators=_DEFAULT_DEAD_WALL[2:3],
            current_player_seat=0,
        )

        chankan_seats = is_kokushi_chankan_possible(round_state, caller_seat=0, kan_tile=man_2m[0])
        assert chankan_seats == []

    def test_kokushi_chankan__when_kokushi_is_riichi_furiten__should_not_allow_robbing(self):
        kokushi_tiles = TilesConverter.string_to_136_array(man="99", pin="19", sou="19", honors="1234567")
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player0_tiles = (*man_1m, *pin_tiles)

        players = [
            create_player(seat=0, tiles=player0_tiles),
            create_player(seat=1, tiles=kokushi_tiles, is_riichi=True, is_riichi_furiten=True),
            create_player(
                seat=2,
                tiles=TilesConverter.string_to_136_array(man="789", pin="789", sou="789", honors="1"),
            ),
            create_player(
                seat=3,
                tiles=TilesConverter.string_to_136_array(man="456", pin="456", sou="789", honors="2"),
            ),
        ]
        round_state = create_round_state(
            players=players,
            wall=_DEFAULT_WALL,
            dead_wall=_DEFAULT_DEAD_WALL,
            dora_indicators=_DEFAULT_DEAD_WALL[2:3],
            current_player_seat=0,
        )

        chankan_seats = is_kokushi_chankan_possible(round_state, caller_seat=0, kan_tile=man_1m[0])
        assert 1 not in chankan_seats

    def test_kokushi_chankan__when_kokushi_is_temporary_furiten__should_not_allow_robbing(self):
        kokushi_tiles = TilesConverter.string_to_136_array(man="99", pin="19", sou="19", honors="1234567")
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player0_tiles = (*man_1m, *pin_tiles)

        players = [
            create_player(seat=0, tiles=player0_tiles),
            create_player(seat=1, tiles=kokushi_tiles, is_temporary_furiten=True),
            create_player(
                seat=2,
                tiles=TilesConverter.string_to_136_array(man="789", pin="789", sou="789", honors="1"),
            ),
            create_player(
                seat=3,
                tiles=TilesConverter.string_to_136_array(man="456", pin="456", sou="789", honors="2"),
            ),
        ]
        round_state = create_round_state(
            players=players,
            wall=_DEFAULT_WALL,
            dead_wall=_DEFAULT_DEAD_WALL,
            dora_indicators=_DEFAULT_DEAD_WALL[2:3],
            current_player_seat=0,
        )

        chankan_seats = is_kokushi_chankan_possible(round_state, caller_seat=0, kan_tile=man_1m[0])
        assert 1 not in chankan_seats
