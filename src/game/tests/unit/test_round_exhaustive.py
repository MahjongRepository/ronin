"""
Unit tests for exhaustive draw processing, tempai detection, and nagashi mangan.
"""

from mahjong.meld import Meld
from mahjong.tile import TilesConverter

from game.logic.round import (
    check_exhaustive_draw,
    check_nagashi_mangan,
    is_tempai,
    process_exhaustive_draw,
)
from game.logic.state import (
    Discard,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
)
from game.logic.types import NagashiManganResult


class TestCheckExhaustiveDraw:
    def test_returns_true_when_wall_empty(self):
        round_state = MahjongRoundState(wall=[])

        result = check_exhaustive_draw(round_state)

        assert result is True

    def test_returns_false_when_wall_has_tiles(self):
        round_state = MahjongRoundState(wall=TilesConverter.string_to_136_array(man="123"))

        result = check_exhaustive_draw(round_state)

        assert result is False

    def test_returns_false_when_wall_has_one_tile(self):
        round_state = MahjongRoundState(wall=TilesConverter.string_to_136_array(pin="2"))

        result = check_exhaustive_draw(round_state)

        assert result is False


class TestIsTempai:
    def _create_tempai_hand(self) -> list[int]:
        """
        Create a tempai hand: 11m 234m 567m 888m 99m, waiting for 9m pair.

        Total: 13 tiles
        """
        return TilesConverter.string_to_136_array(man="1123456788899")

    def _create_non_tempai_hand(self) -> list[int]:
        """
        Create a non-tempai hand (random disconnected tiles).

        13 tiles that don't form a near-complete hand.
        """
        return TilesConverter.string_to_136_array(man="13579", pin="2468", sou="1357")

    def test_is_tempai_returns_true_for_tempai_hand(self):
        player = MahjongPlayer(seat=0, name="Test", tiles=self._create_tempai_hand())

        result = is_tempai(player)

        assert result is True

    def test_is_tempai_returns_false_for_non_tempai_hand(self):
        player = MahjongPlayer(seat=0, name="Test", tiles=self._create_non_tempai_hand())

        result = is_tempai(player)

        assert result is False

    def test_is_tempai_with_chiitoi_wait(self):
        """
        Chiitoitsu (seven pairs) tempai: 6 pairs + 1 single tile.
        """
        # 11m 22m 33m 44m 55m 66m 7m (waiting for second 7m)
        hand = TilesConverter.string_to_136_array(man="1122334455667")
        player = MahjongPlayer(seat=0, name="Test", tiles=hand)

        result = is_tempai(player)

        assert result is True

    def test_is_tempai_with_open_hand(self):
        """
        Tempai with open hand (fewer tiles in hand due to melds).

        Player has 1 pon meld (3 tiles), so only 10 tiles in hand.
        """
        # hand: 234m 567m 888m 9m (10 tiles, waiting for 9m pair)
        hand = TilesConverter.string_to_136_array(man="2345678889")
        player = MahjongPlayer(seat=0, name="Test", tiles=hand)

        result = is_tempai(player)

        assert result is True


