"""
Unit tests for BotController.
"""

import pytest
from mahjong.tile import TilesConverter

from game.logic.bot import BotPlayer, BotStrategy
from game.logic.bot_controller import BotController
from game.logic.enums import CallType, MeldCallType
from game.logic.state import MahjongGameState, MahjongPlayer, MahjongRoundState, RoundPhase
from game.logic.types import HandResultInfo, MeldCaller, TsumoResult
from game.messaging.events import (
    CallPromptEvent,
    DrawEvent,
    RoundEndEvent,
    ServiceEvent,
    convert_events,
    extract_round_result,
)
from game.tests.unit.helpers import _string_to_34_tile, _string_to_136_tile


class TestBotControllerInit:
    def test_init_with_bots(self):
        """BotController initializes with dict of bots."""
        bots = {1: BotPlayer(), 2: BotPlayer(), 3: BotPlayer()}
        controller = BotController(bots)

        assert controller._bots == bots

    def test_init_with_empty_dict(self):
        """BotController can be initialized with empty dict."""
        controller = BotController({})

        assert controller._bots == {}


class TestBotControllerGetBot:
    def test_get_bot_for_valid_seat(self):
        """_get_bot returns correct bot for valid seat."""
        bot1, bot2, bot3 = BotPlayer(), BotPlayer(), BotPlayer()
        bots = {1: bot1, 2: bot2, 3: bot3}
        controller = BotController(bots)

        assert controller._get_bot(1) is bot1
        assert controller._get_bot(2) is bot2
        assert controller._get_bot(3) is bot3

    def test_get_bot_for_non_bot_seat(self):
        """_get_bot returns None for seat without a bot."""
        bots = {1: BotPlayer(), 2: BotPlayer(), 3: BotPlayer()}
        controller = BotController(bots)

        assert controller._get_bot(0) is None

    def test_get_bot_for_invalid_seat(self):
        """_get_bot returns None for invalid seat."""
        bots = {1: BotPlayer(), 2: BotPlayer(), 3: BotPlayer()}
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
        bots = {1: BotPlayer(), 2: BotPlayer(), 3: BotPlayer()}
        controller = BotController(bots)
        round_state = self._create_round_state([1, 2, 3])  # seat 0 is human

        events = [
            ServiceEvent(
                event="call_prompt",
                data=CallPromptEvent(
                    call_type=CallType.MELD,
                    tile_id=_string_to_136_tile(man="1"),
                    from_seat=0,
                    callers=[0, 1],
                    target="all",
                ),
            )
        ]

        assert controller.has_human_caller(round_state, events) is True

    def test_has_human_caller_with_only_bots(self):
        """has_human_caller returns False when only bots can call."""
        bots = {1: BotPlayer(), 2: BotPlayer(), 3: BotPlayer()}
        controller = BotController(bots)
        round_state = self._create_round_state([1, 2, 3])  # seat 0 is human

        events = [
            ServiceEvent(
                event="call_prompt",
                data=CallPromptEvent(
                    call_type=CallType.MELD,
                    tile_id=_string_to_136_tile(man="1"),
                    from_seat=0,
                    callers=[1, 2],
                    target="all",
                ),
            )
        ]

        assert controller.has_human_caller(round_state, events) is False

    def test_has_human_caller_with_meld_caller_models(self):
        """has_human_caller handles MeldCaller callers."""
        bots = {1: BotPlayer(), 2: BotPlayer(), 3: BotPlayer()}
        controller = BotController(bots)
        round_state = self._create_round_state([1, 2, 3])

        events = [
            ServiceEvent(
                event="call_prompt",
                data=CallPromptEvent(
                    call_type=CallType.MELD,
                    tile_id=_string_to_136_tile(man="1"),
                    from_seat=0,
                    callers=[
                        MeldCaller(
                            seat=0,
                            call_type=MeldCallType.CHI,
                            tile_34=_string_to_34_tile(man="6"),
                            priority=2,
                            options=[(_string_to_136_tile(man="2"), _string_to_136_tile(man="3"))],
                        )
                    ],
                    target="all",
                ),
            )
        ]

        assert controller.has_human_caller(round_state, events) is True

    def test_has_human_caller_no_call_prompts(self):
        """has_human_caller returns False when no call prompts exist."""
        bots = {1: BotPlayer(), 2: BotPlayer(), 3: BotPlayer()}
        controller = BotController(bots)
        round_state = self._create_round_state([1, 2, 3])

        events = [
            ServiceEvent(
                event="discard",
                data=DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), tile="1m", target="seat_0"),
            ),
        ]

        assert controller.has_human_caller(round_state, events) is False


