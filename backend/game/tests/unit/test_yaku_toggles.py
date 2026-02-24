"""
Verify that kuitan (open tanyao), ippatsu, atozuke, and renhou settings
are properly configurable and correctly wired into scoring/win logic.
"""

from mahjong.tile import TilesConverter

from game.logic.meld_wrapper import FrozenMeld
from game.logic.scoring import ScoringContext, calculate_hand_value
from game.logic.settings import GameSettings, RenhouValue, build_optional_rules
from game.logic.state import Discard, MahjongPlayer
from game.logic.state_utils import update_player
from game.logic.win import can_call_ron, can_declare_tsumo, is_renhou
from game.tests.conftest import create_player, create_round_state


def _make_round_state(*, wall=None, dead_wall=None, dora_indicators=None):
    """Create a round state with a wall for scoring tests."""
    return create_round_state(
        wall=tuple(range(70)) if wall is None else wall,
        dead_wall=tuple(range(14)) if dead_wall is None else dead_wall,
        dora_indicators=TilesConverter.string_to_136_array(man="9") if dora_indicators is None else dora_indicators,
    )


class TestKuitanToggle:
    """Verify has_kuitan setting controls open tanyao acceptance."""

    def test_kuitan_enabled_allows_open_tanyao_tsumo(self):
        """Open tanyao (all simples) hand is valid when kuitan is enabled."""
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        pon_tiles = TilesConverter.string_to_136_array(pin="888")
        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )
        player = MahjongPlayer(seat=0, name="P0", tiles=tuple(closed_tiles), melds=(pon,), score=25000)
        round_state = _make_round_state()
        assert can_declare_tsumo(player, round_state, GameSettings(has_kuitan=True)) is True

    def test_kuitan_disabled_rejects_open_tanyao_tsumo(self):
        """Open tanyao hand is rejected when kuitan is disabled (no yaku)."""
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        pon_tiles = TilesConverter.string_to_136_array(pin="888")
        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )
        player = MahjongPlayer(seat=0, name="P0", tiles=tuple(closed_tiles), melds=(pon,), score=25000)
        round_state = _make_round_state()
        assert can_declare_tsumo(player, round_state, GameSettings(has_kuitan=False)) is False

    def test_kuitan_disabled_still_allows_closed_tanyao(self):
        """Closed tanyao (menzen) is always valid, regardless of kuitan setting."""
        tiles = TilesConverter.string_to_136_array(man="234567", pin="234", sou="23455")
        player = MahjongPlayer(seat=0, name="P0", tiles=tuple(tiles), score=25000)
        round_state = _make_round_state()
        # menzen tsumo is a yaku by itself, so closed tanyao is allowed
        assert can_declare_tsumo(player, round_state, GameSettings(has_kuitan=False)) is True

    def test_kuitan_wired_through_optional_rules(self):
        """has_kuitan maps to has_open_tanyao in the mahjong library's OptionalRules."""
        rules_enabled = build_optional_rules(GameSettings(has_kuitan=True))
        assert rules_enabled.has_open_tanyao is True
        rules_disabled = build_optional_rules(GameSettings(has_kuitan=False))
        assert rules_disabled.has_open_tanyao is False

    def test_kuitan_disabled_rejects_open_tanyao_ron(self):
        """Open tanyao ron is rejected when kuitan is disabled."""
        closed_tiles = TilesConverter.string_to_136_array(man="234567", pin="234", sou="5")
        pon_tiles = TilesConverter.string_to_136_array(sou="888")
        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )
        player = MahjongPlayer(seat=0, name="P0", tiles=tuple(closed_tiles + pon_tiles), melds=(pon,), score=25000)
        round_state = _make_round_state()
        win_tile = TilesConverter.string_to_136_array(sou="55")[1]
        assert can_call_ron(player, win_tile, round_state, GameSettings(has_kuitan=False)) is False


class TestIppatsuToggle:
    """Verify has_ippatsu setting controls ippatsu yaku credit."""

    def test_ippatsu_credited_when_setting_enabled(self):
        """Ippatsu yaku is awarded when setting is True and player flag is set."""
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        discard_tile = TilesConverter.string_to_136_array(sou="9")[0]
        round_state = _make_round_state()
        # add all_discards to prevent tenhou detection
        round_state = round_state.model_copy(update={"all_discards": (discard_tile,)})
        round_state = update_player(
            round_state,
            0,
            tiles=tuple(tiles),
            is_riichi=True,
            is_ippatsu=True,
            discards=(Discard(tile_id=discard_tile),),
        )
        player = round_state.players[0]
        win_tile = tiles[-1]
        settings = GameSettings(has_ippatsu=True)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        # yaku_id 3 = ippatsu
        assert any(y.yaku_id == 3 for y in result.yaku)

    def test_ippatsu_not_credited_when_setting_disabled(self):
        """Ippatsu yaku is NOT awarded when setting is False, even if player flag is set."""
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        discard_tile = TilesConverter.string_to_136_array(sou="9")[0]
        round_state = _make_round_state()
        round_state = round_state.model_copy(update={"all_discards": (discard_tile,)})
        round_state = update_player(
            round_state,
            0,
            tiles=tuple(tiles),
            is_riichi=True,
            is_ippatsu=True,
            discards=(Discard(tile_id=discard_tile),),
        )
        player = round_state.players[0]
        win_tile = tiles[-1]
        settings = GameSettings(has_ippatsu=False)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        assert not any(y.yaku_id == 3 for y in result.yaku)


