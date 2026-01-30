"""
Unit tests for riichi furiten.

Riichi furiten: when a riichi player's winning tile passes by (for any reason),
they become permanently unable to ron for the rest of the hand. They can still
win by tsumo.
"""

from mahjong.meld import Meld
from mahjong.tile import TilesConverter

from game.logic.action_handlers import handle_pass
from game.logic.enums import CallType
from game.logic.round import _reset_players, discard_tile
from game.logic.state import Discard, MahjongGameState, MahjongPlayer, MahjongRoundState, PendingCallPrompt
from game.logic.tiles import tile_to_34
from game.logic.turn import _check_riichi_furiten
from game.logic.win import (
    can_call_ron,
    can_declare_tsumo,
    get_waiting_tiles,
    is_chankan_possible,
)


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


def _create_game_state(players: list[MahjongPlayer] | None = None) -> MahjongGameState:
    """Create a game state for testing."""
    round_state = _create_round_state(players=players)
    return MahjongGameState(round_state=round_state)


class TestRiichiFuritenSetOnMissedWinningTile:
    def test_riichi_player_winning_tile_passes_due_to_discard_furiten(self):
        """Riichi player whose winning tile passes (already in discard furiten) gets riichi furiten."""
        # player 1 is in riichi, waiting for 3p
        # 123m 456m 789m 12p 55p - waiting for 3p
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        tile_3p = TilesConverter.string_to_136_array(pin="3")[0]
        tile_3p_34 = tile_to_34(tile_3p)

        players = [MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4)]
        players[1].tiles = tiles
        players[1].is_riichi = True
        # player 1 already discarded a 3p (discard furiten)
        players[1].discards = [Discard(tile_id=tile_3p)]

        round_state = _create_round_state(players=players)

        # confirm player 1 is waiting on 3p
        waiting = get_waiting_tiles(players[1])
        assert tile_3p_34 in waiting

        # player 0 discards 3p, player 1 can't call ron (discard furiten)
        # so ron_callers doesn't include seat 1
        discarded_tile = TilesConverter.string_to_136_array(pin="3")[0]
        ron_callers: list[int] = []  # player 1 is furiten so not in callers

        _check_riichi_furiten(round_state, discarded_tile, discarder_seat=0, ron_callers=ron_callers)

        assert players[1].is_riichi_furiten is True

    def test_non_riichi_player_winning_tile_passes_no_riichi_furiten(self):
        """Non-riichi player's winning tile passing does NOT set riichi furiten."""
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")

        players = [MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4)]
        players[1].tiles = tiles
        players[1].is_riichi = False  # not in riichi

        round_state = _create_round_state(players=players)

        discarded_tile = TilesConverter.string_to_136_array(pin="3")[0]
        _check_riichi_furiten(round_state, discarded_tile, discarder_seat=0, ron_callers=[])

        assert players[1].is_riichi_furiten is False

    def test_riichi_player_in_ron_callers_no_riichi_furiten(self):
        """Riichi player who CAN call ron doesn't get riichi furiten."""
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")

        players = [MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4)]
        players[1].tiles = tiles
        players[1].is_riichi = True

        round_state = _create_round_state(players=players)

        discarded_tile = TilesConverter.string_to_136_array(pin="3")[0]
        # player 1 IS in ron_callers (they can call ron)
        _check_riichi_furiten(round_state, discarded_tile, discarder_seat=0, ron_callers=[1])

        assert players[1].is_riichi_furiten is False

    def test_riichi_player_not_waiting_on_tile_no_furiten(self):
        """Riichi player not waiting on the discarded tile doesn't get riichi furiten."""
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")

        players = [MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4)]
        players[1].tiles = tiles
        players[1].is_riichi = True

        round_state = _create_round_state(players=players)

        # discard 9s, which player 1 is not waiting on
        discarded_tile = TilesConverter.string_to_136_array(sou="9")[0]
        _check_riichi_furiten(round_state, discarded_tile, discarder_seat=0, ron_callers=[])

        assert players[1].is_riichi_furiten is False


class TestRiichiFuritenExplicitPass:
    def test_riichi_player_passes_on_ron_sets_riichi_furiten(self):
        """Riichi player who explicitly passes on a ron prompt gets riichi furiten."""
        # player 1 is in riichi, waiting for 3p
        tiles_p1 = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        tiles_p0 = TilesConverter.string_to_136_array(man="234567", pin="345678", sou="23")

        players = [
            MahjongPlayer(seat=0, name="Player0", tiles=tiles_p0),
            MahjongPlayer(seat=1, name="Player1", tiles=tiles_p1, is_riichi=True),
            MahjongPlayer(seat=2, name="Player2"),
            MahjongPlayer(seat=3, name="Player3"),
        ]
        game_state = _create_game_state(players=players)
        round_state = game_state.round_state

        # player 0 discards 3p (player 1 is waiting on)
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
        assert players[1].is_riichi_furiten is True

    def test_non_riichi_player_passes_no_riichi_furiten(self):
        """Non-riichi player who passes on ron gets temporary furiten but not riichi furiten."""
        tiles_p1 = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        tiles_p0 = TilesConverter.string_to_136_array(man="234567", pin="345678", sou="23")

        players = [
            MahjongPlayer(seat=0, name="Player0", tiles=tiles_p0),
            MahjongPlayer(seat=1, name="Player1", tiles=tiles_p1, is_riichi=False),
            MahjongPlayer(seat=2, name="Player2"),
            MahjongPlayer(seat=3, name="Player3"),
        ]
        game_state = _create_game_state(players=players)
        round_state = game_state.round_state

        tile_3p = next(t for t in tiles_p0 if t // 4 == 11)
        discard_tile(round_state, 0, tile_3p)

        # set up pending ron prompt for seat 1
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=tile_3p,
            from_seat=0,
            pending_seats={1},
            callers=[1],
        )

        handle_pass(round_state, game_state, seat=1)

        assert players[1].is_temporary_furiten is True
        assert players[1].is_riichi_furiten is False


