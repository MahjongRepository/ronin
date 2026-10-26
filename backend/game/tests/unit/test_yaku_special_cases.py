from __future__ import annotations

from mahjong.hand_calculating.yaku_list import AkaDora, Haitei, Houtei, Ittsu, Rinshan, Tsumo
from mahjong.tile import TilesConverter

from game.logic.action_handlers import handle_discard, handle_kan, handle_ron, handle_tsumo
from game.logic.action_result import ActionResult, Refusal
from game.logic.ai_player_controller import AIPlayerController
from game.logic.enums import KanType
from game.logic.events import RoundEndEvent
from game.logic.meld_wrapper import FrozenMeld
from game.logic.round import check_nagashi_mangan, process_exhaustive_draw
from game.logic.runtime import GameRuntime
from game.logic.scoring import (
    ScoringContext,
    apply_nagashi_mangan_score,
    calculate_hand_value,
)
from game.logic.settings import GameSettings
from game.logic.state import Caller, Discard, MahjongGameState, MahjongPlayer
from game.logic.tiles import tile_to_34
from game.logic.turn import process_draw_phase
from game.logic.types import DiscardActionData, KanActionData, RonResult, TsumoResult
from game.logic.win import is_chiihou
from game.tests.conftest import create_dealt_game_state, create_game_state, create_player, create_round_state
from game.tests.helpers.hands import tile_copies
from game.tests.unit.helpers import _update_round_state

# --- Tenhou (Blessing of Heaven) ---


class TestTenhouScoring:
    def test_tenhou__when_dealer_tsumo_on_first_draw__should_score_yakuman(self):
        # 1-9m 1-5p pinfu hand for the dealer
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = create_player(seat=0, tiles=tiles)
        players = (
            player,
            *(create_player(seat=i) for i in range(1, 4)),
        )
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            all_discards=(),
            wall=list(range(70)),
        )

        ctx = ScoringContext(
            player=round_state.players[0],
            round_state=round_state,
            settings=GameSettings(),
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, tiles[-1])
        assert result.error is None
        # yaku_id 115 = tenhou
        assert any(y.yaku_id == 115 for y in result.yaku)
        assert result.han >= 13

    def test_tenhou__when_non_dealer__should_not_award_yaku(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = create_player(seat=1, tiles=tiles)
        players = (
            create_player(seat=0),
            player,
            *(create_player(seat=i) for i in range(2, 4)),
        )
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=1,
            all_discards=(),
            wall=list(range(70)),
        )

        ctx = ScoringContext(
            player=round_state.players[1],
            round_state=round_state,
            settings=GameSettings(),
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, tiles[-1])
        assert result.error is None
        # tenhou should not be in yaku list
        assert not any(y.yaku_id == 115 for y in result.yaku)


# --- Chiihou (Blessing of Earth) ---


class TestChiihouBugFix:
    def test_chiihou__when_dealer_discard_in_all_discards__should_still_detect(self):
        player = create_player(seat=1, tiles=[])
        players = (
            create_player(seat=0, discards=(Discard(tile_id=0),)),
            player,
            *(create_player(seat=i) for i in range(2, 4)),
        )
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=1,
            all_discards=(0,),
        )
        # player has no discards (first draw), even though all_discards is non-empty
        assert is_chiihou(round_state.players[1], round_state) is True

    def test_chiihou__when_player_has_discarded__should_not_detect(self):
        player = create_player(seat=1, discards=(Discard(tile_id=5),))
        players = (
            create_player(seat=0),
            player,
            *(create_player(seat=i) for i in range(2, 4)),
        )
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=1,
        )
        assert is_chiihou(round_state.players[1], round_state) is False


