"""
Unit tests for core win detection edge cases requiring direct state construction.

Covers: check_tsumo meld dedup logic, can_declare_tsumo open hand yaku validation,
get_waiting_tiles multi-wait/special-hand/open-hand detection, is_furiten discard matching,
can_call_ron open hand yaku/furiten/meld-removed-from-hand paths,
is_tenhou/is_chiihou guard clause boundary conditions.
"""

from mahjong.tile import TilesConverter

from game.logic.meld_wrapper import FrozenMeld
from game.logic.settings import GameSettings
from game.logic.state import (
    Discard,
    MahjongPlayer,
    MahjongRoundState,
)
from game.logic.wall import Wall
from game.logic.win import (
    can_call_ron,
    can_declare_tsumo,
    check_tsumo,
    check_tsumo_with_tiles,
    get_waiting_tiles,
    is_chiihou,
    is_furiten,
    is_renhou,
    is_tenhou,
)


class TestCheckTsumoMeldDedup:
    """Test check_tsumo meld tile deduplication in all_player_tiles."""

    def test_winning_hand_with_open_pon(self):
        # meld tiles IN player.tiles (dedup path in all_player_tiles)
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        pon_tiles = TilesConverter.string_to_136_array(pin="888")

        all_tiles = closed_tiles + pon_tiles

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(all_tiles), melds=(pon,), score=25000)
        assert check_tsumo(player) is True

    def test_winning_hand_with_meld_tiles_removed_from_hand(self):
        # meld tiles NOT in player.tiles (actual gameplay after call_pon)
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

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(closed_tiles), melds=(pon,), score=25000)
        assert check_tsumo(player) is True


class TestCheckTsumoWithTiles:
    """Test check_tsumo_with_tiles uses all_tiles_from_hand_and_melds for consistent tile assembly."""

    def test_winning_hand_with_ron_tile_and_meld(self):
        """Winning hand with ron tile added and meld tiles separate from closed hand."""
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="2355")
        pon_tiles = TilesConverter.string_to_136_array(honors="555")

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(closed_tiles), melds=(pon,), score=25000)
        ron_tile = TilesConverter.string_to_136_array(sou="4")[0]
        tiles_with_ron = [*closed_tiles, ron_tile]

        assert check_tsumo_with_tiles(player, tiles_with_ron) is True

    def test_non_winning_hand_returns_false(self):
        """Non-winning hand returns False."""
        closed_tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(closed_tiles), score=25000)
        wrong_tile = TilesConverter.string_to_136_array(sou="9")[0]
        tiles_with_wrong = [*closed_tiles, wrong_tile]

        assert check_tsumo_with_tiles(player, tiles_with_wrong) is False


class TestCanDeclareTsumo:
    def _create_round_state(self, dealer_seat: int = 0) -> MahjongRoundState:
        return MahjongRoundState(
            dealer_seat=dealer_seat,
            current_player_seat=0,
            round_wind=0,
            wall=Wall(
                live_tiles=tuple(range(10)),
                dora_indicators=tuple(TilesConverter.string_to_136_array(man="1")),
            ),
        )

    def test_non_winning_hand_cannot_declare(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), score=25000)
        round_state = self._create_round_state()

        assert can_declare_tsumo(player, round_state, GameSettings()) is False

    def test_open_hand_with_yakuhai_can_declare(self):
        # open hand with haku pon (yakuhai yaku exists)
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        haku_tiles = TilesConverter.string_to_136_array(honors="555")

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(haku_tiles),
            opened=True,
            called_tile=haku_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(closed_tiles), melds=(pon,), score=25000)
        round_state = self._create_round_state()

        assert can_declare_tsumo(player, round_state, GameSettings()) is True

    def test_open_hand_without_yaku_cannot_declare(self):
        # open hand with pon of 1m, no yakuhai, no tanyao -> no yaku
        closed_tiles_before_win = TilesConverter.string_to_136_array(man="2345", pin="234", sou="567")
        win_tile = TilesConverter.string_to_136_array(man="5")[:1]
        pon_tiles = TilesConverter.string_to_136_array(man="111")

        all_tiles = closed_tiles_before_win + pon_tiles + win_tile

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(all_tiles), melds=(pon,), score=25000)
        round_state = self._create_round_state()

        assert can_declare_tsumo(player, round_state, GameSettings()) is False

    def test_open_tanyao_with_kuitan_enabled(self):
        # open tanyao (kuitan) - all simples with open meld
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

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(closed_tiles), melds=(pon,), score=25000)
        round_state = self._create_round_state()

        assert can_declare_tsumo(player, round_state, GameSettings()) is True


