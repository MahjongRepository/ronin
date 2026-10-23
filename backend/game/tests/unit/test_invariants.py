import pytest

from game.logic.ai_player_controller import AIPlayerController
from game.logic.exceptions import TileOwnershipError
from game.logic.invariants import verify_tile_ownership
from game.logic.mahjong_service import MahjongGameService
from game.logic.meld_wrapper import FrozenMeld
from game.logic.rng import SEED_BYTES
from game.logic.runtime import GameRuntime
from game.logic.state import Discard
from game.logic.state_utils import update_player

FIXED_SEED = "ab" * SEED_BYTES


def _started_game():
    return MahjongGameService().start_game("game", ["A", "B", "C", "D"], seed=FIXED_SEED).runtime.state


def _with_pon(game_state, *, caller: int, discarder: int):
    round_state = game_state.round_state
    hand = round_state.players[caller].tiles
    called = round_state.players[discarder].tiles[0]
    pon = FrozenMeld(
        tiles=(*hand[:2], called),
        meld_type=FrozenMeld.PON,
        opened=True,
        called_tile=called,
        who=caller,
        from_who=discarder,
    )
    round_state = update_player(round_state, caller, tiles=hand[2:], melds=(pon,))
    discarder_player = round_state.players[discarder]
    round_state = update_player(
        round_state,
        discarder,
        tiles=discarder_player.tiles[1:],
        discards=(Discard(tile_id=called),),
    )
    return game_state.model_copy(update={"round_state": round_state})


class TestVerifyTileOwnership:
    def test_verify_tile_ownership__when_game_just_started__should_pass(self):
        verify_tile_ownership(_started_game())

    def test_verify_tile_ownership__when_a_claimed_discard_sits_in_a_meld__should_count_it_once(self):
        verify_tile_ownership(_with_pon(_started_game(), caller=1, discarder=0))

    def test_verify_tile_ownership__when_a_hand_repeats_a_wall_tile__should_name_the_duplicate_and_the_missing(self):
        game_state = _started_game()
        round_state = game_state.round_state
        player = round_state.players[0]
        stolen = round_state.wall.live_tiles[0]
        round_state = update_player(round_state, 0, tiles=(*player.tiles[:-1], stolen))

        with pytest.raises(TileOwnershipError, match=rf"duplicated=\[{stolen}\] missing=\[{player.tiles[-1]}\]"):
            verify_tile_ownership(game_state.model_copy(update={"round_state": round_state}))

    def test_verify_tile_ownership__when_a_meld_claims_a_tile_it_does_not_contain__should_raise(self):
        game_state = _with_pon(_started_game(), caller=1, discarder=0)
        round_state = game_state.round_state
        pon = round_state.players[1].melds[0]
        foreign = round_state.players[2].tiles[0]
        round_state = update_player(round_state, 1, melds=(pon.model_copy(update={"called_tile": foreign}),))
        round_state = update_player(round_state, 0, discards=(Discard(tile_id=foreign),))

        with pytest.raises(TileOwnershipError, match="does not contain"):
            verify_tile_ownership(game_state.model_copy(update={"round_state": round_state}))

    def test_verify_tile_ownership__when_a_meld_claims_a_tile_never_discarded__should_raise(self):
        game_state = _with_pon(_started_game(), caller=1, discarder=0)
        round_state = game_state.round_state
        round_state = update_player(round_state, 0, discards=())

        with pytest.raises(TileOwnershipError, match="never discarded"):
            verify_tile_ownership(game_state.model_copy(update={"round_state": round_state}))


class TestGameRuntimeCommit:
    def test_commit__when_state_breaks_ownership__should_raise_and_keep_the_old_state(self):
        game_state = _started_game()
        runtime = GameRuntime(game_id="game", state=game_state, ai=AIPlayerController({}))
        round_state = game_state.round_state
        broken = game_state.model_copy(
            update={"round_state": update_player(round_state, 0, tiles=round_state.players[1].tiles)},
        )

        with pytest.raises(TileOwnershipError):
            runtime.commit(broken)
        assert runtime.state is game_state
