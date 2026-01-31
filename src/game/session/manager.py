import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

from game.logic.enums import TimeoutType
from game.logic.timer import TurnTimer
from game.messaging.events import (
    CallPromptEvent,
    ErrorEvent,
    GameEndedEvent,
    RoundStartedEvent,
    TurnEvent,
)
from game.messaging.types import (
    ErrorMessage,
    GameJoinedMessage,
    GameLeftMessage,
    PlayerJoinedMessage,
    PlayerLeftMessage,
    ServerChatMessage,
)
from game.session.models import Game, Player
from game.session.types import GameInfo

if TYPE_CHECKING:
    from game.logic.service import GameService
    from game.logic.types import MeldCaller
    from game.messaging.events import ServiceEvent
    from game.messaging.protocol import ConnectionProtocol

logger = logging.getLogger(__name__)


class SessionManager:
    MAX_PLAYERS_PER_GAME = 4  # Mahjong requires exactly 4 players

    def __init__(self, game_service: GameService) -> None:
        self._game_service = game_service
        self._connections: dict[str, ConnectionProtocol] = {}
        self._players: dict[str, Player] = {}  # connection_id -> Player
        self._games: dict[str, Game] = {}  # game_id -> Game
        self._timers: dict[str, TurnTimer] = {}  # game_id -> TurnTimer
        self._game_locks: dict[str, asyncio.Lock] = {}  # game_id -> Lock

    def register_connection(self, connection: ConnectionProtocol) -> None:
        self._connections[connection.connection_id] = connection

    def unregister_connection(self, connection: ConnectionProtocol) -> None:
        self._connections.pop(connection.connection_id, None)
        self._players.pop(connection.connection_id, None)

    def get_player(self, connection: ConnectionProtocol) -> Player | None:
        return self._players.get(connection.connection_id)

    def get_game(self, game_id: str) -> Game | None:
        return self._games.get(game_id)

    @property
    def game_count(self) -> int:
        return len(self._games)

    def get_games_info(self) -> list[GameInfo]:
        """
        Return info about all active games for the lobby list.
        """
        return [
            GameInfo(
                game_id=game.game_id,
                player_count=game.player_count,
                max_players=self.MAX_PLAYERS_PER_GAME,
            )
            for game in self._games.values()
        ]

    def create_game(self, game_id: str) -> Game:
        game = Game(game_id=game_id)
        self._games[game_id] = game
        logger.info(f"game created: {game_id}")
        return game

    async def _send_error(self, connection: ConnectionProtocol, code: str, message: str) -> None:
        """Send an error message to a connection."""
        await connection.send_message(ErrorMessage(code=code, message=message).model_dump())

    async def join_game(
        self,
        connection: ConnectionProtocol,
        game_id: str,
        player_name: str,
    ) -> None:
        # check if already in a game
        existing_player = self._players.get(connection.connection_id)
        if existing_player and existing_player.game_id:
            await self._send_error(connection, "already_in_game", "You must leave your current game first")
            return

        game = self._games.get(game_id)
        if game is None:
            await self._send_error(connection, "game_not_found", "Game does not exist")
            return

        # check game capacity
        if game.player_count >= self.MAX_PLAYERS_PER_GAME:
            await self._send_error(connection, "game_full", "Game is full")
            return

        # check for duplicate name in game
        if player_name in [p.name for p in game.players.values()]:
            await self._send_error(connection, "name_taken", "That name is already taken in this game")
            return

        # create player and add to game
        player = Player(connection=connection, name=player_name, game_id=game_id)
        self._players[connection.connection_id] = player
        game.players[connection.connection_id] = player
        logger.info(f"player '{player_name}' joined game {game_id}")

        # notify the joining player
        await connection.send_message(
            GameJoinedMessage(
                game_id=game_id,
                players=game.player_names,
            ).model_dump()
        )

        # notify other players in the game
        await self._broadcast_to_game(
            game=game,
            message=PlayerJoinedMessage(player_name=player_name).model_dump(),
            exclude_connection_id=connection.connection_id,
        )

        # start the mahjong game when first human player joins
        if game.player_count == 1:
            await self._start_mahjong_game(game)

    async def leave_game(
        self,
        connection: ConnectionProtocol,
        *,
        notify_player: bool = True,
    ) -> None:
        player = self._players.get(connection.connection_id)
        if player is None or player.game_id is None:
            return

        game = self._games.get(player.game_id)
        if game is None:
            return

        player_name = player.name
        logger.info(f"player '{player_name}' left game {player.game_id}")

        # remove player from game
        game.players.pop(connection.connection_id, None)
        player.game_id = None

        # notify the leaving player (skip if connection is already closed)
        if notify_player:
            await connection.send_message(GameLeftMessage().model_dump())

        # notify remaining players
        await self._broadcast_to_game(
            game=game,
            message=PlayerLeftMessage(player_name=player_name).model_dump(),
        )

        # clean up empty games
        if game.is_empty:
            logger.info(f"game {game.game_id} is empty, cleaning up")
            self._games.pop(game.game_id, None)
            timer = self._timers.pop(game.game_id, None)
            if timer:
                timer.cancel()
            self._game_locks.pop(game.game_id, None)

    async def handle_game_action(
        self,
        connection: ConnectionProtocol,
        action: str,
        data: dict[str, Any],
    ) -> None:
        player = self._players.get(connection.connection_id)
        if player is None or player.game_id is None:
            await self._send_error(connection, "not_in_game", "You must join a game first")
            return

        game = self._games.get(player.game_id)
        if game is None:
            return

        game_id = player.game_id
        lock = self._game_locks.setdefault(game_id, asyncio.Lock())

        async with lock:
            events = await self._game_service.handle_action(
                game_id=game_id,
                player_name=player.name,
                action=action,
                data=data,
            )

            # only deduct bank time if the action progressed the game state.
            # failed actions (errors) should not consume bank time or cancel the timer.
            timer = self._timers.get(game_id)
            if timer and self._has_game_events(events):
                timer.stop()

            await self._broadcast_events(game, events)
            await self._maybe_start_timer(game, events)
            await self._close_connections_on_game_end(game, events)

    async def broadcast_chat(
        self,
        connection: ConnectionProtocol,
        text: str,
    ) -> None:
        player = self._players.get(connection.connection_id)
        if player is None or player.game_id is None:
            await self._send_error(connection, "not_in_game", "You must join a game first")
            return

        game = self._games.get(player.game_id)
        if game is None:
            return

        await self._broadcast_to_game(
            game=game,
            message=ServerChatMessage(
                player_name=player.name,
                text=text,
            ).model_dump(),
        )

    async def _start_mahjong_game(self, game: Game) -> None:
        """
        Start the mahjong game when first human joins.

        Calls the game service to initialize the game with the human player
        and bots, then broadcasts the initial state to all players.
        """
        player_names = game.player_names
        events = await self._game_service.start_game(game.game_id, player_names)

        # assign seats to session players
        for player in game.players.values():
            seat = self._game_service.get_player_seat(game.game_id, player.name)
            if seat is not None:
                player.seat = seat

        # create timer and lock for this game
        timer = TurnTimer()
        self._timers[game.game_id] = timer
        self._game_locks[game.game_id] = asyncio.Lock()

        async with self._game_locks[game.game_id]:
            await self._broadcast_events(game, events)
            await self._maybe_start_timer(game, events)

    async def _broadcast_events(
        self,
        game: Game,
        events: list[ServiceEvent],
    ) -> None:
        """
        Broadcast events with target-based filtering.

        Events with target "all" go to everyone.
        Events with target "seat_N" go only to the player at that seat.
        """
        # build seat -> player mapping using assigned seats
        seat_to_player = {p.seat: p for p in game.players.values() if p.seat is not None}

        for event in events:
            message = {"type": event.event, **event.data.model_dump(exclude={"type", "target"})}

            if event.target == "all":
                await self._broadcast_to_game(game, message)
            elif event.target.startswith("seat_"):
                seat = int(event.target.split("_")[1])
                player = seat_to_player.get(seat)
                if player:
                    # ignore connection errors, will be cleaned up on disconnect
                    with contextlib.suppress(RuntimeError, OSError):
                        await player.connection.send_message(message)

    async def _broadcast_to_game(
        self,
        game: Game,
        message: dict[str, Any],
        exclude_connection_id: str | None = None,
    ) -> None:
        for player in game.players.values():
            if player.connection_id != exclude_connection_id:
                # ignore connection errors, will be cleaned up on disconnect
                with contextlib.suppress(RuntimeError, OSError):
                    await player.connection.send_message(message)

    async def _maybe_start_timer(self, game: Game, events: list[ServiceEvent]) -> None:
        """
        Inspect events and start appropriate timer if a connected player needs to act.
        """
        if self._cleanup_timer_on_game_end(game, events):
            return

        timer = self._timers.get(game.game_id)
        if timer is None:
            return

        # add round bonus once when a new round starts
        if any(isinstance(event.data, RoundStartedEvent) for event in events):
            timer.add_round_bonus()

        game_id = game.game_id

        # check for turn events targeting a connected player
        for event in events:
            if isinstance(event.data, TurnEvent):
                seat = event.data.current_seat
                if self._get_player_at_seat(game, seat) is not None:
                    timer.start_turn_timer(
                        lambda gid=game_id, s=seat: self._handle_timeout(gid, TimeoutType.TURN, s)
                    )
                    return

        # check for call prompts targeting a connected player
        seat = self._find_connected_caller_seat(game, events)
        if seat is not None:
            timer.start_meld_timer(lambda gid=game_id, s=seat: self._handle_timeout(gid, TimeoutType.MELD, s))

    def _cleanup_timer_on_game_end(self, game: Game, events: list[ServiceEvent]) -> bool:
        """
        Clean up timer when the game ends. Returns True if game ended.

        Only cancels the timer here. Lock and timer dict cleanup happens in leave_game
        when the game becomes empty, to avoid removing the lock while it is still held.
        """
        if not any(isinstance(event.data, GameEndedEvent) for event in events):
            return False
        timer = self._timers.get(game.game_id)
        if timer:
            timer.cancel()
        return True

    async def _close_connections_on_game_end(self, game: Game, events: list[ServiceEvent]) -> None:
        """
        Close all player connections after the game ends.

        The WebSocket disconnect handlers will clean up session state
        (remove players, clean up empty game) when connections close.
        """
        if not any(isinstance(event.data, GameEndedEvent) for event in events):
            return
        for player in list(game.players.values()):
            with contextlib.suppress(RuntimeError, OSError):
                await player.connection.close(code=1000, reason="game_ended")

    def _get_player_at_seat(self, game: Game, seat: int) -> Player | None:
        """Get the session player at a specific seat, if connected."""
        for player in game.players.values():
            if player.seat == seat:
                return player
        return None

    def _has_game_events(self, events: list[ServiceEvent]) -> bool:
        """Check if events contain non-error game events (indicating the action progressed the game)."""
        return any(not isinstance(event.data, ErrorEvent) for event in events)

    def _get_caller_seats(self, callers: list[int] | list[MeldCaller]) -> list[int]:
        """Extract seat numbers from a callers list."""
        return [caller if isinstance(caller, int) else caller.seat for caller in callers]

    def _find_connected_caller_seat(self, game: Game, events: list[ServiceEvent]) -> int | None:
        """Find the first connected player's seat from call prompt events."""
        for event in events:
            if isinstance(event.data, CallPromptEvent):
                for seat in self._get_caller_seats(event.data.callers):
                    if self._get_player_at_seat(game, seat) is not None:
                        return seat
        return None

    async def _handle_timeout(self, game_id: str, timeout_type: TimeoutType, seat: int) -> None:
        """Handle timer expiry by performing the default action for the timed-out seat."""
        lock = self._game_locks.get(game_id)
        if lock is None:
            return

        async with lock:
            game = self._games.get(game_id)
            if game is None:
                return

            player = self._get_player_at_seat(game, seat)
            if player is None:
                return

            # deduct elapsed bank time without cancelling the task, since this
            # callback executes within the timer task itself
            timer = self._timers.get(game_id)
            if timer:
                timer.consume_bank()

            events = await self._game_service.handle_timeout(game_id, player.name, timeout_type)
            await self._broadcast_events(game, events)
            await self._maybe_start_timer(game, events)
            await self._close_connections_on_game_end(game, events)
