from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from mahjong.tile import TilesConverter

from game.logic.abortive import check_four_kans
from game.logic.action_handlers import handle_chi, handle_discard, handle_kan, handle_pass, handle_pon, handle_ron
from game.logic.action_result import ActionResult, Refusal
from game.logic.actions import get_available_actions
from game.logic.ai_player_controller import AIPlayerController
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
    SeatTarget,
)
from game.logic.exceptions import InvalidGameActionError
from game.logic.invariants import verify_tile_ownership
from game.logic.mahjong_service import MahjongGameService
from game.logic.meld_wrapper import FrozenMeld
from game.logic.melds import (
    can_call_pon,
    get_possible_added_kans,
    get_possible_closed_kans,
)
from game.logic.runtime import GameRuntime
from game.logic.settings import GameSettings
from game.logic.state import Caller, Discard, MahjongGameState, MahjongPlayer
from game.logic.tiles import NUM_TILES, tile_to_34
from game.logic.turn import process_discard_phase
from game.logic.types import ChiActionData, DiscardActionData, KanActionData, PonActionData
from game.logic.wall import DEAD_WALL_SIZE, DeadWall, TileStack, Wall
from game.logic.win import (
    get_waiting_tiles,
    is_kokushi_chankan_possible,
    is_kokushi_tenpai,
)
from game.tests.conftest import create_dealt_game_state, create_game_state, create_player, create_round_state
from game.tests.helpers.hands import tile_copies
from game.tests.unit.helpers import _update_round_state

if TYPE_CHECKING:
    from collections.abc import Sequence

_ONE_MAN = tuple(tile_copies(0, man="1111"))
_KAN_SEAT_REST = tuple(tile_copies(1, pin="123456789", sou="2"))
_FILLER = {seat: tuple(tile_copies(seat, man="34579", sou="345678", honors="56")) for seat in (1, 2, 3)}
_KOKUSHI_ON_ONE_MAN = create_player(seat=1, tiles=tile_copies(0, man="99", pin="19", sou="19", honors="1234567"))


def _kan_game(
    seat_0: MahjongPlayer,
    *,
    seat_1: MahjongPlayer | None = None,
    seat_3: MahjongPlayer | None = None,
    current_player_seat: int = 0,
    settings: GameSettings | None = None,
) -> MahjongGameState:
    players = (
        seat_0,
        seat_1 or create_player(seat=1, tiles=_FILLER[1]),
        create_player(seat=2, tiles=_FILLER[2]),
        seat_3 or create_player(seat=3, tiles=_FILLER[3]),
    )
    return create_dealt_game_state(players, current_player_seat=current_player_seat, settings=settings)


def _one_man_quad_after_draw() -> MahjongPlayer:
    return create_player(seat=0, tiles=(*_ONE_MAN, *_KAN_SEAT_REST))


def _one_man_pon_from_seat_3() -> FrozenMeld:
    return FrozenMeld(
        meld_type=FrozenMeld.PON, tiles=_ONE_MAN[:3], opened=True, called_tile=_ONE_MAN[2], who=0, from_who=3
    )


def _seat_3_after_discarding(tile_id: int) -> MahjongPlayer:
    return create_player(seat=3, tiles=_FILLER[3], discards=(Discard(tile_id=tile_id),))


def _call_kan(game_state: MahjongGameState, *, seat: int, tile_id: int, kan_type: KanType) -> ActionResult:
    result = handle_kan(game_state, seat=seat, data=KanActionData(tile_id=tile_id, kan_type=kan_type))
    assert isinstance(result, ActionResult)
    return result


def _open_kan_on_seat_3_discard(settings: GameSettings) -> tuple[MahjongGameState, MahjongGameState]:
    seat_0 = create_player(seat=0, tiles=(*_ONE_MAN[:3], *_KAN_SEAT_REST))
    seat_3 = create_player(seat=3, tiles=(_ONE_MAN[3], *_FILLER[3]))
    game_state = _kan_game(seat_0, seat_3=seat_3, current_player_seat=3, settings=settings)
    prompted, _events = process_discard_phase(game_state, _ONE_MAN[3])
    assert prompted.round_state.pending_call_prompt is not None

    kan = _call_kan(prompted, seat=0, tile_id=_ONE_MAN[3], kan_type=KanType.OPEN)
    assert kan.state.round_state.players[0].melds[0].type == FrozenMeld.KAN
    return game_state, kan.state


