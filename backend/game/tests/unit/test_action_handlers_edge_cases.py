from game.logic.action_handlers import (
    handle_kan,
    handle_pass,
)
from game.logic.action_result import ActionResult
from game.logic.ai_player_controller import AIPlayerController
from game.logic.enums import (
    AIPlayerType,
    KanType,
    MeldCallType,
    PromptKind,
)
from game.logic.events import DrawEvent, MeldEvent
from game.logic.game import init_game
from game.logic.meld_wrapper import FrozenMeld
from game.logic.round import draw_tile
from game.logic.runtime import GameRuntime
from game.logic.state import (
    Caller,
    MahjongGameState,
    PendingCallPrompt,
)
from game.logic.state_utils import update_player
from game.logic.turn import process_discard_phase
from game.logic.types import (
    KanActionData,
    SeatConfig,
)
from game.tests.conftest import create_dealt_game_state, create_player
from game.tests.helpers.hands import tile_copies
from game.tests.unit.helpers import _update_round_state


def _default_seat_configs() -> list[SeatConfig]:
    return [
        SeatConfig(name="Player"),
        SeatConfig(name="Tsumogiri 1", ai_player_type=AIPlayerType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 2", ai_player_type=AIPlayerType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 3", ai_player_type=AIPlayerType.TSUMOGIRI),
    ]


def _create_frozen_game_state() -> MahjongGameState:
    game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
    new_round_state, _tile = draw_tile(game_state.round_state)
    return game_state.model_copy(update={"round_state": new_round_state})


class TestResolveMeldResponse:
    def test_resolve_meld_response__when_open_kan_with_minimal_live_wall__should_resolve_kan(self):
        five_man = tile_copies(0, man="5")[0]
        players = (
            create_player(seat=0, tiles=tile_copies(0, man="5", pin="123456789", honors="1234")),
            create_player(
                seat=1,
                tiles=(*tile_copies(1, man="555"), *tile_copies(0, sou="123456789"), *tile_copies(0, honors="5")),
            ),
            create_player(seat=2, tiles=tile_copies(1, pin="123456789", honors="1234")),
            create_player(seat=3, tiles=(*tile_copies(1, sou="123456789"), *tile_copies(2, honors="1234"))),
        )
        runtime = GameRuntime(game_id="game", state=create_dealt_game_state(players), ai=AIPlayerController({}))
        wall = runtime.state.round_state.wall
        minimal_live_tiles = wall.live_tiles[: runtime.state.settings.min_wall_for_kan]
        _update_round_state(runtime, wall=wall.model_copy(update={"live_tiles": minimal_live_tiles}))

        prompted, _events = process_discard_phase(runtime.state, five_man)
        prompt = prompted.round_state.pending_call_prompt
        assert prompt is not None
        assert [(c.seat, [m.call_type for m in c.melds]) for c in prompt.callers] == [
            (1, [MeldCallType.OPEN_KAN, MeldCallType.PON]),
        ]

        kan = handle_kan(prompted, seat=1, data=KanActionData(tile_id=five_man, kan_type=KanType.OPEN))
        assert isinstance(kan, ActionResult)
        assert [type(e) for e in kan.events] == [MeldEvent, DrawEvent]
        assert [m.type for m in kan.state.round_state.players[1].melds] == [FrozenMeld.KAN]


class TestChankanRiechiFuritenOnPass:
    def test_chankan_pass__when_riichi_player_passes__should_set_riichi_furiten(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state
        tile_id = round_state.players[0].tiles[0]
        # make seat 1 a riichi player
        round_state = update_player(round_state, 1, is_riichi=True)

        # seat 1 and seat 2 are pending callers; passing as seat 1 won't trigger
        # resolution (seat 2 is still pending), avoiding the added kan completion
        prompt = PendingCallPrompt(
            kind=PromptKind.CHANKAN,
            tile_id=tile_id,
            from_seat=0,
            pending_seats=frozenset({1, 2}),
            callers=(Caller(seat=1, can_ron=True), Caller(seat=2, can_ron=True)),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = handle_pass(game_state, seat=1)
        assert result.state.round_state.players[1].is_riichi_furiten is True
