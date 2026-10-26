import pytest

from game.logic.action_handlers import handle_chi, handle_kan, handle_pon
from game.logic.call_resolution import resolve_call_prompt
from game.logic.enums import (
    KanType,
    MeldCallType,
    MeldViewType,
    RoundPhase,
)
from game.logic.events import (
    MeldEvent,
    SeatTarget,
    TurnEvent,
)
from game.logic.tiles import tile_to_34
from game.logic.turn import process_discard_phase
from game.logic.types import (
    ChiActionData,
    KanActionData,
    PonActionData,
)
from game.tests.conftest import create_dealt_game_state, create_game_state, create_player, create_round_state
from game.tests.helpers.hands import tile_copies


class TestResolveMeldPriority:
    def test_resolve_call_prompt__when_open_kan_and_chi_declared__should_execute_the_kan(self):
        five_man = tile_copies(0, man="5")[0]
        four_man, six_man = tile_copies(0, man="46")
        players = (
            create_player(seat=0, tiles=tile_copies(0, man="5", pin="123456789", honors="1234")),
            create_player(seat=1, tiles=tile_copies(0, man="46", sou="123456789", honors="56")),
            create_player(seat=2, tiles=tile_copies(1, pin="123456789", honors="1234")),
            create_player(
                seat=3,
                tiles=(*tile_copies(1, man="555"), *tile_copies(1, sou="123456789"), *tile_copies(0, honors="7")),
            ),
        )
        game_state = create_dealt_game_state(players)
        prompted, _events = process_discard_phase(game_state, five_man)
        prompt = prompted.round_state.pending_call_prompt
        assert prompt is not None
        assert [(c.seat, [m.call_type for m in c.melds]) for c in prompt.callers] == [
            (3, [MeldCallType.OPEN_KAN, MeldCallType.PON]),
            (1, [MeldCallType.CHI]),
        ]

        chi = handle_chi(prompted, seat=1, data=ChiActionData(tile_id=five_man, sequence_tiles=(four_man, six_man)))
        kan = handle_kan(chi.state, seat=3, data=KanActionData(tile_id=five_man, kan_type=KanType.OPEN))
        melds = [e for e in kan.events if isinstance(e, MeldEvent)]
        assert [(e.caller_seat, e.meld_type) for e in melds] == [(3, MeldViewType.OPEN_KAN)]


class TestResolveWithoutPrompt:
    def test_resolve_call_prompt__when_no_prompt_pending__should_raise_assertion_error(self):
        round_state = create_round_state(phase=RoundPhase.PLAYING)

        with pytest.raises(AssertionError, match="no pending call prompt"):
            resolve_call_prompt(create_game_state(round_state))


class TestResolvePonMeldResponse:
    def test_resolve_call_prompt__when_pon_declared__should_emit_meld_then_turn_event_forbidding_the_called_type(self):
        nine_man = tile_copies(0, man="9")[0]
        players = (
            create_player(seat=0, tiles=tile_copies(0, man="9", pin="123456789", honors="1234")),
            create_player(seat=1, tiles=tile_copies(1, pin="123456789", honors="1234")),
            create_player(
                seat=2,
                tiles=(
                    *tile_copies(1, man="9"),
                    *tile_copies(2, man="9"),
                    *tile_copies(0, sou="123456789", honors="56"),
                ),
            ),
            create_player(seat=3, tiles=(*tile_copies(1, sou="123456789"), *tile_copies(2, honors="1234"))),
        )
        prompted, _events = process_discard_phase(create_dealt_game_state(players), nine_man)
        prompt = prompted.round_state.pending_call_prompt
        assert prompt is not None
        assert [(c.seat, [m.call_type for m in c.melds]) for c in prompt.callers] == [(2, [MeldCallType.PON])]

        result = handle_pon(prompted, seat=2, data=PonActionData(tile_id=nine_man))
        assert [type(e) for e in result.events] == [MeldEvent, TurnEvent]
        meld_event, turn_event = result.events
        assert (meld_event.caller_seat, meld_event.meld_type) == (2, MeldViewType.PON)
        assert turn_event.target == SeatTarget(seat=2)
        assert turn_event.kuikae_tiles == [tile_to_34(nine_man)]