def _chi_by_seat_holding_quad_and_upgradable_pon() -> MahjongGameState:
    three_pin = tile_copies(0, pin="3")[0]
    one_two_pin = tuple(tile_copies(1, pin="12"))
    seat_0 = create_player(
        seat=0,
        tiles=(
            _ONE_MAN[3],
            *tile_copies(0, man="2222"),
            *one_two_pin,
            *tile_copies(1, sou="2"),
            *tile_copies(0, honors="77"),
        ),
        melds=(_one_man_pon_from_seat_3(),),
    )
    seat_3 = create_player(seat=3, tiles=(three_pin, *_FILLER[3]), discards=(Discard(tile_id=_ONE_MAN[2]),))
    game_state = _kan_game(seat_0, seat_3=seat_3, current_player_seat=3)
    assert get_possible_closed_kans(seat_0, game_state.round_state, settings=game_state.settings) != []
    assert get_possible_added_kans(seat_0, game_state.round_state, settings=game_state.settings) != []

    prompted, _events = process_discard_phase(game_state, three_pin)
    chi = handle_chi(prompted, seat=0, data=ChiActionData(tile_id=three_pin, sequence_tiles=one_two_pin))
    assert isinstance(chi, ActionResult)
    assert chi.state.round_state.is_after_meld_call
    return chi.state


# ---------------------------------------------------------------------------
# Minimum wall tiles for kan (configurable via settings.min_wall_for_kan)
# ---------------------------------------------------------------------------
class TestMinWallForKan:
    def test_closed_kan__when_min_wall_for_kan_setting_changes__should_require_that_many_wall_tiles(self):
        runtime = GameRuntime(game_id="game", state=_kan_game(_one_man_quad_after_draw()), ai=AIPlayerController({}))
        wall = runtime.state.round_state.wall
        round_state = _update_round_state(runtime, wall=wall.model_copy(update={"live_tiles": wall.live_tiles[:2]}))
        player = round_state.players[0]

        assert get_possible_closed_kans(player, round_state, settings=GameSettings()) == [tile_to_34(_ONE_MAN[0])]
        assert get_possible_closed_kans(player, round_state, settings=GameSettings(min_wall_for_kan=3)) == []

    def test_added_kan__when_min_wall_for_kan_setting_changes__should_require_that_many_wall_tiles(self):
        seat_0 = create_player(seat=0, tiles=(_ONE_MAN[3], *_KAN_SEAT_REST), melds=(_one_man_pon_from_seat_3(),))
        game_state = _kan_game(seat_0, seat_3=_seat_3_after_discarding(_ONE_MAN[2]))
        runtime = GameRuntime(game_id="game", state=game_state, ai=AIPlayerController({}))
        wall = runtime.state.round_state.wall
        round_state = _update_round_state(runtime, wall=wall.model_copy(update={"live_tiles": wall.live_tiles[:2]}))
        player = round_state.players[0]

        assert get_possible_added_kans(player, round_state, settings=GameSettings()) == [tile_to_34(_ONE_MAN[0])]
        assert get_possible_added_kans(player, round_state, settings=GameSettings(min_wall_for_kan=3)) == []


# ---------------------------------------------------------------------------
# Kan after pon/chi on same turn: not allowed (fundamental)
# ---------------------------------------------------------------------------
class TestKanAfterMeldCallBlocked:
    def test_kan__when_after_meld_call__should_offer_neither_closed_nor_added_kan(self):
        game_state = _chi_by_seat_holding_quad_and_upgradable_pon()
        round_state = game_state.round_state
        player = round_state.players[0]

        assert get_possible_closed_kans(player, round_state, settings=game_state.settings) == []
        assert get_possible_added_kans(player, round_state, settings=game_state.settings) == []

    def test_handle_kan__when_closed_kan_right_after_meld_call__should_raise(self):
        game_state = _chi_by_seat_holding_quad_and_upgradable_pon()
        two_man = tile_copies(0, man="2")[0]

        with pytest.raises(InvalidGameActionError, match="cannot declare kan after a meld call"):
            handle_kan(game_state, seat=0, data=KanActionData(tile_id=two_man, kan_type=KanType.CLOSED))