class TestChiihouScoring:
    def test_chiihou__when_non_dealer_tsumo_on_first_draw__should_score_yakuman(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = create_player(seat=1, tiles=tiles)
        players = (
            create_player(seat=0, discards=(Discard(tile_id=0),)),
            player,
            *(create_player(seat=i) for i in range(2, 4)),
        )
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=1,
            all_discards=(0,),
            wall=list(range(70)),
        )

        ctx = ScoringContext(
            player=round_state.players[1],
            round_state=round_state,
            settings=GameSettings(),
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, tiles[-1])
        assert result.error is None
        # yaku_id 116 = chiihou
        assert any(y.yaku_id == 116 for y in result.yaku)
        assert result.han >= 13

    def test_chiihou__when_dealer__should_not_award_yaku(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = create_player(seat=0, tiles=tiles)
        players = (
            player,
            *(create_player(seat=i) for i in range(1, 4)),
        )
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            all_discards=(),
            wall=list(range(70)),
        )

        ctx = ScoringContext(
            player=round_state.players[0],
            round_state=round_state,
            settings=GameSettings(),
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, tiles[-1])
        assert result.error is None
        # chiihou should not appear (tenhou would instead)
        assert not any(y.yaku_id == 116 for y in result.yaku)


_ITTSU_EAST_TANKI = tuple(tile_copies(0, man="123456789", pin="444", honors="1"))
_LAST_EAST = tile_copies(1, honors="1")[0]


def _before_last_draw(players: tuple[MahjongPlayer, ...], *, drawing_seat: int) -> MahjongGameState:
    runtime = GameRuntime(
        game_id="game",
        state=create_dealt_game_state(players, draws=(_LAST_EAST,), current_player_seat=drawing_seat),
        ai=AIPlayerController({}),
    )
    wall = runtime.state.round_state.wall
    _update_round_state(runtime, wall=wall.model_copy(update={"live_tiles": (_LAST_EAST,)}))
    drawn_game, _events = process_draw_phase(runtime.state)
    assert drawn_game.round_state.players[drawing_seat].tiles[-1] == _LAST_EAST
    assert drawn_game.round_state.wall.live_tiles == ()
    return drawn_game


def _yaku_ids(result: ActionResult | Refusal) -> list[int]:
    assert isinstance(result, ActionResult)
    round_end = result.events[-1]
    assert isinstance(round_end, RoundEndEvent)
    assert isinstance(round_end.result, (TsumoResult, RonResult))
    return sorted(y.yaku_id for y in round_end.result.hand_result.yaku)


class TestHaiteiAndHoutei:
    def test_haitei__when_tsumo_on_last_tile__should_award_haitei_not_houtei(self):
        players = (
            create_player(seat=0, tiles=tile_copies(1, sou="123456789", honors="2345")),
            create_player(seat=1, tiles=_ITTSU_EAST_TANKI),
            create_player(seat=2, tiles=tile_copies(2, sou="123456789", honors="2345")),
            create_player(seat=3, tiles=tile_copies(3, sou="123456789", honors="2345")),
        )
        game_state = _before_last_draw(players, drawing_seat=1)

        assert _yaku_ids(handle_tsumo(game_state, seat=1)) == sorted(
            (Tsumo.yaku_id, Haitei.yaku_id, Ittsu.yaku_id, AkaDora.yaku_id)
        )

    def test_houtei__when_ron_on_last_discard__should_award_houtei_not_haitei(self):
        players = (
            create_player(seat=0, tiles=(*tile_copies(1, sou="123456789", honors="234"), *tile_copies(2, honors="1"))),
            create_player(seat=1, tiles=(*tile_copies(2, sou="123456789", honors="234"), *tile_copies(3, pin="9"))),
            create_player(seat=2, tiles=_ITTSU_EAST_TANKI),
            create_player(seat=3, tiles=(*tile_copies(3, sou="123456789", honors="234"), *tile_copies(3, honors="1"))),
        )
        game_state = _before_last_draw(players, drawing_seat=1)

        last_discard = handle_discard(game_state, seat=1, data=DiscardActionData(tile_id=_LAST_EAST))
        assert isinstance(last_discard, ActionResult)
        prompt = last_discard.state.round_state.pending_call_prompt
        assert prompt is not None
        assert prompt.callers == (Caller(seat=2, can_ron=True),)

        assert _yaku_ids(handle_ron(last_discard.state, seat=2)) == sorted(
            (Houtei.yaku_id, Ittsu.yaku_id, AkaDora.yaku_id)
        )


