"""
MahjongGameService implementation for the Mahjong game.

Orchestrates game logic, bot turns, and event generation for the session manager.
"""

from typing import Any

from game.logic.abortive import (
    AbortiveDrawType,
    call_kyuushu_kyuuhai,
    can_call_kyuushu_kyuuhai,
    check_four_kans,
    process_abortive_draw,
)
from game.logic.bot import (
    BotPlayer,
    get_bot_action,
    should_call_chi,
    should_call_kan,
    should_call_pon,
    should_call_ron,
)
from game.logic.game import (
    check_game_end,
    finalize_game,
    init_game,
    process_round_end,
)
from game.logic.melds import call_added_kan
from game.logic.round import init_round
from game.logic.service import GameService
from game.logic.state import (
    MahjongGameState,
    MahjongRoundState,
    RoundPhase,
    get_player_view,
)
from game.logic.tiles import tile_to_string
from game.logic.turn import (
    get_available_actions,
    process_discard_phase,
    process_draw_phase,
    process_meld_call,
    process_ron_call,
    process_tsumo_call,
)


def _format_available_actions(actions_dict: dict) -> list[dict]:
    """
    Convert available actions dict to list format expected by client.

    Input format (from get_available_actions):
        {"discard_tiles": [...], "can_riichi": bool, "can_tsumo": bool, ...}

    Output format (AvailableAction list):
        [{"action": "discard", "tiles": [...]}, {"action": "riichi"}, ...]
    """
    result = []

    if actions_dict.get("discard_tiles"):
        result.append({"action": "discard", "tiles": actions_dict["discard_tiles"]})

    if actions_dict.get("can_riichi"):
        result.append({"action": "riichi"})

    if actions_dict.get("can_tsumo"):
        result.append({"action": "tsumo"})

    if actions_dict.get("closed_kans"):
        result.append({"action": "kan", "tiles": actions_dict["closed_kans"]})

    if actions_dict.get("added_kans"):
        result.append({"action": "added_kan", "tiles": actions_dict["added_kans"]})

    return result


def _convert_events(raw_events: list[dict]) -> list[dict[str, Any]]:
    """Convert internal events to service events with event/data/target structure."""
    result = []
    for event in raw_events:
        data = event.copy()
        # convert available_actions dict to list format for turn events
        if event.get("type") == "turn" and isinstance(event.get("available_actions"), dict):
            data["available_actions"] = _format_available_actions(event["available_actions"])
        result.append(
            {
                "event": event["type"],
                "data": data,
                "target": event.get("target", "all"),
            }
        )
    return result


def _extract_round_result(events: list[dict[str, Any]]) -> dict | None:
    """Extract the round result from a list of events."""
    for event in events:
        if event.get("event") == "round_end":
            data = event.get("data", {})
            return data.get("result", data)
    return None


def _get_bot_meld_response(
    bot: BotPlayer,
    player,  # noqa: ANN001
    call_info: tuple[str | None, list | None],
    tile_id: int,
    round_state: MahjongRoundState,
) -> str | None:
    """Check bot's meld response. Returns meld type or None."""
    meld_call_type, caller_options = call_info
    if meld_call_type == "pon" and should_call_pon(bot, player, tile_id, round_state):
        return "pon"
    if meld_call_type == "chi" and should_call_chi(bot, player, tile_id, caller_options or [], round_state):
        return "chi"
    if meld_call_type == "open_kan" and should_call_kan(bot, player, "open", tile_id, round_state):
        return "open_kan"
    return None