# ---------------------------------------------------------------------------
# Consecutive concealed quads: allowed, each reveals new dora (fundamental)
# ---------------------------------------------------------------------------
class TestConsecutiveClosedKans:
    def test_closed_kan__when_second_kan_follows_first__should_allow_it_and_reveal_new_dora(self):
        two_man = tile_copies(0, man="2222")
        seat_0 = create_player(seat=0, tiles=(*_ONE_MAN, *two_man, *tile_copies(1, pin="12345", sou="2")))
        game_state = _kan_game(seat_0)
        dora_before = len(game_state.round_state.wall.dora_indicators)

        first = _call_kan(game_state, seat=0, tile_id=_ONE_MAN[0], kan_type=KanType.CLOSED)
        first_round = first.state.round_state
        assert len(first_round.wall.dora_indicators) == dora_before + 1
        assert get_possible_closed_kans(first_round.players[0], first_round, settings=first.state.settings) == [
            tile_to_34(two_man[0])
        ]

        second = _call_kan(first.state, seat=0, tile_id=two_man[0], kan_type=KanType.CLOSED)
        assert [m.type for m in second.state.round_state.players[0].melds] == [FrozenMeld.KAN, FrozenMeld.KAN]
        assert len(second.state.round_state.wall.dora_indicators) == dora_before + 2


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
    @pytest.mark.parametrize(
        ("settings", "revealed", "pending"),
        [
            pytest.param(GameSettings(), 1, 0, id="immediate_by_default"),
            pytest.param(GameSettings(kandora_immediate_for_closed_kan=False), 0, 1, id="deferred_when_setting_off"),
            pytest.param(GameSettings(has_kandora=False), 0, 0, id="none_when_kandora_disabled"),
        ],
    )
    def test_kan_dora__when_closed_kan__should_follow_the_closed_kan_dora_settings(self, settings, revealed, pending):
        game_state = _kan_game(_one_man_quad_after_draw(), settings=settings)
        dora_before = len(game_state.round_state.wall.dora_indicators)

        kan = _call_kan(game_state, seat=0, tile_id=_ONE_MAN[0], kan_type=KanType.CLOSED)
        wall = kan.state.round_state.wall
        assert (len(wall.dora_indicators) - dora_before, wall.pending_dora_count) == (revealed, pending)

    @pytest.mark.parametrize(
        ("settings", "revealed", "pending"),
        [
            pytest.param(GameSettings(), 0, 1, id="deferred_by_default"),
            pytest.param(GameSettings(kandora_deferred_for_open_kan=False), 1, 0, id="immediate_when_setting_off"),
        ],
    )
    def test_kan_dora__when_open_kan__should_follow_the_open_kan_dora_setting(self, settings, revealed, pending):
        before_discard, after_kan = _open_kan_on_seat_3_discard(settings)
        dora_before = len(before_discard.round_state.wall.dora_indicators)

        wall = after_kan.round_state.wall
        assert (len(wall.dora_indicators) - dora_before, wall.pending_dora_count) == (revealed, pending)

    def test_kan_dora__when_added_kan_by_default__should_defer_dora(self):
        seat_0 = create_player(seat=0, tiles=(_ONE_MAN[3], *_KAN_SEAT_REST), melds=(_one_man_pon_from_seat_3(),))
        game_state = _kan_game(seat_0, seat_3=_seat_3_after_discarding(_ONE_MAN[2]))
        dora_before = len(game_state.round_state.wall.dora_indicators)

        kan = _call_kan(game_state, seat=0, tile_id=_ONE_MAN[3], kan_type=KanType.ADDED)
        wall = kan.state.round_state.wall
        assert kan.state.round_state.players[0].melds[0].type == FrozenMeld.SHOUMINKAN
        assert (len(wall.dora_indicators), wall.pending_dora_count) == (dora_before, 1)

    def test_kan_dora__when_open_kan_replacement_discard_is_ponned__should_reveal_dora_before_the_pon(self):
        nine_pin = tile_copies(0, pin="9999")
        east = tile_copies(0, honors="111")
        players = (
            create_player(
                seat=0, tiles=(nine_pin[3], *tile_copies(0, man="123456789"), *tile_copies(0, honors="2345"))
            ),
            create_player(seat=1, tiles=(*nine_pin[:3], east[0], *tile_copies(1, sou="123456789"))),
            create_player(seat=2, tiles=(*tile_copies(2, sou="123456789"), *tile_copies(1, honors="2345"))),
            create_player(seat=3, tiles=(*east[1:], *tile_copies(3, sou="123456789"), *tile_copies(2, honors="23"))),
        )
        game_state = create_dealt_game_state(players)
        kan_dora_indicator = game_state.round_state.wall.dead_wall.indicators[1].top

        kan_offer = _discard(game_state, seat=0, tile_id=nine_pin[3])
        kan = handle_kan(kan_offer.state, seat=1, data=KanActionData(tile_id=nine_pin[3], kan_type=KanType.OPEN))
        assert isinstance(kan, ActionResult)
        assert kan.state.round_state.wall.pending_dora_count == 1

        replacement_discard = _discard(kan.state, seat=1, tile_id=east[0])
        assert replacement_discard.state.round_state.wall.pending_dora_count == 1
        assert not [e for e in replacement_discard.events if isinstance(e, DoraRevealedEvent)]

        pon = handle_pon(replacement_discard.state, seat=3, data=PonActionData(tile_id=east[0]))
        assert isinstance(pon, ActionResult)
        assert [type(e) for e in pon.events if isinstance(e, (DoraRevealedEvent, MeldEvent))] == [
            DoraRevealedEvent,
            MeldEvent,
        ]
        assert [e.tile_id for e in pon.events if isinstance(e, DoraRevealedEvent)] == [kan_dora_indicator]
        assert pon.state.round_state.wall.pending_dora_count == 0
        assert pon.state.round_state.players[3].melds[-1].type == FrozenMeld.PON


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
        round_state = _kan_game(_one_man_quad_after_draw(), seat_1=_KOKUSHI_ON_ONE_MAN).round_state

        assert is_kokushi_chankan_possible(round_state, caller_seat=0, kan_tile=_ONE_MAN[0]) == [1]

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

    def test_closed_kan__when_kokushi_can_rob__should_prompt_chankan_and_complete_the_kan_once_declined(self):
        game_state = _kan_game(_one_man_quad_after_draw(), seat_1=_KOKUSHI_ON_ONE_MAN)

        kan = _call_kan(game_state, seat=0, tile_id=_ONE_MAN[0], kan_type=KanType.CLOSED)
        prompt = kan.state.round_state.pending_call_prompt
        assert prompt is not None
        assert (prompt.kind, prompt.callers) == (PromptKind.CHANKAN, (Caller(seat=1, can_ron=True),))
        assert [(e.target, e.call_type) for e in kan.events if isinstance(e, CallPromptEvent)] == [
            (SeatTarget(seat=1), CallType.CHANKAN),
        ]
        assert kan.state.round_state.players[0].melds == ()

        declined = handle_pass(kan.state, seat=1)
        assert isinstance(declined, ActionResult)
        assert [(e.meld_type, e.caller_seat) for e in declined.events if isinstance(e, MeldEvent)] == [
            (MeldViewType.CLOSED_KAN, 0),
        ]
        assert [m.type for m in declined.state.round_state.players[0].melds] == [FrozenMeld.KAN]


