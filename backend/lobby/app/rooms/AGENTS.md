# Lobby rooms

A room is a pre-game table of 4 fixed seats: `models.py` holds the room and its members,
`manager.py` (`LobbyRoomManager`) the rules, `websocket.py` the per-connection handler, and
`messages.py` the client → server message models. Server → client messages are plain dicts built in
`websocket.py`; they are the wire reference.

* Players see a room by its name, a random word pair picked apart from every open room's; the room
  id stays the identifier in URLs, sockets and logs, and pages never show it.
* A new room seats a tsumogiri bot in every seat; a joining human takes the first bot seat and a
  leaver hands that exact seat back to a bot, so seat positions never shift. Every `players` array
  the server sends lists all 4 seats in seat order, and a bot seat is always ready.
* The first player to join owns the room and is the only one who can start it; the owner cannot
  toggle ready and always shows as ready. The room can start once at least `min_human_players`
  humans (chosen at creation, bot API only) are seated and every non-owner human is ready. Nothing
  starts automatically. When the owner leaves, ownership passes to the earliest remaining joiner.
  The seats are the room's one record of its members; the owner is derived from arrival order, never
  from seat index, since a refilled low seat holds a later joiner. A user rejoining their own seat
  takes it over (`backend/lobby/AGENTS.md`, Occupancy), and the room gets a state resync, not
  `player_joined`/`player_left`.
* Every room step after a join's playing lookup is synchronous because a send is an enqueue, so
  nothing interleaves inside a step and rooms take no lock.
* The owner's start marks the room transitioning, so joins and ready toggles arriving during the
  game server call are refused as transitioning; the start itself is the shared `start_game`
  (`app/game_transition.py`). A failed start reopens the room with every ready flag reset and the reason
  broadcast; a successful one removes it, never retried. The owner's start may ask for strong bots: up to one idle
  standby bot per open seat is claimed from the pool (`app/bot_pool.py`) at Start, and any seat left over stays a
  tsumogiri bot. However the start ends, the claimed bots' standby sockets are closed and they never return to idle;
  a failed start's room messages go only to the members. Every room state message carries
  `strong_bots_available`, a snapshot of the pool that nothing rebroadcasts when the pool changes. A player who leaves a transitioning room
  keeps the seat, because the ticket is already issued and the game server seats AI for a no-show;
  nothing is announced to the room.
* Each connection has its own rate limit (`websocket.py`, `_read_message`), so one client's chat cannot overflow
  a slow honest peer's send queue; a frame over it is dropped and the connection stays. Chat echoes to its
  sender: the browser shows only the echo.
* The last leave removes a room. A room nobody joined expires `unclaimed_room_ttl_seconds` after
  creation, a joined one `room_ttl_seconds` after it: the reaper removes it, sends its players the
  `room_expired` error and closes their sockets with 4002, so the page ends with that notice instead
  of reconnecting. A transitioning room never expires.
* A socket the client closes with 1000 or 1001, or one a revoked credential cut off (4001), is a leave. Any other
  end holds the seat as it was for `seat_grace_seconds` without telling the room, because a page that lost its
  socket could not say it left; the user's reconnect takes it over like any rejoin. A held seat gives way to its
  user's join anywhere else, room or queue, released in the same step once that join has seated or queued the
  user, so a refused join keeps it.