class TestBotControllerParseCallerInfo:
    def test_parse_caller_info_int(self):
        """_parse_caller_info handles integer seat."""
        controller = BotController({})

        seat, options = controller._parse_caller_info(2)

        assert seat == 2
        assert options is None

    def test_parse_caller_info_meld_caller(self):
        """_parse_caller_info handles MeldCaller with seat and options."""
        controller = BotController({})

        caller = MeldCaller(
            seat=1,
            call_type=MeldCallType.CHI,
            tile_34=_string_to_34_tile(man="6"),
            priority=2,
            options=[(_string_to_136_tile(man="2"), _string_to_136_tile(man="3"))],
        )
        seat, options = controller._parse_caller_info(caller)

        assert seat == 1
        assert options == [(_string_to_136_tile(man="2"), _string_to_136_tile(man="3"))]

    def test_parse_caller_info_meld_caller_without_options(self):
        """_parse_caller_info handles MeldCaller without options."""
        controller = BotController({})

        caller = MeldCaller(
            seat=3, call_type=MeldCallType.PON, tile_34=_string_to_34_tile(man="6"), priority=1
        )
        seat, options = controller._parse_caller_info(caller)

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
        bots = {1: BotPlayer(), 2: BotPlayer(), 3: BotPlayer()}
        controller = BotController(bots)
        round_state = self._create_round_state()

        ron_callers, meld_caller, meld_type, sequence_tiles = controller._evaluate_bot_calls(
            round_state, callers=[0], call_type="ron", tile_id=_string_to_136_tile(man="1")
        )

        assert ron_callers == []
        assert meld_caller is None
        assert meld_type is None
        assert sequence_tiles is None


class TestConvertEvents:
    def test_convert_events_handles_typed_events(self):
        """convert_events converts typed events to ServiceEvent format."""
        events = [DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), tile="1m", target="seat_0")]

        result = convert_events(events)

        assert len(result) == 1
        assert isinstance(result[0], ServiceEvent)
        assert result[0].event == "draw"
        assert isinstance(result[0].data, DrawEvent)
        assert result[0].data.seat == 0
        assert result[0].target == "seat_0"


class TestExtractRoundResult:
    def test_extract_round_result_finds_result(self):
        """extract_round_result extracts result from round_end event."""
        tsumo_result = TsumoResult(
            winner_seat=0,
            hand_result=HandResultInfo(han=1, fu=30, yaku=["tanyao"]),
            score_changes={0: 1000},
            riichi_sticks_collected=0,
        )
        events = [
            ServiceEvent(
                event="draw",
                data=DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), tile="1m", target="seat_0"),
            ),
            ServiceEvent(event="round_end", data=RoundEndEvent(result=tsumo_result, target="all")),
        ]

        result = extract_round_result(events)

        assert result is not None
        assert isinstance(result, TsumoResult)
        assert result.type == "tsumo"
        assert result.winner_seat == 0

    def test_extract_round_result_no_round_end(self):
        """extract_round_result returns None when no round_end event."""
        events = [
            ServiceEvent(
                event="draw",
                data=DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), tile="1m", target="seat_0"),
            ),
            ServiceEvent(
                event="discard",
                data=DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), tile="1m", target="seat_0"),
            ),
        ]

        result = extract_round_result(events)

        assert result is None


