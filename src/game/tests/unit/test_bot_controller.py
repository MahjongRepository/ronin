"""
Unit tests for BotController.
"""

import pytest

from game.logic.bot import BotPlayer, BotStrategy
from game.logic.bot_controller import BotController
from game.logic.state import MahjongGameState, MahjongPlayer, MahjongRoundState, RoundPhase
from game.messaging.events import DrawEvent, convert_events, extract_round_result


class TestBotControllerInit:
    def test_init_with_bots(self):
        """BotController initializes with list of bots."""
        bots = [BotPlayer(), BotPlayer(), BotPlayer()]
        controller = BotController(bots)

        assert controller._bots == bots

    def test_init_with_empty_list(self):
        """BotController can be initialized with empty list."""
        controller = BotController([])

        assert controller._bots == []


class TestBotControllerGetBot:
    def test_get_bot_for_valid_seat(self):
        """_get_bot returns correct bot for valid seat."""
        bots = [BotPlayer(), BotPlayer(), BotPlayer()]
        controller = BotController(bots)

        assert controller._get_bot(1) == bots[0]
        assert controller._get_bot(2) == bots[1]
        assert controller._get_bot(3) == bots[2]

    def test_get_bot_for_seat_zero(self):
        """_get_bot returns None for seat 0 (human seat)."""
        bots = [BotPlayer(), BotPlayer(), BotPlayer()]
        controller = BotController(bots)

        assert controller._get_bot(0) is None

    def test_get_bot_for_invalid_seat(self):
        """_get_bot returns None for invalid seat."""
        bots = [BotPlayer(), BotPlayer(), BotPlayer()]
        controller = BotController(bots)

        assert controller._get_bot(4) is None
        assert controller._get_bot(-1) is None


class TestBotControllerHasHumanCaller:
    def _create_round_state(self, bot_seats: list[int]) -> MahjongRoundState:
        """Create round state with specified bot seats."""
        players = []
        for seat in range(4):
            is_bot = seat in bot_seats
            players.append(
                MahjongPlayer(
                    seat=seat,
                    name=f"Bot{seat}" if is_bot else f"Human{seat}",
                    is_bot=is_bot,
                )
            )
        return MahjongRoundState(players=players, wall=list(range(10)))

    def test_has_human_caller_with_human_in_callers(self):
        """has_human_caller returns True when human can call."""
        bots = [BotPlayer(), BotPlayer(), BotPlayer()]
        controller = BotController(bots)
        round_state = self._create_round_state([1, 2, 3])  # seat 0 is human

        events = [
            {
                "event": "call_prompt",
                "data": {"call_type": "pon", "callers": [0, 1]},
            }
        ]

        assert controller.has_human_caller(round_state, events) is True

    def test_has_human_caller_with_only_bots(self):
        """has_human_caller returns False when only bots can call."""
        bots = [BotPlayer(), BotPlayer(), BotPlayer()]
        controller = BotController(bots)
        round_state = self._create_round_state([1, 2, 3])  # seat 0 is human

        events = [
            {
                "event": "call_prompt",
                "data": {"call_type": "pon", "callers": [1, 2]},
            }
        ]

        assert controller.has_human_caller(round_state, events) is False

    def test_has_human_caller_with_dict_callers(self):
        """has_human_caller handles dict-format callers."""
        bots = [BotPlayer(), BotPlayer(), BotPlayer()]
        controller = BotController(bots)
        round_state = self._create_round_state([1, 2, 3])

        events = [
            {
                "event": "call_prompt",
                "data": {"call_type": "chi", "callers": [{"seat": 0, "options": [(4, 8)]}]},
            }
        ]

        assert controller.has_human_caller(round_state, events) is True

    def test_has_human_caller_no_call_prompts(self):
        """has_human_caller returns False when no call prompts exist."""
        bots = [BotPlayer(), BotPlayer(), BotPlayer()]
        controller = BotController(bots)
        round_state = self._create_round_state([1, 2, 3])

        events = [
            {"event": "discard", "data": {"seat": 0}},
        ]

        assert controller.has_human_caller(round_state, events) is False


class TestBotControllerParseCallerInfo:
    def test_parse_caller_info_int(self):
        """_parse_caller_info handles integer seat."""
        controller = BotController([])

        seat, options = controller._parse_caller_info(2)

        assert seat == 2
        assert options is None

    def test_parse_caller_info_dict(self):
        """_parse_caller_info handles dict with seat and options."""
        controller = BotController([])

        seat, options = controller._parse_caller_info({"seat": 1, "options": [(4, 8)]})

        assert seat == 1
        assert options == [(4, 8)]

    def test_parse_caller_info_dict_without_options(self):
        """_parse_caller_info handles dict without options."""
        controller = BotController([])

        seat, options = controller._parse_caller_info({"seat": 3})

        assert seat == 3
        assert options is None


class TestBotControllerEvaluateBotCalls:
    def _create_round_state(self) -> MahjongRoundState:
        """Create round state for testing."""
        players = [
            MahjongPlayer(seat=0, name="Human", is_bot=False, tiles=[]),
            MahjongPlayer(seat=1, name="Bot1", is_bot=True, tiles=[]),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True, tiles=[]),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True, tiles=[]),
        ]
        return MahjongRoundState(players=players, wall=list(range(10)))

    def test_evaluate_bot_calls_skips_humans(self):
        """_evaluate_bot_calls ignores human callers."""
        bots = [BotPlayer(), BotPlayer(), BotPlayer()]
        controller = BotController(bots)
        round_state = self._create_round_state()

        ron_callers, meld_caller, meld_type, sequence_tiles = controller._evaluate_bot_calls(
            round_state, callers=[0], call_type="ron", tile_id=0
        )

        assert ron_callers == []
        assert meld_caller is None
        assert meld_type is None
        assert sequence_tiles is None