class TestRenhouToggle:
    """Verify renhou_value setting controls renhou detection and scoring."""

    def _make_renhou_round_state(self):
        """Create a round state for renhou eligibility (first go-around, no calls)."""
        players = tuple(create_player(seat=i) for i in range(4))
        return create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            all_discards=(),
            players_with_open_hands=(),
            wall=tuple(range(70)),
            dead_wall=tuple(range(14)),
            dora_indicators=TilesConverter.string_to_136_array(man="9"),
        )

    def test_renhou_disabled_does_not_award_yaku(self):
        """When renhou_value=NONE, renhou yaku is not awarded even if eligible."""
        tiles = TilesConverter.string_to_136_array(man="234", pin="234", sou="234678", honors="11")
        round_state = self._make_renhou_round_state()
        round_state = update_player(round_state, 1, tiles=tuple(tiles))
        player = round_state.players[1]
        win_tile = tiles[-1]
        settings = GameSettings(renhou_value=RenhouValue.NONE)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=False)
        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        # yaku_id 11 = renhou
        assert not any(y.yaku_id == 11 for y in result.yaku)

    def test_renhou_mangan_awards_5_han(self):
        """When renhou_value=MANGAN, renhou is awarded as 5-han yaku."""
        tiles = TilesConverter.string_to_136_array(man="234", pin="234", sou="234678", honors="11")
        round_state = self._make_renhou_round_state()
        round_state = update_player(round_state, 1, tiles=tuple(tiles))
        player = round_state.players[1]
        win_tile = tiles[-1]
        settings = GameSettings(renhou_value=RenhouValue.MANGAN)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=False)
        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        assert any(y.yaku_id == 11 for y in result.yaku)
        assert result.han >= 5

    def test_renhou_yakuman_setting_wired(self):
        """renhou_value=YAKUMAN maps to renhou_as_yakuman=True in OptionalRules."""
        rules = build_optional_rules(GameSettings(renhou_value=RenhouValue.YAKUMAN))
        assert rules.renhou_as_yakuman is True

    def test_renhou_mangan_setting_not_yakuman(self):
        """renhou_value=MANGAN maps to renhou_as_yakuman=False in OptionalRules."""
        rules = build_optional_rules(GameSettings(renhou_value=RenhouValue.MANGAN))
        assert rules.renhou_as_yakuman is False


class TestRenhouEligibility:
    """Verify renhou eligibility enforces: non-dealer, first uninterrupted turn, ron only."""

    def test_dealer_not_eligible_for_renhou(self):
        """Dealer cannot have renhou (tenhou is the dealer equivalent)."""
        players = tuple(create_player(seat=i) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            all_discards=(),
            players_with_open_hands=(),
        )
        assert is_renhou(round_state.players[0], round_state) is False

    def test_non_dealer_eligible_for_renhou(self):
        """Non-dealer with no discards and no calls is eligible."""
        players = tuple(create_player(seat=i) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            all_discards=(),
            players_with_open_hands=(),
        )
        assert is_renhou(round_state.players[1], round_state) is True

    def test_renhou_blocked_by_any_call(self):
        """Any open meld by any player blocks renhou for all."""
        players = tuple(create_player(seat=i) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            all_discards=(),
            players_with_open_hands=(3,),
        )
        assert is_renhou(round_state.players[1], round_state) is False

    def test_renhou_blocked_after_player_discards(self):
        """Player who has already discarded is not eligible for renhou."""
        players = tuple(create_player(seat=i) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            all_discards=(),
            players_with_open_hands=(),
        )
        tile = TilesConverter.string_to_136_array(man="1")[0]
        round_state = update_player(round_state, 1, discards=(Discard(tile_id=tile),))
        assert is_renhou(round_state.players[1], round_state) is False

    def test_renhou_is_ron_only_not_tsumo(self):
        """Renhou flag is only set for ron (is_tsumo=False), not tsumo."""
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        round_state = create_round_state(
            wall=tuple(range(70)),
            dead_wall=tuple(range(14)),
            dora_indicators=TilesConverter.string_to_136_array(man="9"),
            all_discards=(),
            players_with_open_hands=(),
        )
        round_state = update_player(round_state, 1, tiles=tuple(tiles))
        player = round_state.players[1]
        win_tile = tiles[-1]

        # tsumo context: renhou should not appear
        ctx_tsumo = ScoringContext(
            player=player,
            round_state=round_state,
            settings=GameSettings(),
            is_tsumo=True,
        )
        result_tsumo = calculate_hand_value(ctx_tsumo, win_tile)
        assert not any(y.yaku_id == 11 for y in result_tsumo.yaku)

    def test_renhou_blocked_by_closed_kan(self):
        """A closed kan by any player blocks renhou."""
        players = tuple(create_player(seat=i) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            all_discards=(),
            players_with_open_hands=(),
        )
        kan_tiles = TilesConverter.string_to_136_array(man="1111")
        closed_kan = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=tuple(kan_tiles), opened=False)
        round_state = update_player(round_state, 0, melds=(closed_kan,))
        assert is_renhou(round_state.players[1], round_state) is False