class TestProcessExhaustiveDraw:
    def _create_game_state_with_players(self, tempai_seats: list[int]) -> MahjongGameState:
        """
        Create a game state with players where specified seats are in tempai.
        """
        tempai_hand = TilesConverter.string_to_136_array(man="1123456788899")
        non_tempai_hand = TilesConverter.string_to_136_array(man="13579", pin="2468", sou="1357")
        players = [
            MahjongPlayer(
                seat=seat,
                name=f"Player{seat}",
                tiles=tempai_hand if seat in tempai_seats else non_tempai_hand,
                score=25000,
            )
            for seat in range(4)
        ]
        round_state = MahjongRoundState(players=players, wall=[])
        return MahjongGameState(round_state=round_state)

    def test_process_exhaustive_draw_one_tempai(self):
        """
        1 tempai, 3 noten: each noten pays 1000 to tempai.
        """
        game_state = self._create_game_state_with_players(tempai_seats=[0])
        round_state = game_state.round_state

        result = process_exhaustive_draw(game_state)

        assert result.tempai_seats == [0]
        assert result.noten_seats == [1, 2, 3]
        assert result.score_changes == {0: 3000, 1: -1000, 2: -1000, 3: -1000}
        # verify scores updated
        assert round_state.players[0].score == 28000
        assert round_state.players[1].score == 24000
        assert round_state.players[2].score == 24000
        assert round_state.players[3].score == 24000

    def test_process_exhaustive_draw_two_tempai(self):
        """
        2 tempai, 2 noten: each noten pays 1500 total, each tempai gets 1500.
        """
        game_state = self._create_game_state_with_players(tempai_seats=[0, 2])
        round_state = game_state.round_state

        result = process_exhaustive_draw(game_state)

        assert result.tempai_seats == [0, 2]
        assert result.noten_seats == [1, 3]
        assert result.score_changes == {0: 1500, 1: -1500, 2: 1500, 3: -1500}
        assert round_state.players[0].score == 26500
        assert round_state.players[1].score == 23500
        assert round_state.players[2].score == 26500
        assert round_state.players[3].score == 23500

    def test_process_exhaustive_draw_three_tempai(self):
        """
        3 tempai, 1 noten: noten pays 1000 to each tempai.
        """
        game_state = self._create_game_state_with_players(tempai_seats=[0, 1, 2])
        round_state = game_state.round_state

        result = process_exhaustive_draw(game_state)

        assert result.tempai_seats == [0, 1, 2]
        assert result.noten_seats == [3]
        assert result.score_changes == {0: 1000, 1: 1000, 2: 1000, 3: -3000}
        assert round_state.players[0].score == 26000
        assert round_state.players[1].score == 26000
        assert round_state.players[2].score == 26000
        assert round_state.players[3].score == 22000

    def test_process_exhaustive_draw_all_tempai(self):
        """
        All 4 tempai: no payment.
        """
        game_state = self._create_game_state_with_players(tempai_seats=[0, 1, 2, 3])
        round_state = game_state.round_state

        result = process_exhaustive_draw(game_state)

        assert result.tempai_seats == [0, 1, 2, 3]
        assert result.noten_seats == []
        assert result.score_changes == {0: 0, 1: 0, 2: 0, 3: 0}
        for player in round_state.players:
            assert player.score == 25000

    def test_process_exhaustive_draw_all_noten(self):
        """
        All 4 noten: no payment.
        """
        game_state = self._create_game_state_with_players(tempai_seats=[])
        round_state = game_state.round_state

        result = process_exhaustive_draw(game_state)

        assert result.tempai_seats == []
        assert result.noten_seats == [0, 1, 2, 3]
        assert result.score_changes == {0: 0, 1: 0, 2: 0, 3: 0}
        for player in round_state.players:
            assert player.score == 25000

    def test_process_exhaustive_draw_returns_type(self):
        """
        Verify the result contains the correct type field.
        """
        game_state = self._create_game_state_with_players(tempai_seats=[0])

        result = process_exhaustive_draw(game_state)

        assert result.type == "exhaustive_draw"