class TestGetWaitingTiles:
    def test_tempai_multiple_waits(self):
        # ryanmen wait: 123m 456m 789m 45p 5p -> waiting for 3p or 6p
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="4555")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), score=25000)

        waiting = get_waiting_tiles(player)

        assert 11 in waiting  # 3p
        assert 14 in waiting  # 6p

    def test_tempai_tanki_wait(self):
        # tanki wait: 111m 222m 333m 444m 5m -> waiting for 5m
        tiles = TilesConverter.string_to_136_array(man="1112223334445")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), score=25000)

        waiting = get_waiting_tiles(player)

        assert 4 in waiting  # 5m

    def test_chiitoitsu_wait(self):
        # 6 pairs + single: 11m 22m 33m 44p 55p 66s 7s -> waiting for 7s
        tiles = TilesConverter.string_to_136_array(man="112233", pin="4455", sou="667")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), score=25000)

        waiting = get_waiting_tiles(player)

        assert 24 in waiting  # 7s

    def test_waiting_tiles_with_open_pon_meld_tiles_removed_from_hand(self):
        # meld tiles NOT in player.tiles (actual gameplay after call_pon)
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="2355")
        pon_tiles = TilesConverter.string_to_136_array(pin="888")

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(closed_tiles), melds=(pon,), score=25000)

        waiting = get_waiting_tiles(player)

        assert 18 in waiting  # 1s
        assert 21 in waiting  # 4s


class TestIsFuriten:
    def test_not_furiten_no_discards(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), score=25000)

        assert is_furiten(player) is False

    def test_not_furiten_irrelevant_discards(self):
        # tempai waiting for 3p, discarded unrelated 1m
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        discards = (Discard(tile_id=TilesConverter.string_to_136_array(man="1")[0]),)
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), discards=discards, score=25000)

        assert is_furiten(player) is False

    def test_furiten_discarded_waiting_tile(self):
        # tempai waiting for 3p, already discarded 3p
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        discards = (Discard(tile_id=TilesConverter.string_to_136_array(pin="3")[0]),)
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), discards=discards, score=25000)

        assert is_furiten(player) is True

    def test_furiten_multiple_discards_one_waiting(self):
        # tempai waiting for 3p or 6p, discarded 6p (one of two waits)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="4555")
        discards = (
            Discard(tile_id=TilesConverter.string_to_136_array(man="1")[0]),
            Discard(tile_id=TilesConverter.string_to_136_array(pin="6")[0]),
        )
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), discards=discards, score=25000)

        assert is_furiten(player) is True

    def test_not_tempai_not_furiten(self):
        # not in tempai -> empty waiting set -> not furiten
        tiles = TilesConverter.string_to_136_array(man="1357", pin="2468", sou="13579")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), score=25000)

        assert is_furiten(player) is False


class TestCanCallRon:
    def _create_round_state(self, dealer_seat: int = 0) -> MahjongRoundState:
        return MahjongRoundState(
            dealer_seat=dealer_seat,
            current_player_seat=0,
            round_wind=0,
            wall=Wall(
                live_tiles=tuple(range(10)),
                dora_indicators=tuple(TilesConverter.string_to_136_array(man="1")),
            ),
        )

    def test_cannot_ron_furiten(self):
        # permanent furiten (discarded waiting tile 3p)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        discards = (Discard(tile_id=TilesConverter.string_to_136_array(pin="3")[0]),)
        player = MahjongPlayer(
            seat=0,
            name="Player1",
            tiles=tuple(tiles),
            discards=discards,
            is_riichi=True,
            score=25000,
        )
        round_state = self._create_round_state()

        discarded_tile = TilesConverter.string_to_136_array(pin="3")[0]

        assert can_call_ron(player, discarded_tile, round_state, GameSettings()) is False

    def test_cannot_ron_wrong_tile(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), is_riichi=True, score=25000)
        round_state = self._create_round_state()

        discarded_tile = TilesConverter.string_to_136_array(sou="9")[0]

        assert can_call_ron(player, discarded_tile, round_state, GameSettings()) is False

    def test_can_ron_open_hand_with_yaku(self):
        # open hand with haku pon (yakuhai) via _has_yaku_for_ron_with_tiles
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="2355")
        haku_tiles = TilesConverter.string_to_136_array(honors="555")
        all_tiles = closed_tiles + haku_tiles

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(haku_tiles),
            opened=True,
            called_tile=haku_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(all_tiles), melds=(pon,), score=25000)
        round_state = self._create_round_state()

        discarded_tile = TilesConverter.string_to_136_array(sou="4")[0]

        assert can_call_ron(player, discarded_tile, round_state, GameSettings()) is True

    def test_cannot_ron_open_hand_no_yaku(self):
        # open hand with pon of 1m, no yakuhai, no tanyao -> no yaku
        closed_tiles = TilesConverter.string_to_136_array(man="2345", pin="234", sou="567")
        pon_tiles = TilesConverter.string_to_136_array(man="111")
        all_tiles = closed_tiles + pon_tiles

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(all_tiles), melds=(pon,), score=25000)
        round_state = self._create_round_state()

        discarded_tile = TilesConverter.string_to_136_array(man="6")[0]

        assert can_call_ron(player, discarded_tile, round_state, GameSettings()) is False

    def test_can_ron_open_tanyao(self):
        # open tanyao (kuitan) ron via _has_yaku_for_ron_with_tiles
        closed_tiles = TilesConverter.string_to_136_array(man="234567", pin="234", sou="5")
        pon_tiles = TilesConverter.string_to_136_array(sou="888")
        all_tiles = closed_tiles + pon_tiles

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(all_tiles), melds=(pon,), score=25000)
        round_state = self._create_round_state()

        discarded_tile = TilesConverter.string_to_136_array(sou="55")[1]

        assert can_call_ron(player, discarded_tile, round_state, GameSettings()) is True

    def test_can_ron_open_hand_meld_tiles_removed(self):
        # meld tiles NOT in player.tiles (actual gameplay after call_pon)
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="2355")
        haku_tiles = TilesConverter.string_to_136_array(honors="555")

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(haku_tiles),
            opened=True,
            called_tile=haku_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(closed_tiles), melds=(pon,), score=25000)
        round_state = self._create_round_state()

        discarded_tile = TilesConverter.string_to_136_array(sou="4")[0]

        assert can_call_ron(player, discarded_tile, round_state, GameSettings()) is True

    def test_can_ron_open_chi_meld_tiles_removed(self):
        # chi meld tiles NOT in player.tiles (actual gameplay after call_chi)
        closed_tiles = TilesConverter.string_to_136_array(man="567", sou="2355", honors="555")
        chi_tiles = sorted(TilesConverter.string_to_136_array(man="234"))

        chi = FrozenMeld(
            meld_type=FrozenMeld.CHI,
            tiles=tuple(chi_tiles),
            opened=True,
            called_tile=chi_tiles[0],
            who=0,
            from_who=3,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(closed_tiles), melds=(chi,), score=25000)
        round_state = self._create_round_state()

        discarded_tile = TilesConverter.string_to_136_array(sou="4")[0]

        assert can_call_ron(player, discarded_tile, round_state, GameSettings()) is True