class TestBotControllerProcessBotTurns:
    def _create_game_state(self, current_seat: int = 1) -> MahjongGameState:
        """Create a minimal game state for testing bot turns."""
        # create a hand that will result in a simple discard (not winning)
        non_winning_hand = TilesConverter.string_to_136_array(man="13579", pin="2468", sou="13579")

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
            dora_indicators=TilesConverter.string_to_136_array(man="1"),
            current_player_seat=current_seat,
            phase=RoundPhase.PLAYING,
        )
        return MahjongGameState(round_state=round_state)

    @pytest.mark.asyncio
    async def test_process_bot_turns_stops_at_human(self):
        """process_bot_turns stops when reaching human player's turn."""
        bots = {1: BotPlayer(), 2: BotPlayer(), 3: BotPlayer()}
        controller = BotController(bots)
        game_state = self._create_game_state(current_seat=0)

        events = await controller.process_bot_turns(game_state)

        # should stop immediately since current player is human
        assert events == []

    @pytest.mark.asyncio
    async def test_process_bot_turns_stops_when_round_finished(self):
        """process_bot_turns stops when round is finished."""
        bots = {1: BotPlayer(), 2: BotPlayer(), 3: BotPlayer()}
        controller = BotController(bots)
        game_state = self._create_game_state(current_seat=1)
        game_state.round_state.phase = RoundPhase.FINISHED

        events = await controller.process_bot_turns(game_state)

        # should stop immediately since round is finished
        assert events == []

    @pytest.mark.asyncio
    async def test_process_bot_turns_returns_empty_for_invalid_bot(self):
        """process_bot_turns returns empty when bot index is invalid."""
        controller = BotController({})  # no bots
        game_state = self._create_game_state(current_seat=1)

        events = await controller.process_bot_turns(game_state)

        assert events == []


class TestBotControllerProcessCallResponses:
    def _create_game_state(self) -> MahjongGameState:
        """Create a minimal game state for testing."""
        players = [
            MahjongPlayer(seat=0, name="Human", is_bot=False, tiles=[]),
            MahjongPlayer(
                seat=1,
                name="Bot1",
                is_bot=True,
                tiles=TilesConverter.string_to_136_array(man="1123"),
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
        bots = {1: BotPlayer(), 2: BotPlayer(), 3: BotPlayer()}
        controller = BotController(bots)
        game_state = self._create_game_state()

        events = await controller.process_call_responses(
            game_state,
            [
                ServiceEvent(
                    event="discard",
                    data=DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), tile="1m", target="seat_0"),
                )
            ],
        )

        assert events == []

    @pytest.mark.asyncio
    async def test_process_call_responses_advances_turn_when_no_calls(self):
        """process_call_responses advances turn when bots decline calls."""
        bots = {
            1: BotPlayer(strategy=BotStrategy.TSUMOGIRI),
            2: BotPlayer(strategy=BotStrategy.TSUMOGIRI),
            3: BotPlayer(strategy=BotStrategy.TSUMOGIRI),
        }
        controller = BotController(bots)
        game_state = self._create_game_state()
        game_state.round_state.current_player_seat = 0

        # call prompt for meld that simple bot will decline
        events = [
            ServiceEvent(
                event="call_prompt",
                data=CallPromptEvent(
                    call_type="meld",
                    tile_id=TilesConverter.string_to_136_array(man="111")[2],
                    from_seat=0,
                    callers=[
                        MeldCaller(
                            seat=1,
                            call_type=MeldCallType.PON,
                            tile_34=_string_to_34_tile(man="1"),
                            priority=1,
                        )
                    ],
                    target="all",
                ),
            )
        ]

        await controller.process_call_responses(game_state, events)

        # turn should have advanced
        assert game_state.round_state.current_player_seat == 1
