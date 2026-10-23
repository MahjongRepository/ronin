# Lobby rooms

A room is a pre-game table of 4 fixed seats: `models.py` holds the room and its members,
`manager.py` (`LobbyRoomManager`) the rules, `websocket.py` the per-connection handler, and
`messages.py` the client → server message models. Server → client messages are plain dicts built in
`websocket.py`; they are the wire reference.

* A new room seats a tsumogiri bot in every seat; a joining human takes the first bot seat and a
  leaver hands that exact seat back to a bot, so seat positions never shift. Every `players` array
  the server sends lists all 4 seats in seat order, and a bot seat is always ready.
* The first player to join owns the room and is the only one who can start it; the owner cannot
  toggle ready and always shows as ready. The room can start once at least `min_human_players`
  humans (chosen at creation, bot API only) are seated and every non-owner human is ready. Nothing
  starts automatically. When the owner leaves, ownership passes to the earliest remaining joiner.
* Every room step after a join's playing lookup is synchronous because a send is an enqueue, so
  nothing interleaves inside a step and rooms take no lock.
* The owner's start marks the room transitioning, so joins and ready toggles arriving during the
  game server call are refused as transitioning; the start itself is the shared `start_game`
  (`lobby/AGENTS.md`). A failed start reopens the room with every ready flag reset and the reason
  broadcast; a successful one removes it, never retried. A player who leaves a transitioning room
  keeps the seat, because the ticket is already issued and the game server seats AI for a no-show;
  nothing is announced to the room.
* Each connection has its own rate limit, charged for every frame before it is decoded, invalid ones
  included; a frame over it is answered rate-limited and dropped, and the connection stays. It
  keeps one client's chat from overflowing a slow honest peer's send queue. A binary frame gets an
  error and the connection stays. Chat echoes to its sender: the browser shows only the echo.
* Every room expires `room_ttl_seconds` after creation unless it is transitioning. A reaper tick
  removes every expired room and closes its members' sockets in one pass; a failed tick is logged
  and the next one still runs.
