from typing import TYPE_CHECKING, Any

from game.messaging.types import (
    ErrorMessage,
    GameEventMessage,
    PlayerJoinedMessage,
    PlayerLeftMessage,
    RoomJoinedMessage,
    RoomLeftMessage,
    ServerChatMessage,
)
from game.session.models import Player, Room

if TYPE_CHECKING:
    from game.logic.service import GameService
    from game.messaging.protocol import ConnectionProtocol


class SessionManager:
    MAX_PLAYERS_PER_ROOM = 4  # Mahjong requires exactly 4 players

    def __init__(self, game_service: GameService) -> None:
        self._game_service = game_service
        self._connections: dict[str, ConnectionProtocol] = {}
        self._players: dict[str, Player] = {}  # connection_id -> Player
        self._rooms: dict[str, Room] = {}  # room_id -> Room

    def register_connection(self, connection: ConnectionProtocol) -> None:
        self._connections[connection.connection_id] = connection

    def unregister_connection(self, connection: ConnectionProtocol) -> None:
        self._connections.pop(connection.connection_id, None)
        self._players.pop(connection.connection_id, None)

    def get_player(self, connection: ConnectionProtocol) -> Player | None:
        return self._players.get(connection.connection_id)

    def get_room(self, room_id: str) -> Room | None:
        return self._rooms.get(room_id)

    @property
    def room_count(self) -> int:
        return len(self._rooms)

    def create_room(self, room_id: str) -> Room:
        room = Room(room_id=room_id)
        self._rooms[room_id] = room
        return room

    async def join_room(
        self,
        connection: ConnectionProtocol,
        room_id: str,
        player_name: str,
    ) -> None:
        # check if already in a room
        existing_player = self._players.get(connection.connection_id)
        if existing_player and existing_player.room_id:
            await connection.send_json(
                ErrorMessage(
                    code="already_in_room",
                    message="You must leave your current room first",
                ).model_dump()
            )
            return

        room = self._rooms.get(room_id)
        if room is None:
            room = Room(room_id=room_id)
            self._rooms[room_id] = room

        # check room capacity
        if room.player_count >= self.MAX_PLAYERS_PER_ROOM:
            await connection.send_json(ErrorMessage(code="room_full", message="Room is full").model_dump())
            return

        # check for duplicate name in room
        if player_name in [p.name for p in room.players.values()]:
            await connection.send_json(
                ErrorMessage(
                    code="name_taken",
                    message="That name is already taken in this room",
                ).model_dump()
            )
            return

        # create player and add to room
        player = Player(connection=connection, name=player_name, room_id=room_id)
        self._players[connection.connection_id] = player
        room.players[connection.connection_id] = player

        # notify the joining player
        await connection.send_json(
            RoomJoinedMessage(
                room_id=room_id,
                players=room.player_names,
            ).model_dump()
        )

        # notify other players in the room
        await self._broadcast_to_room(
            room=room,
            message=PlayerJoinedMessage(player_name=player_name).model_dump(),
            exclude_connection_id=connection.connection_id,
        )

    async def leave_room(self, connection: ConnectionProtocol) -> None:
        player = self._players.get(connection.connection_id)
        if player is None or player.room_id is None:
            return

        room = self._rooms.get(player.room_id)
        if room is None:
            return

        player_name = player.name

        # remove player from room
        room.players.pop(connection.connection_id, None)
        player.room_id = None

        # notify the leaving player
        await connection.send_json(RoomLeftMessage().model_dump())

        # notify remaining players
        await self._broadcast_to_room(
            room=room,
            message=PlayerLeftMessage(player_name=player_name).model_dump(),
        )

        # clean up empty rooms
        if room.is_empty:
            self._rooms.pop(room.room_id, None)

    async def handle_game_action(
        self,
        connection: ConnectionProtocol,
        action: str,
        data: dict[str, Any],
    ) -> None:
        player = self._players.get(connection.connection_id)
        if player is None or player.room_id is None:
            await connection.send_json(
                ErrorMessage(
                    code="not_in_room",
                    message="You must join a room first",
                ).model_dump()
            )
            return

        room = self._rooms.get(player.room_id)
        if room is None:
            return

        # delegate to game service
        result = await self._game_service.handle_action(
            room_id=player.room_id,
            player_name=player.name,
            action=action,
            data=data,
        )

        # broadcast the result to all players in the room
        if result:
            await self._broadcast_to_room(
                room=room,
                message=GameEventMessage(
                    event=result.get("event", action),
                    data=result.get("data", {}),
                ).model_dump(),
            )

    async def broadcast_chat(
        self,
        connection: ConnectionProtocol,
        text: str,
    ) -> None:
        player = self._players.get(connection.connection_id)
        if player is None or player.room_id is None:
            await connection.send_json(
                ErrorMessage(
                    code="not_in_room",
                    message="You must join a room first",
                ).model_dump()
            )
            return

        room = self._rooms.get(player.room_id)
        if room is None:
            return

        await self._broadcast_to_room(
            room=room,
            message=ServerChatMessage(
                player_name=player.name,
                text=text,
            ).model_dump(),
        )

    async def _broadcast_to_room(
        self,
        room: Room,
        message: dict[str, Any],
        exclude_connection_id: str | None = None,
    ) -> None:
        for player in room.players.values():
            if player.connection_id != exclude_connection_id:
                await player.connection.send_json(message)