class TestRiichiFuritenBlocksRon:
    def test_riichi_furiten_blocks_ron_permanently(self):
        """Player with riichi furiten cannot call ron on any future tile."""
        # 123m 456m 789m 12p 55p - waiting for 3p
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=1, name="Player1", tiles=tiles, is_riichi=True, is_riichi_furiten=True)
        round_state = _create_round_state()

        discarded_tile = TilesConverter.string_to_136_array(pin="3")[0]
        assert can_call_ron(player, discarded_tile, round_state) is False

    def test_riichi_furiten_persists_through_turns(self):
        """Riichi furiten is not cleared by discards (unlike temporary furiten)."""
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = MahjongPlayer(seat=1, name="Player1", tiles=tiles, is_riichi=True, is_riichi_furiten=True)
        round_state = _create_round_state(
            players=[MahjongPlayer(seat=0, name="Player0")]
            + [player]
            + [MahjongPlayer(seat=i, name=f"Player{i}") for i in range(2, 4)],
        )

        # discard a tile (normally clears temporary furiten)
        tile_to_discard = tiles[0]
        discard_tile(round_state, 1, tile_to_discard)

        # riichi furiten persists
        assert player.is_riichi_furiten is True
        # temporary furiten is cleared by discard
        assert player.is_temporary_furiten is False


class TestRiichiFuritenAllowsTsumo:
    def test_riichi_furiten_allows_tsumo(self):
        """Player with riichi furiten can still win by tsumo."""
        # winning hand: 123m 456m 789m 123p 55p (14 tiles)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = MahjongPlayer(seat=0, name="Player0", tiles=tiles, is_riichi=True, is_riichi_furiten=True)
        round_state = _create_round_state()

        assert can_declare_tsumo(player, round_state) is True


class TestRiichiFuritenResetsOnNewRound:
    def test_resets_on_new_round(self):
        """Riichi furiten resets at the start of a new round."""
        players = [MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4)]
        players[1].is_riichi_furiten = True
        round_state = _create_round_state(players=players)

        _reset_players(round_state)

        assert players[1].is_riichi_furiten is False


class TestRiichiFuritenChankanPass:
    def test_chankan_pass_sets_riichi_furiten_for_riichi_player(self):
        """Passing on chankan sets temporary and riichi furiten for a riichi player."""
        # player 1 is in riichi, waiting for 3p
        tiles_p1 = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        # player 0 has a pon of 3p and a 3p tile in hand for added kan
        pin_3_tiles = TilesConverter.string_to_136_array(pin="3333")
        pon_meld = Meld(
            meld_type=Meld.PON,
            tiles=pin_3_tiles[:3],
            opened=True,
            called_tile=pin_3_tiles[0],
            who=0,
            from_who=1,
        )
        tiles_p0 = [*TilesConverter.string_to_136_array(man="123456789"), pin_3_tiles[3]]

        players = [
            MahjongPlayer(seat=0, name="Player0", tiles=tiles_p0, melds=[pon_meld]),
            MahjongPlayer(seat=1, name="Player1", tiles=tiles_p1, is_riichi=True),
            MahjongPlayer(seat=2, name="Player2"),
            MahjongPlayer(seat=3, name="Player3"),
        ]
        round_state = _create_round_state(players=players)
        # provide dead wall and wall tiles needed for kan draw and replenishment
        round_state.dead_wall = TilesConverter.string_to_136_array(sou="1234567")
        round_state.wall = TilesConverter.string_to_136_array(sou="89")
        game_state = _create_game_state(players=players)

        # seat 0 declares added kan with 3p; seat 1 (riichi) passes on chankan
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.CHANKAN,
            tile_id=pin_3_tiles[3],
            from_seat=0,
            pending_seats={1},
            callers=[1],
        )
        # handle_pass applies furiten and triggers resolution
        handle_pass(round_state, game_state, seat=1)

        assert players[1].is_temporary_furiten is True
        assert players[1].is_riichi_furiten is True

    def test_riichi_furiten_blocks_chankan_ron(self):
        """Player with riichi furiten cannot ron on chankan."""
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        players = [MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4)]
        players[1].tiles = tiles
        players[1].is_riichi = True
        players[1].is_riichi_furiten = True

        round_state = _create_round_state(players=players)

        kan_tile = TilesConverter.string_to_136_array(pin="3")[0]
        chankan_seats = is_chankan_possible(round_state, caller_seat=0, kan_tile=kan_tile)

        assert 1 not in chankan_seats