# ---------------------------------------------------------------------------
# Chankan preservation: ippatsu not cleared, dora not flipped (fundamental)
# ---------------------------------------------------------------------------
_FIRST_GO_AROUND = tuple(tile_copies(0, honors="123"))
_AFTER_PON = tuple(tile_copies(1, honors="1234"))


class TestChankanPreservation:
    def test_chankan_prompt__when_added_kan_declared__should_preserve_ippatsu_and_not_reveal_dora(self):
        three_pin = tile_copies(0, pin="3333")
        pon_from_seat_3 = FrozenMeld(
            meld_type=FrozenMeld.PON, tiles=three_pin[:3], opened=True, called_tile=three_pin[2], who=0, from_who=3
        )
        seat_0 = create_player(
            seat=0,
            tiles=(three_pin[3], *tile_copies(0, pin="6789", sou="12345", honors="7")),
            melds=(pon_from_seat_3,),
            discards=(Discard(tile_id=_FIRST_GO_AROUND[0]), Discard(tile_id=_AFTER_PON[0])),
        )
        riichi_ippatsu_on_three_pin = create_player(
            seat=1,
            tiles=tile_copies(0, man="123456789", pin="1255"),
            discards=(Discard(tile_id=_FIRST_GO_AROUND[1]), Discard(tile_id=_AFTER_PON[1], is_riichi_discard=True)),
            is_riichi=True,
            is_ippatsu=True,
        )
        seat_2 = create_player(
            seat=2,
            tiles=_FILLER[2],
            discards=(Discard(tile_id=_FIRST_GO_AROUND[2]), Discard(tile_id=_AFTER_PON[2])),
        )
        seat_3 = create_player(
            seat=3,
            tiles=_FILLER[3],
            discards=(Discard(tile_id=three_pin[2]), Discard(tile_id=_AFTER_PON[3])),
        )
        game_state = create_dealt_game_state(
            (seat_0, riichi_ippatsu_on_three_pin, seat_2, seat_3),
            all_discards=(*_FIRST_GO_AROUND, three_pin[2], *_AFTER_PON),
        )
        dora_before = len(game_state.round_state.wall.dora_indicators)

        kan = _call_kan(game_state, seat=0, tile_id=three_pin[3], kan_type=KanType.ADDED)
        round_state = kan.state.round_state
        assert round_state.pending_call_prompt is not None
        assert round_state.pending_call_prompt.kind == PromptKind.CHANKAN
        assert round_state.players[1].is_ippatsu is True
        assert (len(round_state.wall.dora_indicators), round_state.wall.pending_dora_count) == (dora_before, 0)


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
    return GameRuntime(game_id="game1", state=create_dealt_game_state(players), ai=AIPlayerController({}))


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
