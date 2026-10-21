import pytest
from mahjong.tile import TilesConverter

from game.logic.abortive import check_four_kans
from game.logic.action_handlers import _handle_self_kan
from game.logic.call_resolution import resolve_call_prompt
from game.logic.enums import CallType, KanType, MeldViewType, RoundPhase
from game.logic.events import CallPromptEvent, MeldEvent, RoundEndEvent
from game.logic.exceptions import InvalidGameActionError
from game.logic.meld_wrapper import FrozenMeld
from game.logic.melds import (
    call_added_kan,
    call_closed_kan,
    call_open_kan,
    get_possible_added_kans,
    get_possible_closed_kans,
)
from game.logic.settings import GameSettings
from game.logic.state import Discard, PendingCallPrompt
from game.logic.tiles import tile_to_34
from game.logic.turn import _process_added_kan_call, _process_closed_kan_call
from game.logic.types import KanActionData
from game.logic.win import (
    is_chankan_possible,
    is_kokushi_chankan_possible,
    is_kokushi_tenpai,
)
from game.tests.conftest import create_game_state, create_player, create_round_state

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
    players_with_open_hands=None,
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
        players_with_open_hands=players_with_open_hands or (),
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
            players_with_open_hands=(0,),
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


# ---------------------------------------------------------------------------
# Four quads by same player: play continues (fundamental)
# Four quads by different players (2+): abortive draw (configurable)
# ---------------------------------------------------------------------------
class TestFourKansAbort:
    def test_four_kans_abort__when_one_player_has_all_four_kans__should_not_abort(self):
        kan_meld = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=(0, 1, 2, 3), opened=False, who=0)
        round_state = _make_round_state(
            player0_tiles=TilesConverter.string_to_136_array(pin="123456789"),
            player0_melds=(kan_meld, kan_meld, kan_meld, kan_meld),
        )

        settings = GameSettings()
        assert check_four_kans(round_state, settings) is False

    def test_four_kans_abort__when_two_players_share_four_kans__should_abort(self):
        kan_meld_0 = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=(0, 1, 2, 3), opened=True, who=0, from_who=1)
        kan_meld_1 = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=(4, 5, 6, 7), opened=True, who=1, from_who=0)
        round_state = _make_round_state(
            player0_tiles=TilesConverter.string_to_136_array(pin="123456789"),
            player0_melds=(kan_meld_0, kan_meld_0),
            player1_tiles=TilesConverter.string_to_136_array(man="123", pin="123", sou="123456"),
            player1_melds=(kan_meld_1, kan_meld_1),
        )

        settings = GameSettings()
        assert check_four_kans(round_state, settings) is True

    def test_four_kans_abort__when_min_players_setting_is_3__should_not_abort_with_two_players(self):
        kan_meld_0 = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=(0, 1, 2, 3), opened=True, who=0, from_who=1)
        kan_meld_1 = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=(4, 5, 6, 7), opened=True, who=1, from_who=0)
        round_state = _make_round_state(
            player0_tiles=TilesConverter.string_to_136_array(pin="123456789"),
            player0_melds=(kan_meld_0, kan_meld_0),
            player1_tiles=TilesConverter.string_to_136_array(man="123", pin="123", sou="123456"),
            player1_melds=(kan_meld_1, kan_meld_1),
        )
        # still triggers with default settings
        settings = GameSettings()
        assert check_four_kans(round_state, settings) is True

        # custom min_players_for_kan_abort=3 means 2 players is not enough
        settings_3 = GameSettings(min_players_for_kan_abort=3)
        assert check_four_kans(round_state, settings_3) is False

    def test_four_kans_abort__when_shouminkans_make_four_kans__should_abort(self):
        kan_meld = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=(0, 1, 2, 3), opened=True, who=0, from_who=1)
        shouminkan_meld = FrozenMeld(
            meld_type=FrozenMeld.SHOUMINKAN,
            tiles=(4, 5, 6, 7),
            opened=True,
            who=1,
            from_who=0,
        )
        round_state = _make_round_state(
            player0_tiles=TilesConverter.string_to_136_array(pin="123456789"),
            player0_melds=(kan_meld, kan_meld),
            player1_tiles=TilesConverter.string_to_136_array(man="123", pin="123", sou="123456"),
            player1_melds=(shouminkan_meld, shouminkan_meld),
        )

        settings = GameSettings()
        assert check_four_kans(round_state, settings) is True


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
        # player 1 is tenpai on 1m but not for kokushi (e.g., 23m waiting on 1-4m)
        regular_tenpai = TilesConverter.string_to_136_array(man="2345678", pin="12355", sou="9")
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="6789", sou="12345")
        player0_tiles = (*man_1m, *pin_tiles)

        round_state = _make_round_state(
            player0_tiles,
            player1_tiles=regular_tenpai,
        )

        chankan_seats = is_kokushi_chankan_possible(round_state, caller_seat=0, kan_tile=man_1m[0])
        assert 1 not in chankan_seats
        assert chankan_seats == []

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

        new_rs, _new_gs, events = _process_closed_kan_call(round_state, game_state, caller_seat=0, tile_id=man_1m[0])
        # should create a chankan prompt, not execute the kan
        chankan_events = [e for e in events if isinstance(e, CallPromptEvent) and e.call_type == CallType.CHANKAN]
        assert len(chankan_events) == 1
        assert new_rs.pending_call_prompt is not None
        assert new_rs.pending_call_prompt.call_type == CallType.CHANKAN

    def test_process_closed_kan_call__when_no_kokushi_can_rob__should_execute_kan(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player0_tiles = (*man_1m, *pin_tiles)

        round_state = _make_round_state(player0_tiles)
        game_state = create_game_state(round_state)

        new_rs, _new_gs, events = _process_closed_kan_call(round_state, game_state, caller_seat=0, tile_id=man_1m[0])
        # should execute the kan (MeldEvent, not CallPromptEvent)
        meld_events = [e for e in events if isinstance(e, MeldEvent) and e.meld_type == MeldViewType.CLOSED_KAN]
        assert len(meld_events) == 1
        assert new_rs.pending_call_prompt is None


# ---------------------------------------------------------------------------
# Chankan on shouminkan (already verified, sanity check)
# ---------------------------------------------------------------------------
class TestChankanOnShouminkan:
    def test_chankan__when_tenpai_player_waits_on_added_kan_tile__should_allow_robbing(self):
        # player 1 is tenpai waiting on 3p
        tiles_p1 = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        pin_3 = TilesConverter.string_to_136_array(pin="3")[0]

        players = [
            create_player(seat=0, tiles=TilesConverter.string_to_136_array(pin="123456789", man="1234")),
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

        chankan_seats = is_chankan_possible(round_state, caller_seat=0, kan_tile=pin_3)
        assert 1 in chankan_seats


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
            players_with_open_hands=(0,),
        )
        game_state = create_game_state(round_state)

        new_rs, _new_gs, events = _process_added_kan_call(round_state, game_state, caller_seat=0, tile_id=pin_3[3])
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
            players_with_open_hands=(0,),
        )
        game_state = create_game_state(round_state)

        initial_dora_count = len(round_state.wall.dora_indicators)
        new_rs, _new_gs, _events = _process_added_kan_call(round_state, game_state, caller_seat=0, tile_id=pin_3[3])
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
            _handle_self_kan(round_state, game_state, seat=0, data=data)


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
            call_type=CallType.CHANKAN,
            tile_id=man_1m[0],
            from_seat=0,
            pending_seats=frozenset(),
            callers=(1,),
            responses=(),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = resolve_call_prompt(round_state, game_state)
        assert result.new_round_state is not None
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.CLOSED_KAN

    def test_resolve_chankan_decline__when_closed_kan_is_fourth_kan__should_abort_round(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player0_tiles = (*man_1m, *pin_tiles)

        # player 0 already has 2 kans, player 1 has 1 kan → 3 total, 4th triggers abort
        existing_kans_p0 = tuple(
            FrozenMeld(meld_type=FrozenMeld.KAN, tiles=(i * 4, i * 4 + 1, i * 4 + 2, i * 4 + 3), opened=False, who=0)
            for i in range(2)
        )
        existing_kan_p1 = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=(12, 13, 14, 15),
            opened=True,
            who=1,
            from_who=2,
        )

        round_state = _make_round_state(
            player0_tiles,
            player0_melds=existing_kans_p0,
            player1_melds=(existing_kan_p1,),
        )
        round_state = round_state.model_copy(update={"phase": RoundPhase.PLAYING})
        game_state = create_game_state(round_state)

        prompt = PendingCallPrompt(
            call_type=CallType.CHANKAN,
            tile_id=man_1m[0],
            from_seat=0,
            pending_seats=frozenset(),
            callers=(1,),
            responses=(),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = resolve_call_prompt(round_state, game_state)
        # should trigger four kans abort
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert result.new_round_state.phase == RoundPhase.FINISHED


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