class TestConvertEvents:
    def testconvert_events_handles_typed_events(self):
        """convert_events converts typed events to dict format."""
        events = [DrawEvent(seat=0, tile_id=0, tile="1m", target="seat_0")]

        result = convert_events(events)

        assert len(result) == 1
        assert result[0]["event"] == "draw"
        assert result[0]["data"]["seat"] == 0
        assert result[0]["target"] == "seat_0"


class TestExtractRoundResult:
    def testextract_round_result_finds_result(self):
        """extract_round_result extracts result from round_end event."""
        events = [
            {"event": "draw", "data": {}},
            {"event": "round_end", "data": {"result": {"type": "tsumo", "winner": 0}}},
        ]

        result = extract_round_result(events)

        assert result == {"type": "tsumo", "winner": 0}

    def testextract_round_result_no_round_end(self):
        """extract_round_result returns None when no round_end event."""
        events = [
            {"event": "draw", "data": {}},
            {"event": "discard", "data": {}},
        ]

        result = extract_round_result(events)

        assert result is None


class TestBotControllerProcessBotTurns:
    def _create_game_state(self, current_seat: int = 1) -> MahjongGameState:
        """Create a minimal game state for testing bot turns."""
        # create a hand that will result in a simple discard (not winning)
        non_winning_hand = [0, 8, 16, 24, 32, 40, 48, 56, 64, 72, 80, 88, 96, 104]

        players = [
            MahjongPlayer(seat=0, name="Human", is_bot=False, tiles=list(non_winning_hand[:13])),
            MahjongPlayer(seat=1, name="Bot1", is_bot=True, tiles=list(non_winning_hand)),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True, tiles=list(non_winning_hand[:13])),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True, tiles=list(non_winning_hand[:13])),
        ]
        round_state = MahjongRoundState(
            players=players,
            wall=list(range(50)),
            dead_wall=list(range(14)),
            dora_indicators=[0],
            current_player_seat=current_seat,
            phase=RoundPhase.PLAYING,
        )
        return MahjongGameState(round_state=round_state)

    @pytest.mark.asyncio
    async def test_process_bot_turns_stops_at_human(self):
        """process_bot_turns stops when reaching human player's turn."""
        bots = [BotPlayer(), BotPlayer(), BotPlayer()]
        controller = BotController(bots)
        game_state = self._create_game_state(current_seat=0)

        events = await controller.process_bot_turns(game_state)

        # should stop immediately since current player is human
        assert events == []

    @pytest.mark.asyncio
    async def test_process_bot_turns_stops_when_round_finished(self):
        """process_bot_turns stops when round is finished."""
        bots = [BotPlayer(), BotPlayer(), BotPlayer()]
        controller = BotController(bots)
        game_state = self._create_game_state(current_seat=1)
        game_state.round_state.phase = RoundPhase.FINISHED

        events = await controller.process_bot_turns(game_state)

        # should stop immediately since round is finished
        assert events == []

    @pytest.mark.asyncio
    async def test_process_bot_turns_returns_empty_for_invalid_bot(self):
        """process_bot_turns returns empty when bot index is invalid."""
        controller = BotController([])  # no bots
        game_state = self._create_game_state(current_seat=1)

        events = await controller.process_bot_turns(game_state)

        assert events == []


class TestBotControllerProcessCallResponses:
    def _create_game_state(self) -> MahjongGameState:
        """Create a minimal game state for testing."""
        players = [
            MahjongPlayer(seat=0, name="Human", is_bot=False, tiles=[]),
            MahjongPlayer(
                seat=1, name="Bot1", is_bot=True, tiles=[0, 1, 4, 8]
            ),  # has tiles for potential pon
            MahjongPlayer(seat=2, name="Bot2", is_bot=True, tiles=[]),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True, tiles=[]),
        ]
        round_state = MahjongRoundState(
            players=players,
            wall=list(range(50)),
            current_player_seat=0,
            phase=RoundPhase.PLAYING,
        )
        return MahjongGameState(round_state=round_state)

    @pytest.mark.asyncio
    async def test_process_call_responses_no_prompts(self):
        """process_call_responses returns empty when no call prompts."""
        bots = [BotPlayer(), BotPlayer(), BotPlayer()]
        controller = BotController(bots)
        game_state = self._create_game_state()

        events = await controller.process_call_responses(game_state, [{"event": "discard"}])

        assert events == []

    @pytest.mark.asyncio
    async def test_process_call_responses_advances_turn_when_no_calls(self):
        """process_call_responses advances turn when bots decline calls."""
        bots = [BotPlayer(strategy=BotStrategy.SIMPLE)] * 3
        controller = BotController(bots)
        game_state = self._create_game_state()
        game_state.round_state.current_player_seat = 0

        # call prompt for meld that simple bot will decline
        events = [
            {
                "event": "call_prompt",
                "data": {
                    "call_type": "meld",
                    "tile_id": 2,
                    "from_seat": 0,
                    "callers": [{"seat": 1, "call_type": "pon"}],
                },
            }
        ]

        await controller.process_call_responses(game_state, events)

        # turn should have advanced
        assert game_state.round_state.current_player_seat == 1
