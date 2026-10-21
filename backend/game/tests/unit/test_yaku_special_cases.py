from __future__ import annotations

from mahjong.tile import TilesConverter

from game.logic.meld_wrapper import FrozenMeld
from game.logic.round import check_nagashi_mangan, process_exhaustive_draw
from game.logic.scoring import (
    ScoringContext,
    apply_nagashi_mangan_score,
    calculate_hand_value,
)
from game.logic.settings import GameSettings
from game.logic.state import Discard
from game.logic.win import is_chiihou
from game.tests.conftest import create_game_state, create_player, create_round_state

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
            players_with_open_hands=(),
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
            players_with_open_hands=(),
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
            players_with_open_hands=(),
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
            players_with_open_hands=(),
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
            players_with_open_hands=(),
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
            players_with_open_hands=(),
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


# --- Haitei Raoyue (Under the Sea) ---


class TestHaiteiRaoyue:
    def test_haitei__when_tsumo_on_last_tile__should_award_yaku(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
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
            wall=[],
        )
        ctx = ScoringContext(
            player=round_state.players[0],
            round_state=round_state,
            settings=GameSettings(),
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, tiles[-1])
        assert result.error is None
        assert any(y.yaku_id == 6 for y in result.yaku)

    def test_haitei__when_wall_has_tiles__should_not_award_yaku(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
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
            wall=list(range(10)),
        )
        ctx = ScoringContext(
            player=round_state.players[0],
            round_state=round_state,
            settings=GameSettings(),
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, tiles[-1])
        assert result.error is None
        assert not any(y.yaku_id == 6 for y in result.yaku)

    def test_haitei__when_ron__should_award_houtei_instead(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = create_player(
            seat=0,
            tiles=tiles,
            is_riichi=True,
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
            wall=[],
        )
        ctx = ScoringContext(
            player=round_state.players[0],
            round_state=round_state,
            settings=GameSettings(),
            is_tsumo=False,
        )
        result = calculate_hand_value(ctx, tiles[-1])
        assert result.error is None
        # haitei (id=6) should NOT be present; houtei (id=7) should be
        assert not any(y.yaku_id == 6 for y in result.yaku)
        assert any(y.yaku_id == 7 for y in result.yaku)


# --- Houtei Raoyui (Under the River) ---


class TestHouteiRaoyui:
    def test_houtei__when_ron_on_last_discard__should_award_yaku(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = create_player(
            seat=0,
            tiles=tiles,
            is_riichi=True,
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
            wall=[],
        )
        ctx = ScoringContext(
            player=round_state.players[0],
            round_state=round_state,
            settings=GameSettings(),
            is_tsumo=False,
        )
        result = calculate_hand_value(ctx, tiles[-1])
        assert result.error is None
        assert any(y.yaku_id == 7 for y in result.yaku)

    def test_houtei__when_tsumo__should_award_haitei_instead(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
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
            wall=[],
        )
        ctx = ScoringContext(
            player=round_state.players[0],
            round_state=round_state,
            settings=GameSettings(),
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, tiles[-1])
        assert result.error is None
        # houtei (id=7) should NOT be present; haitei (id=6) should be
        assert not any(y.yaku_id == 7 for y in result.yaku)
        assert any(y.yaku_id == 6 for y in result.yaku)


# --- Rinshan Kaihou ---


class TestRinshanKaihou:
    def test_rinshan__when_rinshan_flag_set__should_award_yaku(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = create_player(
            seat=0,
            tiles=tiles,
            is_rinshan=True,
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
            wall=list(range(10)),
        )
        ctx = ScoringContext(
            player=round_state.players[0],
            round_state=round_state,
            settings=GameSettings(),
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, tiles[-1])
        assert result.error is None
        assert any(y.yaku_id == 5 for y in result.yaku)

    def test_rinshan__when_rinshan_flag_clear__should_not_award_yaku(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = create_player(
            seat=0,
            tiles=tiles,
            is_rinshan=False,
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
            wall=list(range(10)),
        )
        ctx = ScoringContext(
            player=round_state.players[0],
            round_state=round_state,
            settings=GameSettings(),
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, tiles[-1])
        assert result.error is None
        assert not any(y.yaku_id == 5 for y in result.yaku)


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
            players_with_open_hands=(0,),
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
            players_with_open_hands=(1,),
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
            players_with_open_hands=(0,),
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

        _new_rs, _new_gs, result = process_exhaustive_draw(game_state)
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

        _rs, _gs, result = apply_nagashi_mangan_score(
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

        _rs, _gs, result = apply_nagashi_mangan_score(
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