class TestIsTenhou:
    def test_tenhou_dealer_first_draw(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(),
        )
        assert is_tenhou(players[0], round_state) is True

    def test_not_tenhou_non_dealer(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=1,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(),
        )
        assert is_tenhou(players[1], round_state) is False

    def test_not_tenhou_after_discards(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
            all_discards=(1,),
            players_with_open_hands=(),
        )
        assert is_tenhou(players[0], round_state) is False

    def test_not_tenhou_after_meld(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(1,),
        )
        assert is_tenhou(players[0], round_state) is False


class TestIsChiihou:
    def test_chiihou_non_dealer_first_draw(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=1,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(),
        )
        assert is_chiihou(players[1], round_state) is True

    def test_not_chiihou_dealer(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(),
        )
        assert is_chiihou(players[0], round_state) is False

    def test_not_chiihou_after_discards(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=1,
            round_wind=0,
            players=players,
            all_discards=(1,),
            players_with_open_hands=(),
        )
        assert is_chiihou(players[1], round_state) is False

    def test_not_chiihou_after_meld(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=1,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(2,),
        )
        assert is_chiihou(players[1], round_state) is False


class TestIsTenhouClosedKan:
    """Test that closed kans invalidate tenhou."""

    def test_not_tenhou_after_closed_kan(self):
        """Dealer cannot claim tenhou if any player has a closed kan."""
        closed_kan = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(TilesConverter.string_to_136_array(man="1111")),
            opened=False,
        )
        players = tuple(
            MahjongPlayer(
                seat=i,
                name=f"Player{i}",
                melds=(closed_kan,) if i == 0 else (),
                score=25000,
            )
            for i in range(4)
        )
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(),
        )
        assert is_tenhou(players[0], round_state) is False


class TestIsChiihouClosedKan:
    """Test that closed kans invalidate chiihou."""

    def test_not_chiihou_after_dealer_closed_kan(self):
        """Non-dealer cannot claim chiihou if dealer declared a closed kan."""
        closed_kan = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(TilesConverter.string_to_136_array(man="1111")),
            opened=False,
        )
        players = tuple(
            MahjongPlayer(
                seat=i,
                name=f"Player{i}",
                melds=(closed_kan,) if i == 0 else (),
                score=25000,
            )
            for i in range(4)
        )
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=1,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(),
        )
        assert is_chiihou(players[1], round_state) is False


class TestIsRenhouClosedKan:
    """Test that closed kans invalidate renhou."""

    def test_not_renhou_after_closed_kan(self):
        """Non-dealer cannot claim renhou if any player declared a closed kan."""
        closed_kan = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(TilesConverter.string_to_136_array(man="1111")),
            opened=False,
        )
        players = tuple(
            MahjongPlayer(
                seat=i,
                name=f"Player{i}",
                melds=(closed_kan,) if i == 2 else (),
                score=25000,
            )
            for i in range(4)
        )
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=2,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(),
        )
        assert is_renhou(players[1], round_state) is False