class TestCheckNagashiMangan:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state with 4 players for nagashi mangan testing."""
        players = [
            MahjongPlayer(seat=0, name="Player0", score=25000),
            MahjongPlayer(seat=1, name="Player1", score=25000),
            MahjongPlayer(seat=2, name="Player2", score=25000),
            MahjongPlayer(seat=3, name="Player3", score=25000),
        ]
        return MahjongRoundState(players=players, wall=[])

    def test_qualifies_with_all_terminal_honor_discards(self):
        """Player with only terminal/honor discards and none claimed qualifies."""
        round_state = self._create_round_state()
        man_1 = TilesConverter.string_to_136_array(man="1")[0]
        man_9 = TilesConverter.string_to_136_array(man="9")[0]
        east = TilesConverter.string_to_136_array(honors="1")[0]
        south = TilesConverter.string_to_136_array(honors="2")[0]
        haku = TilesConverter.string_to_136_array(honors="5")[0]
        round_state.players[0].discards = [
            Discard(tile_id=man_1),  # 1m (terminal)
            Discard(tile_id=man_9),  # 9m (terminal)
            Discard(tile_id=east),  # East (honor)
            Discard(tile_id=south),  # South (honor)
            Discard(tile_id=haku),  # Haku (honor)
        ]

        result = check_nagashi_mangan(round_state)

        assert result == [0]

    def test_fails_with_non_terminal_discard(self):
        """Player with a non-terminal/non-honor discard does not qualify."""
        round_state = self._create_round_state()
        man_2 = TilesConverter.string_to_136_array(man="2")[0]
        east = TilesConverter.string_to_136_array(honors="1")[0]
        round_state.players[0].discards = [
            Discard(tile_id=man_2),  # 2m (simples, not terminal)
            Discard(tile_id=east),  # East (honor)
        ]

        result = check_nagashi_mangan(round_state)

        assert result == []

    def test_fails_when_discard_claimed_by_opponent(self):
        """Player whose discard was claimed by opponent does not qualify."""
        round_state = self._create_round_state()
        man_1 = TilesConverter.string_to_136_array(man="1")[0]
        east_tiles = TilesConverter.string_to_136_array(honors="111")
        round_state.players[0].discards = [
            Discard(tile_id=man_1),  # 1m (terminal)
            Discard(tile_id=east_tiles[0]),  # East (honor)
        ]
        # opponent at seat 1 has a pon meld taken from seat 0
        pon_meld = Meld(
            meld_type=Meld.PON,
            tiles=east_tiles[:3],
            opened=True,
            called_tile=east_tiles[0],
            who=1,
            from_who=0,
        )
        round_state.players[1].melds = [pon_meld]

        result = check_nagashi_mangan(round_state)

        assert result == []

    def test_no_discards_does_not_qualify(self):
        """Player with no discards does not qualify."""
        round_state = self._create_round_state()
        # no discards for any player

        result = check_nagashi_mangan(round_state)

        assert result == []

    def test_multiple_players_qualify(self):
        """Multiple players can qualify simultaneously."""
        round_state = self._create_round_state()
        man_1 = TilesConverter.string_to_136_array(man="1")[0]
        man_9 = TilesConverter.string_to_136_array(man="9")[0]
        east = TilesConverter.string_to_136_array(honors="1")[0]
        haku = TilesConverter.string_to_136_array(honors="5")[0]
        round_state.players[0].discards = [
            Discard(tile_id=man_1),  # 1m
            Discard(tile_id=east),  # East
        ]
        round_state.players[2].discards = [
            Discard(tile_id=man_9),  # 9m
            Discard(tile_id=haku),  # Haku
        ]

        result = check_nagashi_mangan(round_state)

        assert result == [0, 2]

    def test_claimed_by_self_does_not_disqualify(self):
        """Melds from_who == self (closed kan) should not disqualify."""
        round_state = self._create_round_state()
        man_1 = TilesConverter.string_to_136_array(man="1")[0]
        east_tiles = TilesConverter.string_to_136_array(honors="1111")
        round_state.players[0].discards = [
            Discard(tile_id=man_1),  # 1m
            Discard(tile_id=east_tiles[0]),  # East
        ]
        # player 0 has a closed kan (from_who == self)
        kan_meld = Meld(
            meld_type=Meld.KAN,
            tiles=east_tiles[:4],
            opened=False,
            called_tile=east_tiles[0],
            who=0,
            from_who=0,
        )
        round_state.players[0].melds = [kan_meld]

        result = check_nagashi_mangan(round_state)

        assert result == [0]


class TestProcessExhaustiveDrawNagashiMangan:
    def _create_game_state_for_nagashi(self) -> MahjongGameState:
        """
        Create a game state where seat 0 qualifies for nagashi mangan.

        Uses non-tempai hands to simplify score verification.
        """
        non_tempai_hand = TilesConverter.string_to_136_array(man="13579", pin="2468", sou="1357")
        players = [
            MahjongPlayer(seat=seat, name=f"Player{seat}", tiles=non_tempai_hand, score=25000)
            for seat in range(4)
        ]

        # seat 0 has all terminal/honor discards
        man_1 = TilesConverter.string_to_136_array(man="1")[0]
        man_9 = TilesConverter.string_to_136_array(man="9")[0]
        east = TilesConverter.string_to_136_array(honors="1")[0]
        players[0].discards = [
            Discard(tile_id=man_1),  # 1m
            Discard(tile_id=man_9),  # 9m
            Discard(tile_id=east),  # East
        ]

        round_state = MahjongRoundState(players=players, wall=[], dealer_seat=0)
        return MahjongGameState(round_state=round_state)

    def test_process_exhaustive_draw_returns_nagashi_mangan_result(self):
        """When nagashi mangan qualifies, returns NagashiManganResult."""
        game_state = self._create_game_state_for_nagashi()

        result = process_exhaustive_draw(game_state)

        assert isinstance(result, NagashiManganResult)
        assert result.type == "nagashi_mangan"
        assert result.qualifying_seats == [0]

    def test_nagashi_mangan_dealer_scoring(self):
        """Dealer nagashi mangan: 4000 from each non-dealer (12000 total)."""
        game_state = self._create_game_state_for_nagashi()
        # seat 0 is dealer

        result = process_exhaustive_draw(game_state)

        assert isinstance(result, NagashiManganResult)
        assert result.score_changes[0] == 12000
        assert result.score_changes[1] == -4000
        assert result.score_changes[2] == -4000
        assert result.score_changes[3] == -4000
        # verify scores applied
        assert game_state.round_state.players[0].score == 37000
        assert game_state.round_state.players[1].score == 21000

    def test_nagashi_mangan_non_dealer_scoring(self):
        """Non-dealer nagashi mangan: 4000 from dealer + 2000 from each non-dealer."""
        game_state = self._create_game_state_for_nagashi()
        game_state.round_state.dealer_seat = 1  # seat 1 is dealer, seat 0 is non-dealer

        result = process_exhaustive_draw(game_state)

        assert isinstance(result, NagashiManganResult)
        # seat 0 gets 4000+2000+2000 = 8000
        assert result.score_changes[0] == 8000
        # dealer (seat 1) pays 4000
        assert result.score_changes[1] == -4000
        # non-dealers pay 2000 each
        assert result.score_changes[2] == -2000
        assert result.score_changes[3] == -2000
