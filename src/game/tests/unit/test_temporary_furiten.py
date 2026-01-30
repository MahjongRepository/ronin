"""
Unit tests for temporary furiten.

Temporary furiten: when a player passes on a ron opportunity, they cannot ron
until their next discard. They can still win by tsumo.
"""

from mahjong.tile import TilesConverter

from game.logic.action_handlers import handle_pass
from game.logic.enums import CallType, MeldCallType
from game.logic.round import _reset_players, discard_tile
from game.logic.state import MahjongGameState, MahjongPlayer, MahjongRoundState, PendingCallPrompt
from game.logic.tiles import tile_to_34
from game.logic.types import MeldCaller
from game.logic.win import (
    apply_temporary_furiten,
    can_call_ron,
    can_declare_tsumo,
    is_chankan_possible,
)
from game.tests.unit.helpers import _string_to_34_tile


def _create_round_state(
    players: list[MahjongPlayer] | None = None,
    dealer_seat: int = 0,
) -> MahjongRoundState:
    """Create a basic round state for testing."""
    if players is None:
        players = [MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4)]
    return MahjongRoundState(
        dealer_seat=dealer_seat,
        current_player_seat=0,
        round_wind=0,
        players=players,
        dora_indicators=TilesConverter.string_to_136_array(man="1"),
    )


class TestApplyTemporaryFuriten:
    def test_passing_on_ron_sets_temporary_furiten(self):
        """Player who passes on a ron opportunity gets temporary furiten."""
        player = MahjongPlayer(seat=1, name="Player1")
        assert player.is_temporary_furiten is False

        apply_temporary_furiten(player)
        assert player.is_temporary_furiten is True


class TestTemporaryFuritenBlocksRon:
    def test_temporary_furiten_blocks_ron(self):
        """Player with temporary furiten cannot call ron."""
        # 123m 456m 789m 12p 55p - waiting for 3p
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=1, name="Player1", tiles=tiles, is_riichi=True, is_temporary_furiten=True)
        round_state = _create_round_state()

        discarded_tile = TilesConverter.string_to_136_array(pin="3")[0]
        assert can_call_ron(player, discarded_tile, round_state) is False

    def test_without_temporary_furiten_can_ron(self):
        """Player without temporary furiten can call ron normally."""
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=1, name="Player1", tiles=tiles, is_riichi=True)
        round_state = _create_round_state()

        discarded_tile = TilesConverter.string_to_136_array(pin="3")[0]
        assert can_call_ron(player, discarded_tile, round_state) is True


class TestTemporaryFuritenAllowsTsumo:
    def test_temporary_furiten_allows_tsumo(self):
        """Player with temporary furiten can still win by tsumo."""
        # winning hand: 123m 456m 789m 123p 55p (14 tiles)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = MahjongPlayer(seat=0, name="Player0", tiles=tiles, is_temporary_furiten=True)
        round_state = _create_round_state()

        assert can_declare_tsumo(player, round_state) is True


class TestTemporaryFuritenClearsOnDiscard:
    def test_clears_on_discard(self):
        """Temporary furiten clears after the player discards."""
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = MahjongPlayer(seat=0, name="Player0", tiles=tiles, is_temporary_furiten=True)
        round_state = _create_round_state(
            players=[player] + [MahjongPlayer(seat=i, name=f"Player{i}") for i in range(1, 4)]
        )

        # discard a tile
        tile_to_discard = tiles[0]
        discard_tile(round_state, 0, tile_to_discard)

        assert player.is_temporary_furiten is False


class TestTemporaryFuritenResetsOnNewRound:
    def test_resets_on_new_round(self):
        """Temporary furiten resets at the start of a new round."""
        players = [MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4)]
        players[1].is_temporary_furiten = True
        round_state = _create_round_state(players=players)

        _reset_players(round_state)

        assert players[1].is_temporary_furiten is False


class TestPassingOnMeldDoesNotSetTemporaryFuriten:
    def test_passing_on_meld_no_temporary_furiten(self):
        """Passing on a pon/chi opportunity does NOT set temporary furiten."""
        # player 1 hand: 1112m 456p 789s 55s (13 tiles) - waiting for 3m, not 5s
        # player 1 could pon 5s, but is NOT waiting on it for ron
        tiles_p1 = TilesConverter.string_to_136_array(man="1112", pin="456", sou="78955")
        # player 0 has 14 tiles including 5s to discard
        tiles_p0 = TilesConverter.string_to_136_array(man="234567", pin="34567", sou="235")
        players = [
            MahjongPlayer(seat=0, name="Player0", tiles=tiles_p0),
            MahjongPlayer(seat=1, name="Player1", tiles=tiles_p1),
            MahjongPlayer(seat=2, name="Player2"),
            MahjongPlayer(seat=3, name="Player3"),
        ]
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
            dora_indicators=TilesConverter.string_to_136_array(man="1"),
        )
        game_state = MahjongGameState(round_state=round_state)

        # player 0 discards 5s (player 1 could pon but is NOT waiting on it)
        five_sou_34 = _string_to_34_tile(sou="5")
        tile_5s = next(t for t in tiles_p0 if tile_to_34(t) == five_sou_34)
        discard_tile(round_state, 0, tile_5s)

        # set up pending meld prompt for seat 1
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_5s,
            from_seat=0,
            pending_seats={1},
            callers=[MeldCaller(seat=1, call_type=MeldCallType.PON, tile_34=five_sou_34, priority=1)],
        )

        # player 1 passes on the meld-only opportunity
        handle_pass(round_state, game_state, seat=1)

        # temporary furiten should NOT be set since this was a meld opportunity, not ron
        assert players[1].is_temporary_furiten is False