class MahjongGameService(GameService):
    """
    Game service for Mahjong implementing the GameService interface.

    Maintains game states for multiple concurrent games and handles all
    player actions including bot turn automation.
    """

    def __init__(self) -> None:
        self._games: dict[str, MahjongGameState] = {}
        self._bots: dict[str, list[BotPlayer]] = {}

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
        self._bots[game_id] = [BotPlayer() for _ in range(3)]

        events: list[dict[str, Any]] = []
        events.extend(self._create_game_started_events(game_state))

        draw_events = process_draw_phase(game_state.round_state, game_state)
        events.extend(_convert_events(draw_events))

        if game_state.round_state.players[0].is_bot:
            bot_events = await self._process_bot_turns(game_id)
            events.extend(bot_events)

        return events

    def _fill_bot_names(self, player_names: list[str]) -> list[str]:
        """Fill remaining slots with bot names."""
        full_names = list(player_names)
        bot_num = 1
        while len(full_names) < 4:
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
        handlers = {
            "discard": lambda: self._handle_discard(game_id, seat, data),
            "declare_riichi": lambda: self._handle_riichi(game_id, seat, data),
            "declare_tsumo": lambda: self._handle_tsumo(game_id, seat),
            "call_ron": lambda: self._handle_ron(game_id, seat, data),
            "call_pon": lambda: self._handle_pon(game_id, seat, data),
            "call_chi": lambda: self._handle_chi(game_id, seat, data),
            "call_kan": lambda: self._handle_kan(game_id, seat, data),
            "call_kyuushu": lambda: self._handle_kyuushu(game_id, seat),
            "pass": lambda: self._handle_pass(game_id, seat),
        }

        handler = handlers.get(action)
        if handler is None:
            return [
                {"event": "error", "data": {"message": f"unknown action: {action}"}, "target": f"seat_{seat}"}
            ]

        return await handler()

    def _find_player_seat(self, game_state: MahjongGameState, player_name: str) -> int | None:
        """Find the seat number for a player by name."""
        for player in game_state.round_state.players:
            if player.name == player_name:
                return player.seat
        return None

    async def _handle_discard(self, game_id: str, seat: int, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Handle a discard action."""
        game_state = self._games[game_id]
        round_state = game_state.round_state

        if round_state.current_player_seat != seat:
            return [{"event": "error", "data": {"message": "not your turn"}, "target": f"seat_{seat}"}]

        tile_id = data.get("tile_id")
        if tile_id is None:
            return [{"event": "error", "data": {"message": "tile_id required"}, "target": f"seat_{seat}"}]

        try:
            discard_events = process_discard_phase(round_state, game_state, tile_id, is_riichi=False)
            events = _convert_events(discard_events)
        except ValueError as e:
            return [{"event": "error", "data": {"message": str(e)}, "target": f"seat_{seat}"}]

        return await self._process_post_discard(game_id, events)

    async def _handle_riichi(self, game_id: str, seat: int, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Handle a riichi declaration with discard."""
        game_state = self._games[game_id]
        round_state = game_state.round_state

        if round_state.current_player_seat != seat:
            return [{"event": "error", "data": {"message": "not your turn"}, "target": f"seat_{seat}"}]

        tile_id = data.get("tile_id")
        if tile_id is None:
            return [{"event": "error", "data": {"message": "tile_id required"}, "target": f"seat_{seat}"}]

        try:
            discard_events = process_discard_phase(round_state, game_state, tile_id, is_riichi=True)
            events = _convert_events(discard_events)
        except ValueError as e:
            return [{"event": "error", "data": {"message": str(e)}, "target": f"seat_{seat}"}]

        return await self._process_post_discard(game_id, events)

    async def _process_post_discard(self, game_id: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Process events after a discard (check round end, call prompts, bot turns)."""
        game_state = self._games[game_id]
        round_state = game_state.round_state

        if round_state.phase == RoundPhase.FINISHED:
            result = _extract_round_result(events)
            events.extend(await self._handle_round_end(game_id, result))
            return events

        has_call_prompt = any(e.get("event") == "call_prompt" for e in events)
        if has_call_prompt:
            # check if any human player can respond to the call prompt
            human_can_call = self._human_can_respond_to_prompt(round_state, events)
            if human_can_call:
                # wait for human response - don't advance the game
                return events

            bot_responses = await self._process_bot_call_responses(game_id, events)
            events.extend(bot_responses)

            if round_state.phase == RoundPhase.FINISHED:
                result = _extract_round_result(events)
                events.extend(await self._handle_round_end(game_id, result))
                return events

        # draw for next player before processing their turn
        if round_state.phase == RoundPhase.PLAYING:
            draw_events = process_draw_phase(round_state, game_state)
            events.extend(_convert_events(draw_events))

            if round_state.phase == RoundPhase.FINISHED:
                result = _extract_round_result(events)
                events.extend(await self._handle_round_end(game_id, result))
                return events

        # process bot turns if next player is a bot
        if round_state.phase == RoundPhase.PLAYING:
            current_player = round_state.players[round_state.current_player_seat]
            if current_player.is_bot:
                bot_events = await self._process_bot_turns(game_id)
                events.extend(bot_events)

        return events

    def _human_can_respond_to_prompt(
        self, round_state: MahjongRoundState, events: list[dict[str, Any]]
    ) -> bool:
        """Check if any human player can respond to a call prompt in the events."""
        for event in events:
            if event.get("event") != "call_prompt":
                continue
            callers = event.get("data", {}).get("callers", [])
            for caller_info in callers:
                caller_seat = caller_info if isinstance(caller_info, int) else caller_info.get("seat")
                if caller_seat is not None:
                    player = round_state.players[caller_seat]
                    if not player.is_bot:
                        return True
        return False

    async def _handle_tsumo(self, game_id: str, seat: int) -> list[dict[str, Any]]:
        """Handle a tsumo declaration."""
        game_state = self._games[game_id]
        round_state = game_state.round_state

        if round_state.current_player_seat != seat:
            return [{"event": "error", "data": {"message": "not your turn"}, "target": f"seat_{seat}"}]

        try:
            tsumo_events = process_tsumo_call(round_state, game_state, seat)
            events = _convert_events(tsumo_events)
        except ValueError as e:
            return [{"event": "error", "data": {"message": str(e)}, "target": f"seat_{seat}"}]

        result = _extract_round_result(events)
        events.extend(await self._handle_round_end(game_id, result))
        return events

    async def _handle_ron(self, game_id: str, seat: int, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Handle a ron call from a player."""
        game_state = self._games[game_id]
        round_state = game_state.round_state

        tile_id = data.get("tile_id")
        discarder_seat = data.get("from_seat")

        if tile_id is None or discarder_seat is None:
            return [
                {
                    "event": "error",
                    "data": {"message": "tile_id and from_seat required"},
                    "target": f"seat_{seat}",
                }
            ]

        try:
            ron_events = process_ron_call(round_state, game_state, [seat], tile_id, discarder_seat)
            events = _convert_events(ron_events)
        except ValueError as e:
            return [{"event": "error", "data": {"message": str(e)}, "target": f"seat_{seat}"}]

        result = _extract_round_result(events)
        events.extend(await self._handle_round_end(game_id, result))
        return events

    async def _handle_pon(self, game_id: str, seat: int, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Handle a pon call from a player."""
        game_state = self._games[game_id]
        round_state = game_state.round_state

        tile_id = data.get("tile_id")
        if tile_id is None:
            return [{"event": "error", "data": {"message": "tile_id required"}, "target": f"seat_{seat}"}]

        try:
            meld_events = process_meld_call(round_state, game_state, seat, "pon", tile_id)
            events = _convert_events(meld_events)
        except ValueError as e:
            return [{"event": "error", "data": {"message": str(e)}, "target": f"seat_{seat}"}]

        events.append(self._create_turn_event(round_state, game_state, seat))
        return events

    async def _handle_chi(self, game_id: str, seat: int, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Handle a chi call from a player."""
        game_state = self._games[game_id]
        round_state = game_state.round_state

        tile_id = data.get("tile_id")
        sequence_tiles = data.get("sequence_tiles")
        if tile_id is None or sequence_tiles is None:
            return [
                {
                    "event": "error",
                    "data": {"message": "tile_id and sequence_tiles required"},
                    "target": f"seat_{seat}",
                }
            ]

        try:
            meld_events = process_meld_call(
                round_state, game_state, seat, "chi", tile_id, sequence_tiles=tuple(sequence_tiles)
            )
            events = _convert_events(meld_events)
        except ValueError as e:
            return [{"event": "error", "data": {"message": str(e)}, "target": f"seat_{seat}"}]

        events.append(self._create_turn_event(round_state, game_state, seat))
        return events

    async def _handle_kan(self, game_id: str, seat: int, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Handle a kan call (open, closed, or added)."""
        game_state = self._games[game_id]
        round_state = game_state.round_state

        tile_id = data.get("tile_id")
        kan_type = data.get("kan_type", "open")
        if tile_id is None:
            return [{"event": "error", "data": {"message": "tile_id required"}, "target": f"seat_{seat}"}]

        try:
            meld_events = process_meld_call(round_state, game_state, seat, f"{kan_type}_kan", tile_id)
            events = _convert_events(meld_events)
        except ValueError as e:
            return [{"event": "error", "data": {"message": str(e)}, "target": f"seat_{seat}"}]

        if round_state.phase == RoundPhase.FINISHED:
            result = _extract_round_result(events)
            events.extend(await self._handle_round_end(game_id, result))
            return events

        chankan_prompt = next(
            (
                e
                for e in events
                if e.get("event") == "call_prompt" and e.get("data", {}).get("call_type") == "chankan"
            ),
            None,
        )
        if chankan_prompt:
            # check if any human player can respond to the chankan prompt
            human_can_call = self._human_can_respond_to_prompt(round_state, events)
            if human_can_call:
                # wait for human response - don't advance the game
                return events

            bot_responses = await self._process_bot_call_responses(game_id, events)
            events.extend(bot_responses)
            if round_state.phase == RoundPhase.FINISHED:
                result = _extract_round_result(events)
                events.extend(await self._handle_round_end(game_id, result))
                return events

            # chankan was declined, complete the added kan
            prompt_data = chankan_prompt.get("data", {})
            kan_tile_id = prompt_data.get("tile_id")
            kan_caller_seat = prompt_data.get("from_seat")
            if kan_tile_id is not None and kan_caller_seat is not None:
                kan_events = self._complete_added_kan_after_chankan_decline(
                    round_state, game_state, kan_caller_seat, kan_tile_id
                )
                events.extend(kan_events)

        # after kan, the player already drew from dead wall in the kan function
        # emit draw event for the dead wall tile, then turn event
        if round_state.phase == RoundPhase.PLAYING:
            player = round_state.players[seat]
            if player.tiles:
                # the dead wall tile is the last tile in hand (appended by draw_from_dead_wall)
                drawn_tile = player.tiles[-1]
                events.append(
                    {
                        "event": "draw",
                        "data": {
                            "type": "draw",
                            "seat": seat,
                            "tile_id": drawn_tile,
                            "tile": tile_to_string(drawn_tile),
                            "is_rinshan": True,
                            "target": f"seat_{seat}",
                        },
                        "target": f"seat_{seat}",
                    }
                )
            events.append(self._create_turn_event(round_state, game_state, seat))

        return events

    async def _handle_kyuushu(self, game_id: str, seat: int) -> list[dict[str, Any]]:
        """Handle kyuushu kyuuhai (nine terminals) abortive draw declaration."""
        game_state = self._games[game_id]
        round_state = game_state.round_state

        if round_state.current_player_seat != seat:
            return [{"event": "error", "data": {"message": "not your turn"}, "target": f"seat_{seat}"}]

        player = round_state.players[seat]
        if not can_call_kyuushu_kyuuhai(player, round_state):
            return [
                {
                    "event": "error",
                    "data": {"message": "cannot call kyuushu kyuuhai"},
                    "target": f"seat_{seat}",
                }
            ]

        result = call_kyuushu_kyuuhai(round_state)
        round_state.phase = RoundPhase.FINISHED
        process_abortive_draw(game_state, AbortiveDrawType.NINE_TERMINALS)

        events: list[dict[str, Any]] = [
            {
                "event": "round_end",
                "data": {"type": "round_end", "result": result, "target": "all"},
                "target": "all",
            }
        ]
        events.extend(await self._handle_round_end(game_id, result))
        return events

    async def _handle_pass(self, game_id: str, seat: int) -> list[dict[str, Any]]:
        """
        Handle passing on a meld/ron opportunity.

        Pass is only valid when the current player has 13 tiles (just discarded).
        After acknowledging the pass, resumes game processing:
        advances the turn, draws for the next player, and processes bot turns if needed.
        """
        game_state = self._games.get(game_id)
        if game_state is None:
            return [{"event": "error", "data": {"message": "game not found"}, "target": f"seat_{seat}"}]

        round_state = game_state.round_state
        events: list[dict[str, Any]] = [
            {"event": "pass_acknowledged", "data": {"seat": seat}, "target": f"seat_{seat}"}
        ]

        # pass is only valid when a discard just happened (current player has 13 tiles)
        current_player = round_state.players[round_state.current_player_seat]
        if len(current_player.tiles) != 13:
            # no pending call prompt, just acknowledge the pass
            return events

        # advance to the next player's turn
        from game.logic.round import advance_turn

        advance_turn(round_state)

        # draw for next player
        if round_state.phase == RoundPhase.PLAYING:
            draw_events = process_draw_phase(round_state, game_state)
            events.extend(_convert_events(draw_events))

            if round_state.phase == RoundPhase.FINISHED:
                result = _extract_round_result(events)
                events.extend(await self._handle_round_end(game_id, result))
                return events

        # process bot turns if next player is a bot
        if round_state.phase == RoundPhase.PLAYING:
            current_player = round_state.players[round_state.current_player_seat]
            if current_player.is_bot:
                bot_events = await self._process_bot_turns(game_id)
                events.extend(bot_events)

        return events

    def _complete_added_kan_after_chankan_decline(
        self,
        round_state: MahjongRoundState,
        game_state: MahjongGameState,
        caller_seat: int,
        tile_id: int,
    ) -> list[dict[str, Any]]:
        """Complete an added kan after chankan opportunity was declined."""
        meld = call_added_kan(round_state, caller_seat, tile_id)
        tile_ids = list(meld.tiles) if meld.tiles else []
        events: list[dict[str, Any]] = [
            {
                "event": "meld",
                "data": {
                    "type": "meld",
                    "meld_type": "kan",
                    "kan_type": "added",
                    "caller_seat": caller_seat,
                    "tile_ids": tile_ids,
                    "tiles": [tile_to_string(t) for t in tile_ids],
                    "target": "all",
                },
                "target": "all",
            }
        ]

        # check for four kans abortive draw
        if check_four_kans(round_state):
            result = process_abortive_draw(game_state, AbortiveDrawType.FOUR_KANS)
            round_state.phase = RoundPhase.FINISHED
            events.append(
                {"event": "round_end", "data": {"type": "round_end", "result": result}, "target": "all"}
            )
        else:
            # emit draw event for the dead wall tile
            player = round_state.players[caller_seat]
            if player.tiles:
                drawn_tile = player.tiles[-1]
                events.append(
                    {
                        "event": "draw",
                        "data": {
                            "type": "draw",
                            "seat": caller_seat,
                            "tile_id": drawn_tile,
                            "tile": tile_to_string(drawn_tile),
                            "is_rinshan": True,
                            "target": f"seat_{caller_seat}",
                        },
                        "target": f"seat_{caller_seat}",
                    }
                )

        return events

    def _create_turn_event(
        self, round_state: MahjongRoundState, game_state: MahjongGameState, seat: int
    ) -> dict[str, Any]:
        """Create a turn event for a player."""
        actions_dict = get_available_actions(round_state, game_state, seat)
        available_actions = _format_available_actions(actions_dict)
        return {
            "event": "turn",
            "data": {"type": "turn", "current_seat": seat, "available_actions": available_actions},
            "target": f"seat_{seat}",
        }

    async def _handle_round_end(self, game_id: str, round_result: dict | None = None) -> list[dict[str, Any]]:
        """Handle the end of a round and start next round or end game."""
        game_state = self._games[game_id]

        # use provided result or construct default
        result = round_result if round_result else {"type": "unknown"}
        process_round_end(game_state, result)

        if check_game_end(game_state):
            game_result = finalize_game(game_state)
            return [{"event": "game_end", "data": game_result, "target": "all"}]

        return await self._start_next_round(game_id)

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
        events.extend(_convert_events(draw_events))

        dealer_seat = round_state.dealer_seat
        if round_state.players[dealer_seat].is_bot:
            bot_events = await self._process_bot_turns(game_id)
            events.extend(bot_events)

        return events

    async def _process_bot_turns(self, game_id: str) -> list[dict[str, Any]]:
        """
        Process bot turns until it's a human player's turn.

        Returns all events generated during bot turns.
        """
        game_state = self._games.get(game_id)
        if game_state is None:
            return []

        round_state = game_state.round_state
        bots = self._bots.get(game_id, [])
        events: list[dict[str, Any]] = []

        for _ in range(100):  # safety limit
            if round_state.phase == RoundPhase.FINISHED:
                break

            current_seat = round_state.current_player_seat
            current_player = round_state.players[current_seat]

            if not current_player.is_bot:
                break

            bot_index = current_seat - 1
            if bot_index < 0 or bot_index >= len(bots):
                break

            turn_events = await self._process_single_bot_turn(game_id, bots[bot_index], current_seat)
            events.extend(turn_events)

            if round_state.phase == RoundPhase.FINISHED:
                break

            # check if we're waiting for human input on a call prompt
            has_call_prompt = any(e.get("event") == "call_prompt" for e in turn_events)
            if has_call_prompt and self._human_can_respond_to_prompt(round_state, turn_events):
                break

        return events

    async def _process_single_bot_turn(
        self,
        game_id: str,
        bot: BotPlayer,
        current_seat: int,
    ) -> list[dict[str, Any]]:
        """Process a single bot's turn and return events."""
        game_state = self._games[game_id]
        round_state = game_state.round_state
        current_player = round_state.players[current_seat]

        action = get_bot_action(bot, current_player, round_state)
        action_type = action.get("action")
        events: list[dict[str, Any]] = []

        if action_type == "tsumo":
            tsumo_events = process_tsumo_call(round_state, game_state, current_seat)
            events.extend(_convert_events(tsumo_events))
            return events

        if action_type in ("riichi", "discard"):
            tile_id = action.get("tile_id")
            is_riichi = action_type == "riichi"
            discard_events = process_discard_phase(round_state, game_state, tile_id, is_riichi=is_riichi)
            events.extend(_convert_events(discard_events))

        if round_state.phase == RoundPhase.FINISHED:
            return events

        # handle call prompts from discard
        has_call_prompt = any(e.get("event") == "call_prompt" for e in events)
        if has_call_prompt:
            # check if any human player can respond to the call prompt
            human_can_call = self._human_can_respond_to_prompt(round_state, events)
            if human_can_call:
                # wait for human response - don't advance the game
                return events

            bot_responses = await self._process_bot_call_responses(game_id, events)
            events.extend(bot_responses)
            if round_state.phase == RoundPhase.FINISHED:
                return events

        # draw for next player
        if round_state.phase == RoundPhase.PLAYING:
            draw_events = process_draw_phase(round_state, game_state)
            events.extend(_convert_events(draw_events))

            # check if draw phase caused round to end (exhaustive draw)
            if round_state.phase == RoundPhase.FINISHED:
                result = _extract_round_result(events)
                events.extend(await self._handle_round_end(game_id, result))

        return events

    async def _process_bot_call_responses(
        self, game_id: str, events: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Process bot responses to call prompts (ron, pon, chi, kan).

        Returns events generated from bot calls.
        """
        game_state = self._games.get(game_id)
        if game_state is None:
            return []

        call_prompts = [e for e in events if e.get("event") == "call_prompt"]
        result_events: list[dict[str, Any]] = []

        for prompt in call_prompts:
            prompt_events = await self._process_single_call_prompt(game_id, prompt)
            result_events.extend(prompt_events)
            if prompt_events:
                return result_events

        return result_events

    async def _process_single_call_prompt(self, game_id: str, prompt: dict[str, Any]) -> list[dict[str, Any]]:
        """Process a single call prompt and return any resulting events."""
        game_state = self._games[game_id]
        round_state = game_state.round_state
        bots = self._bots.get(game_id, [])

        prompt_data = prompt.get("data", {})
        call_type = prompt_data.get("call_type")
        tile_id = prompt_data.get("tile_id")
        from_seat = prompt_data.get("from_seat")
        callers = prompt_data.get("callers", [])

        ron_callers, meld_caller, meld_type = self._evaluate_bot_calls(
            round_state, bots, callers, call_type, tile_id
        )

        if ron_callers:
            ron_events = process_ron_call(round_state, game_state, ron_callers, tile_id, from_seat)
            return _convert_events(ron_events)

        if meld_caller is not None and meld_type is not None and meld_type != "chi":
            meld_events = process_meld_call(round_state, game_state, meld_caller, meld_type, tile_id)
            result = _convert_events(meld_events)
            bot_turn_events = await self._process_bot_turns(game_id)
            result.extend(bot_turn_events)
            return result

        # no bot wants to call - advance the turn since process_discard_phase didn't
        from game.logic.round import advance_turn

        advance_turn(round_state)
        return []

    def _evaluate_bot_calls(
        self,
        round_state: MahjongRoundState,
        bots: list[BotPlayer],
        callers: list,
        call_type: str,
        tile_id: int,
    ) -> tuple[list[int], int | None, str | None]:
        """Evaluate which bots want to make calls. Returns (ron_callers, meld_caller, meld_type)."""
        ron_callers: list[int] = []
        meld_caller: int | None = None
        meld_type: str | None = None

        for caller_info in callers:
            result = self._evaluate_single_caller(round_state, bots, caller_info, call_type, tile_id)
            if result is None:
                continue
            call_result_type, caller_seat, result_meld_type = result
            if call_result_type == "ron":
                ron_callers.append(caller_seat)
            elif call_result_type == "meld" and result_meld_type:
                meld_caller, meld_type = caller_seat, result_meld_type

        return ron_callers, meld_caller, meld_type

    def _evaluate_single_caller(
        self,
        round_state: MahjongRoundState,
        bots: list[BotPlayer],
        caller_info: int | dict,
        call_type: str,
        tile_id: int,
    ) -> tuple[str, int, str | None] | None:
        """Evaluate a single caller's response. Returns (result_type, seat, meld_type) or None."""
        caller_seat, caller_options = self._parse_caller_info(caller_info)
        if caller_seat is None:
            return None

        player = round_state.players[caller_seat]
        if not player.is_bot:
            return None

        bot_index = caller_seat - 1
        if bot_index < 0 or bot_index >= len(bots):
            return None

        bot = bots[bot_index]

        if call_type == "ron" and should_call_ron(bot, player, tile_id, round_state):
            return ("ron", caller_seat, None)

        if call_type == "meld":
            meld_call_type = caller_info.get("call_type") if isinstance(caller_info, dict) else None
            meld_result = _get_bot_meld_response(
                bot, player, (meld_call_type, caller_options), tile_id, round_state
            )
            if meld_result:
                return ("meld", caller_seat, meld_result)

        return None

    def _parse_caller_info(self, caller_info: int | dict) -> tuple[int | None, list | None]:
        """Parse caller info which can be int (seat) or dict with seat/options."""
        if isinstance(caller_info, int):
            return caller_info, None
        return caller_info.get("seat"), caller_info.get("options")
