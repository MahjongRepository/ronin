"""
MahjongGameService implementation for the Mahjong game.

Orchestrates game logic, bot turns, and event generation for the session manager.
"""

from functools import partial
from typing import TYPE_CHECKING, Any

from game.logic.action_handlers import (
    ActionResult,
    complete_added_kan_after_chankan_decline,
    handle_chi,
    handle_discard,
    handle_kan,
    handle_kyuushu,
    handle_pass,
    handle_pon,
    handle_riichi,
    handle_ron,
    handle_tsumo,
)
from game.logic.bot import BotPlayer
from game.logic.bot_controller import BotController
from game.logic.game import check_game_end, finalize_game, init_game, process_round_end
from game.logic.round import init_round
from game.logic.service import GameService
from game.logic.state import MahjongGameState, RoundPhase, get_player_view
from game.logic.turn import process_draw_phase
from game.messaging.events import convert_events, extract_round_result

if TYPE_CHECKING:
    from collections.abc import Awaitable


NUM_PLAYERS = 4


class MahjongGameService(GameService):
    """
    Game service for Mahjong implementing the GameService interface.

    Maintains game states for multiple concurrent games and handles all
    player actions including bot turn automation.
    """

    def __init__(self) -> None:
        self._games: dict[str, MahjongGameState] = {}
        self._bots: dict[str, list[BotPlayer]] = {}
        self._bot_controllers: dict[str, BotController] = {}

    async def start_game(
        self,
        game_id: str,
        player_names: list[str],
    ) -> list[dict[str, Any]]:
        """
        Start a new mahjong game with the given players.

        First player is human, the rest are filled with bots up to 4 players.
        Returns initial state events for each player.
        """
        full_names = self._fill_bot_names(player_names)
        game_state = init_game(full_names)
        self._games[game_id] = game_state

        bots = [BotPlayer() for _ in range(3)]
        self._bots[game_id] = bots
        self._bot_controllers[game_id] = BotController(bots)

        events: list[dict[str, Any]] = []
        events.extend(self._create_game_started_events(game_state))

        draw_events = process_draw_phase(game_state.round_state, game_state)
        events.extend(convert_events(draw_events))

        if game_state.round_state.players[0].is_bot:
            bot_events = await self._process_bot_turns(game_id)
            events.extend(bot_events)

        return events

    def _fill_bot_names(self, player_names: list[str]) -> list[str]:
        """Fill remaining slots with bot names."""
        full_names = list(player_names)
        bot_num = 1
        while len(full_names) < NUM_PLAYERS:
            full_names.append(f"Bot{bot_num}")
            bot_num += 1
        return full_names

    def _create_game_started_events(self, game_state: MahjongGameState) -> list[dict[str, Any]]:
        """Create game_started events for all players."""
        return [
            {"event": "game_started", "data": get_player_view(game_state, seat), "target": f"seat_{seat}"}
            for seat in range(4)
        ]

    async def handle_action(
        self,
        game_id: str,
        player_name: str,
        action: str,
        data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Handle a game action from a player.

        Processes the action and triggers bot turns as needed.
        """
        game_state = self._games.get(game_id)
        if game_state is None:
            return [{"event": "error", "data": {"message": "game not found"}, "target": "all"}]

        seat = self._find_player_seat(game_state, player_name)
        if seat is None:
            return [{"event": "error", "data": {"message": "player not in game"}, "target": "all"}]

        return await self._dispatch_action(game_id, seat, action, data)

    async def _dispatch_action(
        self, game_id: str, seat: int, action: str, data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Dispatch action to appropriate handler."""
        game_state = self._games[game_id]
        round_state = game_state.round_state

        handlers = {
            "discard": lambda: handle_discard(round_state, game_state, seat, data),
            "declare_riichi": lambda: handle_riichi(round_state, game_state, seat, data),
            "declare_tsumo": lambda: handle_tsumo(round_state, game_state, seat),
            "call_ron": lambda: handle_ron(round_state, game_state, seat, data),
            "call_pon": lambda: handle_pon(round_state, game_state, seat, data),
            "call_chi": lambda: handle_chi(round_state, game_state, seat, data),
            "call_kan": lambda: self._handle_kan_action(game_id, seat, data),
            "call_kyuushu": lambda: handle_kyuushu(round_state, game_state, seat),
            "pass": lambda: handle_pass(round_state, game_state, seat),
        }

        handler = handlers.get(action)
        if handler is None:
            return [
                {"event": "error", "data": {"message": f"unknown action: {action}"}, "target": f"seat_{seat}"}
            ]

        result = handler()
        return await self._process_action_result(game_id, result)

    def _handle_kan_action(self, game_id: str, seat: int, data: dict[str, Any]) -> ActionResult:
        """Handle kan action with special post-processing for chankan."""
        game_state = self._games[game_id]
        return handle_kan(game_state.round_state, game_state, seat, data)

    async def _process_action_result(self, game_id: str, result: ActionResult) -> list[dict[str, Any]]:
        """Process action result and handle post-action logic."""
        game_state = self._games[game_id]
        round_state = game_state.round_state
        events = convert_events(result.events)

        if round_state.phase == RoundPhase.FINISHED:
            round_result = extract_round_result(events)
            events.extend(await self._handle_round_end(game_id, round_result))
            return events

        if result.needs_post_discard:
            return await self._process_post_discard(game_id, events)

        # check for chankan prompt
        chankan_prompt = self._find_chankan_prompt(events)
        if chankan_prompt:
            return await self._handle_chankan_prompt(game_id, events, chankan_prompt)

        # process bot turns if needed
        if round_state.phase == RoundPhase.PLAYING:
            current_player = round_state.players[round_state.current_player_seat]
            if current_player.is_bot:
                bot_events = await self._process_bot_turns(game_id)
                events.extend(bot_events)

        return events

    def _find_chankan_prompt(self, events: list[dict[str, Any]]) -> dict | None:
        """Find a chankan call prompt in events."""
        return next(
            (
                e
                for e in events
                if e.get("event") == "call_prompt" and e.get("data", {}).get("call_type") == "chankan"
            ),
            None,
        )

    async def _handle_chankan_prompt(
        self, game_id: str, events: list[dict[str, Any]], chankan_prompt: dict
    ) -> list[dict[str, Any]]:
        """Handle chankan prompt: wait for human or process bot response."""
        game_state = self._games[game_id]
        round_state = game_state.round_state
        bot_controller = self._bot_controllers[game_id]

        if bot_controller.has_human_caller(round_state, events):
            return events

        bot_responses = await bot_controller.process_call_responses(
            game_state, events, partial(self._round_end_callback, game_id)
        )
        events.extend(bot_responses)

        if round_state.phase == RoundPhase.FINISHED:
            result = extract_round_result(events)
            events.extend(await self._handle_round_end(game_id, result))
            return events

        # chankan was declined, complete the added kan
        prompt_data = chankan_prompt.get("data", {})
        kan_tile_id = prompt_data.get("tile_id")
        kan_caller_seat = prompt_data.get("from_seat")
        if kan_tile_id is not None and kan_caller_seat is not None:
            kan_events = complete_added_kan_after_chankan_decline(
                round_state, game_state, kan_caller_seat, kan_tile_id
            )
            events.extend(convert_events(kan_events))

            # check if four-kans abortive draw occurred
            if round_state.phase == RoundPhase.FINISHED:
                result = extract_round_result(events)
                events.extend(await self._handle_round_end(game_id, result))
                return events

        return events

    def _find_player_seat(self, game_state: MahjongGameState, player_name: str) -> int | None:
        """Find the seat number for a player by name."""
        for player in game_state.round_state.players:
            if player.name == player_name:
                return player.seat
        return None

    async def _process_post_discard(self, game_id: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Process events after a discard (check round end, call prompts, bot turns)."""
        game_state = self._games[game_id]
        round_state = game_state.round_state
        bot_controller = self._bot_controllers[game_id]

        if round_state.phase == RoundPhase.FINISHED:
            result = extract_round_result(events)
            events.extend(await self._handle_round_end(game_id, result))
            return events

        has_call_prompt = any(e.get("event") == "call_prompt" for e in events)
        if has_call_prompt:
            if bot_controller.has_human_caller(round_state, events):
                return events

            bot_responses = await bot_controller.process_call_responses(
                game_state, events, partial(self._round_end_callback, game_id)
            )
            events.extend(bot_responses)

            if round_state.phase == RoundPhase.FINISHED:
                result = extract_round_result(events)
                events.extend(await self._handle_round_end(game_id, result))
                return events

        # draw for next player
        if round_state.phase == RoundPhase.PLAYING:
            draw_events = process_draw_phase(round_state, game_state)
            events.extend(convert_events(draw_events))

            if round_state.phase == RoundPhase.FINISHED:
                result = extract_round_result(events)
                events.extend(await self._handle_round_end(game_id, result))
                return events

        # process bot turns if next player is a bot
        if round_state.phase == RoundPhase.PLAYING:
            current_player = round_state.players[round_state.current_player_seat]
            if current_player.is_bot:
                bot_events = await self._process_bot_turns(game_id)
                events.extend(bot_events)

        return events

    async def _handle_round_end(self, game_id: str, round_result: dict | None = None) -> list[dict[str, Any]]:
        """Handle the end of a round and start next round or end game."""
        game_state = self._games[game_id]

        result = round_result if round_result else {"type": "unknown"}
        process_round_end(game_state, result)

        if check_game_end(game_state):
            game_result = finalize_game(game_state)
            self._cleanup_game(game_id)
            return [{"event": "game_end", "data": game_result, "target": "all"}]

        return await self._start_next_round(game_id)

    def _cleanup_game(self, game_id: str) -> None:
        """Clean up game state after game ends."""
        self._games.pop(game_id, None)
        self._bots.pop(game_id, None)
        self._bot_controllers.pop(game_id, None)

    async def _start_next_round(self, game_id: str) -> list[dict[str, Any]]:
        """Start the next round and return events."""
        game_state = self._games[game_id]
        init_round(game_state)

        events: list[dict[str, Any]] = [
            {"event": "round_started", "data": get_player_view(game_state, seat), "target": f"seat_{seat}"}
            for seat in range(4)
        ]

        round_state = game_state.round_state
        draw_events = process_draw_phase(round_state, game_state)
        events.extend(convert_events(draw_events))

        dealer_seat = round_state.dealer_seat
        if round_state.players[dealer_seat].is_bot:
            bot_events = await self._process_bot_turns(game_id)
            events.extend(bot_events)

        return events

    def _round_end_callback(self, game_id: str, result: dict | None) -> Awaitable[list[dict[str, Any]]]:
        """Handle round end and return events."""
        return self._handle_round_end(game_id, result)

    async def _process_bot_turns(self, game_id: str) -> list[dict[str, Any]]:
        """Process bot turns using BotController."""
        game_state = self._games.get(game_id)
        if game_state is None:
            return []

        bot_controller = self._bot_controllers.get(game_id)
        if bot_controller is None:
            return []

        return await bot_controller.process_bot_turns(game_state, partial(self._round_end_callback, game_id))