class TestTemporaryFuritenOnChankan:
    def test_chankan_pass_sets_temporary_furiten(self):
        """Passing on a chankan ron opportunity sets temporary furiten."""
        player = MahjongPlayer(seat=2, name="Player2")
        assert player.is_temporary_furiten is False

        # simulates passing on a chankan opportunity
        apply_temporary_furiten(player)
        assert player.is_temporary_furiten is True

    def test_temporary_furiten_blocks_chankan_ron(self):
        """Player with temporary furiten cannot ron on chankan."""
        # player 1 has a hand waiting for a specific tile
        # 123m 456m 789m 12p 55p - waiting for 3p
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        players = [MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4)]
        players[1].tiles = tiles
        players[1].is_riichi = True
        players[1].is_temporary_furiten = True

        round_state = _create_round_state(players=players)

        # player 0 adds kan with 3p - player 1 would normally be able to chankan
        kan_tile = TilesConverter.string_to_136_array(pin="3")[0]
        chankan_seats = is_chankan_possible(round_state, caller_seat=0, kan_tile=kan_tile)

        # player 1 should NOT be in chankan_seats due to temporary furiten
        assert 1 not in chankan_seats


class TestHandlePassSetsTemporaryFuriten:
    def _create_game_state(self, players: list[MahjongPlayer] | None = None) -> MahjongGameState:
        """Create a game state for testing handle_pass."""
        if players is None:
            players = [MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4)]
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
            dora_indicators=TilesConverter.string_to_136_array(man="1"),
        )
        return MahjongGameState(round_state=round_state)

    def test_handle_pass_sets_temporary_furiten_on_ron_opportunity(self):
        """handle_pass sets temporary furiten when player passes on ron prompt."""
        # player 1 is waiting for 3p: 123m 456m 789m 12p 55p (13 tiles)
        tiles_p1 = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        # player 0 needs 14 tiles so after discard they have 13
        tiles_p0 = TilesConverter.string_to_136_array(man="234567", pin="345678", sou="23")
        players = [
            MahjongPlayer(seat=0, name="Player0", tiles=tiles_p0),
            MahjongPlayer(seat=1, name="Player1", tiles=tiles_p1, is_riichi=True),
            MahjongPlayer(seat=2, name="Player2"),
            MahjongPlayer(seat=3, name="Player3"),
        ]
        game_state = self._create_game_state(players=players)
        round_state = game_state.round_state

        # player 0 discards 3p (which player 1 is waiting on)
        tile_3p = next(t for t in tiles_p0 if t // 4 == 11)  # 3p in 34-format is index 11
        discard_tile(round_state, 0, tile_3p)

        # set up pending ron prompt for seat 1
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=tile_3p,
            from_seat=0,
            pending_seats={1},
            callers=[1],
        )

        # player 1 passes on the ron opportunity
        handle_pass(round_state, game_state, seat=1)

        assert players[1].is_temporary_furiten is True

    def test_handle_pass_no_furiten_when_meld_prompt(self):
        """handle_pass does not set furiten when player passes on meld prompt (not ron)."""
        # player 1 is waiting for 3p: 123m 456m 789m 12p 55p
        tiles_p1 = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        # player 0 has 14 tiles including 9s to discard
        tiles_p0 = TilesConverter.string_to_136_array(man="234567", pin="45678", sou="239")
        players = [
            MahjongPlayer(seat=0, name="Player0", tiles=tiles_p0),
            MahjongPlayer(seat=1, name="Player1", tiles=tiles_p1),
            MahjongPlayer(seat=2, name="Player2"),
            MahjongPlayer(seat=3, name="Player3"),
        ]
        game_state = self._create_game_state(players=players)
        round_state = game_state.round_state

        # player 0 discards 9s (player 1 is NOT waiting on this)
        tile_9s = next(t for t in tiles_p0 if t // 4 == 26)  # 9s in 34-format is index 26
        discard_tile(round_state, 0, tile_9s)

        # set up a meld prompt (not ron) for seat 1
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_9s,
            from_seat=0,
            pending_seats={1},
            callers=[MeldCaller(seat=1, call_type=MeldCallType.PON, tile_34=tile_9s // 4, priority=1)],
        )

        # player 1 passes on the meld opportunity
        handle_pass(round_state, game_state, seat=1)

        # furiten not set for meld-only prompt
        assert players[1].is_temporary_furiten is False

    def test_handle_pass_no_furiten_when_no_pending_prompt(self):
        """handle_pass does not set furiten when there is no pending call prompt."""
        tiles_p1 = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        tiles_p0 = TilesConverter.string_to_136_array(man="234567", pin="45678", sou="23")
        players = [
            MahjongPlayer(seat=0, name="Player0", tiles=tiles_p0),
            MahjongPlayer(seat=1, name="Player1", tiles=tiles_p1),
            MahjongPlayer(seat=2, name="Player2"),
            MahjongPlayer(seat=3, name="Player3"),
        ]
        game_state = self._create_game_state(players=players)

        # no pending call prompt set
        handle_pass(game_state.round_state, game_state, seat=1)

        assert players[1].is_temporary_furiten is False