# --- Rinshan Kaihou ---


class TestRinshanKaihou:
    def test_rinshan__when_closed_kan_replacement_tile_completes_hand__should_award_yaku(self):
        one_man_quad = tuple(tile_copies(0, man="1111"))
        north_tanki_with_ittsu = (*one_man_quad, *tile_copies(0, pin="123456789", honors="4"))
        players = (
            create_player(
                seat=0, tiles=north_tanki_with_ittsu, discards=(Discard(tile_id=tile_copies(0, sou="9")[0]),)
            ),
            *(
                create_player(
                    seat=seat,
                    tiles=tile_copies(seat, pin="123456789", sou="1234"),
                    discards=(Discard(tile_id=tile_copies(seat, sou="9")[0]),),
                )
                for seat in range(1, 4)
            ),
        )
        game_state = create_dealt_game_state(players)
        rinshan_tile = game_state.round_state.wall.dead_wall.rinshan[0]
        assert tile_to_34(rinshan_tile) == tile_to_34(north_tanki_with_ittsu[-1])

        kan = handle_kan(game_state, seat=0, data=KanActionData(tile_id=one_man_quad[0], kan_type=KanType.CLOSED))
        assert isinstance(kan, ActionResult)
        assert kan.state.round_state.players[0].tiles[-1] == rinshan_tile

        tsumo = handle_tsumo(kan.state, seat=0)
        assert isinstance(tsumo, ActionResult)
        round_end = tsumo.events[-1]
        assert isinstance(round_end, RoundEndEvent)
        assert isinstance(round_end.result, TsumoResult)
        assert sorted(y.yaku_id for y in round_end.result.hand_result.yaku) == sorted(
            (Tsumo.yaku_id, Rinshan.yaku_id, Ittsu.yaku_id, AkaDora.yaku_id)
        )


# --- Ryuuiisou (All Green) ---


