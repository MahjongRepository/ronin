# Lobby rooms

A room is a fixed 4-seat table (`LobbyRoomManager`, `models.py`). Messages are JSON text frames,
modelled in `messages.py` (client → server) and built in `websocket.py` (server → client).

* Creating a room fills every seat with a tsumogiri bot; each joining human replaces the first bot
  seat. Every `players` array holds exactly 4 entries in seat order, and bot seats are always ready.
* The first player to join owns the room (`host_connection_id`) and is the only one who starts it:
  non-owners send `set_ready`, the owner sends `start_game`. `can_start` is true once at least `min_human_players` humans are seated
  (bot API, 1–4, default 1) and every non-owner human is ready. Nothing starts automatically. When
  the owner leaves, ownership passes on (`owner_changed`).
* Game transition: under the room's `join_lock` the lobby only sets `transitioning=True`, then
  releases the lock before any network call, so joins arriving meanwhile get `room_transitioning`
  instead of waiting. It then signs a ticket per human and calls the game server's `POST /games`
  (with `num_ai_players` from the bot seats). Before a 201, any exception clears `transitioning`,
  which resets the ready flags, and rebroadcasts the room state; a cancellation (only server
  shutdown causes one) does not. After a 201 the game exists with
  every signed ticket and a retry would get 409: `game_starting` goes best-effort to every seated
  player, then the room is removed and its connections closed whatever happens. Transitioning is
  never cleared, the state never rebroadcast and creation never retried.
* A player who leaves a transitioning room keeps the seat: the ticket is already signed and sent
  in `POST /games`, and the game server replaces that seat, whose human never gets `ws_url` or the
  ticket, with AI. There is no host transfer, no `owner_changed` or `player_left`, no
  `game_starting` for the leaver, and the room is not dropped when it empties. The transition
  settles those seats: a failed start releases them (and drops a room left empty), a successful one
  removes the room.
* A dead socket never costs another player their seat. Room sends and closes go through
  `send_or_drop` / `close_quietly` (`lobby/websocket_utils.py`): a failed send to a dead peer is
  logged at info and skipped, a failed close is ignored, fan-out continues, and the exception never
  reaches the sender's handler. A handler ends normally on `WebSocketDisconnected` as on
  `WebSocketDisconnect`: it is what its next receive raises once another task closed its socket.
  The joiner's own `room_joined` ack runs inside the handler's `try/finally`, so a failed ack frees
  the seat and the host.
* Every room expires `room_ttl_seconds` (300s) after creation unless it is transitioning. The
  manager's reaper re-checks each expired room under its `join_lock`, and removes it and has
  `on_room_expired` disconnect its players while holding the lock. A join in progress is therefore
  registered before the close, and a start that won the lock keeps its room. A failed reaper tick is
  logged and the next one still runs.
