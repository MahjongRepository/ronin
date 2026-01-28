import contextlib
from typing import TYPE_CHECKING, Any

from game.messaging.types import (
    ErrorMessage,
    GameEventMessage,
    GameJoinedMessage,
    GameLeftMessage,
    PlayerJoinedMessage,
    PlayerLeftMessage,
    ServerChatMessage,
)
from game.session.models import Game, Player

if TYPE_CHECKING:
    from game.logic.service import GameService
    from game.messaging.protocol import ConnectionProtocol


class SessionManager:
    MAX_PLAYERS_PER_GAME = 4  # Mahjong requires exactly 4 players

    def __init__(self, game_service: GameService) -> None:
        self._game_service = game_service
        self._connections: dict[str, ConnectionProtocol] = {}
        self._players: dict[str, Player] = {}  # connection_id -> Player
        self._games: dict[str, Game] = {}  # game_id -> Game

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

    def get_games_info(self) -> list[dict[str, Any]]:
        """
        Return info about all active games for the lobby list.
        """
        return [
            {
                "game_id": game.game_id,
                "player_count": game.player_count,
                "max_players": self.MAX_PLAYERS_PER_GAME,
            }
            for game in self._games.values()
        ]

    def create_game(self, game_id: str) -> Game:
        game = Game(game_id=game_id)
        self._games[game_id] = game
        return game

    async def join_game(
        self,
        connection: ConnectionProtocol,
        game_id: str,
        player_name: str,
    ) -> None:
        # check if already in a game
        existing_player = self._players.get(connection.connection_id)
        if existing_player and existing_player.game_id:
            await connection.send_json(
                ErrorMessage(
                    code="already_in_game",
                    message="You must leave your current game first",
                ).model_dump()
            )
            return

        game = self._games.get(game_id)
        if game is None:
            await connection.send_json(
                ErrorMessage(
                    code="game_not_found",
                    message="Game does not exist",
                ).model_dump()
            )
            return

        # check game capacity
        if game.player_count >= self.MAX_PLAYERS_PER_GAME:
            await connection.send_json(ErrorMessage(code="game_full", message="Game is full").model_dump())
            return

        # check for duplicate name in game
        if player_name in [p.name for p in game.players.values()]:
            await connection.send_json(
                ErrorMessage(
                    code="name_taken",
                    message="That name is already taken in this game",
                ).model_dump()
            )
            return

        # create player and add to game
        player = Player(connection=connection, name=player_name, game_id=game_id)
        self._players[connection.connection_id] = player
        game.players[connection.connection_id] = player

        # notify the joining player
        await connection.send_json(
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

        # remove player from game
        game.players.pop(connection.connection_id, None)
        player.game_id = None

        # notify the leaving player (skip if connection is already closed)
        if notify_player:
            await connection.send_json(GameLeftMessage().model_dump())

        # notify remaining players
        await self._broadcast_to_game(
            game=game,
            message=PlayerLeftMessage(player_name=player_name).model_dump(),
        )

        # clean up empty games
        if game.is_empty:
            self._games.pop(game.game_id, None)

    async def handle_game_action(
        self,
        connection: ConnectionProtocol,
        action: str,
        data: dict[str, Any],
    ) -> None:
        player = self._players.get(connection.connection_id)
        if player is None or player.game_id is None:
            await connection.send_json(
                ErrorMessage(
                    code="not_in_game",
                    message="You must join a game first",
                ).model_dump()
            )
            return

        game = self._games.get(player.game_id)
        if game is None:
            return

        # delegate to game service
        events = await self._game_service.handle_action(
            game_id=player.game_id,
            player_name=player.name,
            action=action,
            data=data,
        )

        # broadcast each event to appropriate targets
        await self._broadcast_events(game, events)

    async def broadcast_chat(
        self,
        connection: ConnectionProtocol,
        text: str,
    ) -> None:
        player = self._players.get(connection.connection_id)
        if player is None or player.game_id is None:
            await connection.send_json(
                ErrorMessage(
                    code="not_in_game",
                    message="You must join a game first",
                ).model_dump()
            )
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
        await self._broadcast_events(game, events)

    async def _broadcast_events(
        self,
        game: Game,
        events: list[dict[str, Any]],
    ) -> None:
        """
        Broadcast events with target-based filtering.

        Events with target "all" go to everyone.
        Events with target "seat_N" go only to the player at that seat.
        """
        # build seat -> player mapping
        seat_to_player = dict(enumerate(game.players.values()))

        for event in events:
            target = event.get("target", "all")
            message = GameEventMessage(
                event=event.get("event", ""),
                data=event.get("data", {}),
            ).model_dump()

            if target == "all":
                await self._broadcast_to_game(game, message)
            elif target.startswith("seat_"):
                seat = int(target.split("_")[1])
                player = seat_to_player.get(seat)
                if player:
                    # ignore connection errors, will be cleaned up on disconnect
                    with contextlib.suppress(RuntimeError, OSError):
                        await player.connection.send_json(message)

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
                    await player.connection.send_json(message)