class TestRyuuiisou:
    def test_ryuuiisou__when_hand_has_hatsu__should_score_yakuman(self):
        # 222s 333s 444s 666z + 66s pair = 14 tiles, all green
        tiles = TilesConverter.string_to_136_array(sou="22233344466", honors="666")
        player = create_player(
            seat=0,
            tiles=tiles,
            discards=(Discard(tile_id=0),),
        )
        players = (
            player,
            *(create_player(seat=i, discards=(Discard(tile_id=i),)) for i in range(1, 4)),
        )
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            all_discards=(0, 1, 2, 3),
            wall=list(range(70)),
        )

        ctx = ScoringContext(
            player=round_state.players[0],
            round_state=round_state,
            settings=GameSettings(),
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, tiles[-1])
        assert result.error is None
        assert any(y.yaku_id == 105 for y in result.yaku)
        assert result.han >= 13

    def test_ryuuiisou__when_hand_lacks_hatsu__should_score_yakuman(self):
        # 222s 333s 444s 666s + 88s pair = 14 tiles, all green, no hatsu
        tiles = TilesConverter.string_to_136_array(sou="22233344466688")
        player = create_player(
            seat=0,
            tiles=tiles,
            discards=(Discard(tile_id=0),),
        )
        players = (
            player,
            *(create_player(seat=i, discards=(Discard(tile_id=i),)) for i in range(1, 4)),
        )
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            all_discards=(0, 1, 2, 3),
            wall=list(range(70)),
        )

        ctx = ScoringContext(
            player=round_state.players[0],
            round_state=round_state,
            settings=GameSettings(),
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, tiles[-1])
        assert result.error is None
        # ryuuiisou without hatsu
        assert any(y.yaku_id == 105 for y in result.yaku)
        assert result.han >= 13

    def test_ryuuiisou__when_hand_is_open__should_score_yakuman(self):
        # open pon of hatsu (666z) + closed 222s 333s 444s + 88s pair = 14 tiles
        hatsu_tiles = TilesConverter.string_to_136_array(honors="666")
        closed_tiles = TilesConverter.string_to_136_array(sou="22233344488")
        all_tiles = tuple(closed_tiles) + tuple(hatsu_tiles)
        # win tile is the second 8-sou (completing the pair), from closed portion
        win_tile = closed_tiles[-1]

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(hatsu_tiles),
            opened=True,
            called_tile=hatsu_tiles[0],
            who=0,
            from_who=1,
        )
        player = create_player(
            seat=0,
            tiles=all_tiles,
            melds=(pon,),
            discards=(Discard(tile_id=0),),
        )
        players = (
            player,
            *(create_player(seat=i, discards=(Discard(tile_id=i),)) for i in range(1, 4)),
        )
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            all_discards=(0, 1, 2, 3),
            wall=list(range(70)),
        )

        ctx = ScoringContext(
            player=round_state.players[0],
            round_state=round_state,
            settings=GameSettings(),
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        assert any(y.yaku_id == 105 for y in result.yaku)


# --- Double Riichi ---


class TestDoubleRiichiScoring:
    def test_double_riichi__when_declared_on_first_turn__should_score_2_han(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = create_player(
            seat=0,
            tiles=tiles,
            is_riichi=True,
            is_daburi=True,
            discards=(Discard(tile_id=0, is_riichi_discard=True),),
        )
        players = (
            player,
            *(create_player(seat=i, discards=(Discard(tile_id=i),)) for i in range(1, 4)),
        )
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            all_discards=(0, 1, 2, 3),
            wall=list(range(70)),
        )

        ctx = ScoringContext(
            player=round_state.players[0],
            round_state=round_state,
            settings=GameSettings(),
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, tiles[-1])
        assert result.error is None
        # yaku_id 8 = daburu riichi (double riichi)
        assert any(y.yaku_id == 8 for y in result.yaku)
        # double riichi gives 2 han
        daburi_yaku = next(y for y in result.yaku if y.yaku_id == 8)
        assert daburi_yaku.han == 2

    def test_double_riichi__when_regular_riichi__should_not_score_double(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = create_player(
            seat=0,
            tiles=tiles,
            is_riichi=True,
            is_daburi=False,
            discards=(
                Discard(tile_id=0),
                Discard(tile_id=4, is_riichi_discard=True),
            ),
        )
        players = (
            player,
            *(create_player(seat=i, discards=(Discard(tile_id=i),)) for i in range(1, 4)),
        )
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            all_discards=(0, 1, 2, 3, 4),
            wall=list(range(70)),
        )

        ctx = ScoringContext(
            player=round_state.players[0],
            round_state=round_state,
            settings=GameSettings(),
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, tiles[-1])
        assert result.error is None
        # regular riichi (id=1), NOT double riichi (id=8)
        assert any(y.yaku_id == 1 for y in result.yaku)
        assert not any(y.yaku_id == 8 for y in result.yaku)


# --- Nagashi Mangan ---


class TestNagashiManganDetection:
    def test_nagashi_mangan__when_all_discards_terminal_or_honor__should_qualify(self):
        # terminals: 1m(0), 9m(32), 1p(36), 9p(68), honors: E(108)
        discards = (
            Discard(tile_id=0),  # 1m
            Discard(tile_id=32),  # 9m
            Discard(tile_id=36),  # 1p
            Discard(tile_id=68),  # 9p
            Discard(tile_id=108),  # East
        )
        player = create_player(seat=1, discards=discards)
        players = (
            create_player(seat=0, discards=(Discard(tile_id=4),)),
            player,
            create_player(seat=2),
            create_player(seat=3),
        )
        round_state = create_round_state(players=players)

        qualifying = check_nagashi_mangan(round_state)
        assert 1 in qualifying

    def test_nagashi_mangan__when_non_terminal_discard__should_not_qualify(self):
        discards = (
            Discard(tile_id=0),  # 1m (terminal)
            Discard(tile_id=4),  # 2m (NOT terminal)
        )
        player = create_player(seat=0, discards=discards)
        players = (
            player,
            *(create_player(seat=i) for i in range(1, 4)),
        )
        round_state = create_round_state(players=players)

        qualifying = check_nagashi_mangan(round_state)
        assert 0 not in qualifying

    def test_nagashi_mangan__when_discard_was_claimed__should_not_qualify(self):
        discards = (
            Discard(tile_id=0),  # 1m
            Discard(tile_id=108),  # East
        )
        # opponent has a pon called from seat 0
        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=(108, 109, 110),
            opened=True,
            called_tile=108,
            who=1,
            from_who=0,
        )
        player = create_player(seat=0, discards=discards)
        opponent = create_player(seat=1, melds=(pon,))
        players = (
            player,
            opponent,
            create_player(seat=2),
            create_player(seat=3),
        )
        round_state = create_round_state(
            players=players,
        )

        qualifying = check_nagashi_mangan(round_state)
        assert 0 not in qualifying

    def test_nagashi_mangan__when_player_called_others_tiles__should_still_qualify(self):
        # player 0 has all terminal discards, and called a pon from player 1
        discards = (
            Discard(tile_id=0),  # 1m
            Discard(tile_id=32),  # 9m
        )
        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=(108, 109, 110),
            opened=True,
            called_tile=108,
            who=0,
            from_who=1,
        )
        player = create_player(seat=0, discards=discards, melds=(pon,))
        players = (
            player,
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        )
        round_state = create_round_state(
            players=players,
        )

        qualifying = check_nagashi_mangan(round_state)
        # player 0 called from player 1, but their OWN discards were not claimed
        assert 0 in qualifying

    def test_nagashi_mangan__when_disabled_by_setting__should_produce_regular_draw_result(self):
        discards = (
            Discard(tile_id=0),
            Discard(tile_id=32),
        )
        player = create_player(seat=0, discards=discards)
        players = (
            player,
            *(create_player(seat=i, discards=(Discard(tile_id=i * 4),)) for i in range(1, 4)),
        )
        round_state = create_round_state(players=players, wall=[])
        settings = GameSettings(has_nagashi_mangan=False)
        game_state = create_game_state(round_state=round_state, settings=settings)

        _new_gs, result = process_exhaustive_draw(game_state)
        # should be a regular exhaustive draw, not nagashi mangan
        assert not hasattr(result, "qualifying_seats")


class TestNagashiManganPayments:
    def test_nagashi_mangan_payment__when_custom_amounts__should_use_them(self):
        settings = GameSettings(
            nagashi_mangan_dealer_payment=6000,
            nagashi_mangan_non_dealer_payment=3000,
        )
        players = tuple(create_player(seat=i) for i in range(4))
        round_state = create_round_state(players=players, dealer_seat=0)
        game_state = create_game_state(round_state=round_state, settings=settings)

        _gs, result = apply_nagashi_mangan_score(
            game_state,
            qualifying_seats=[1],
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
        )
        # seat 1 (non-dealer): 6000 from dealer + 3000 from each non-dealer = 12000
        assert result.score_changes[1] == 12000
        assert result.score_changes[0] == -6000  # dealer pays 6000
        assert result.score_changes[2] == -3000  # non-dealer pays 3000
        assert result.score_changes[3] == -3000  # non-dealer pays 3000

    def test_nagashi_mangan_payment__when_honba__should_not_add_bonus(self):
        players = tuple(create_player(seat=i) for i in range(4))
        round_state = create_round_state(players=players, dealer_seat=0)
        game_state = create_game_state(
            round_state=round_state,
            honba_sticks=5,
        )

        _gs, result = apply_nagashi_mangan_score(
            game_state,
            qualifying_seats=[1],
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
        )
        # standard non-dealer nagashi: 4000 + 2000 + 2000 = 8000 total
        # no honba bonus despite 5 honba sticks
        assert result.score_changes[1] == 8000
        assert result.score_changes[0] == -4000
        assert result.score_changes[2] == -2000
        assert result.score_changes[3] == -2000
