# Lobby rooms

A room is a fixed 4-seat table (`LobbyRoomManager`, `models.py`). Messages are JSON text frames,
modelled in `messages.py` (client → server) and built in `websocket.py` (server → client).

* Creating a room fills every seat with a tsumogiri bot; each joining human replaces the first bot
  seat. Every `players` array holds exactly 4 entries in seat order, and bot seats are always ready.
* The first player to join owns the room (`host_connection_id`) and is the only one who starts it:
  non-owners send `set_ready`, the owner sends `start_game`. `can_start` is true once at least `min_human_players` humans are seated
  (bot API, 1–4, default 1) and every non-owner human is ready. Nothing starts automatically. When
  the owner leaves, ownership passes on (`owner_changed`).
* Every room step after a join's playing lookup is synchronous (a send is an enqueue): the join
  with its ack and broadcast, `set_ready`, chat, the start's flag, the cleanup with its host
  transfer, the recovery and the reaper tick. Nothing interleaves inside a step, so rooms take no
  lock, and a joiner is registered in the step that seats it.
* Game transition: the owner's `start_game` sets `transitioning=True` in one step, so joins and
  ready toggles arriving during the network call get `room_transitioning`. The host's handler then
  runs the shared `start_game` (`lobby/AGENTS.md`) for every seated human, with `num_ai_players`
  from the bot seats. On `GameStartError` it clears `transitioning`, which resets the ready flags,
  and rebroadcasts the room state and `Failed to start game: <reason>`; a cancellation (only server
  shutdown causes one) does not. After a 201 every seated player already has `game_starting` and a
  1000 close queued, and the room is removed: transitioning is never cleared, the state never
  rebroadcast and creation never retried.
* A player who leaves a transitioning room keeps the seat: the ticket is already signed and sent
  in `POST /games`, and the game server replaces that seat, whose human never gets `ws_url` or the
  ticket, with AI. There is no host transfer, no `owner_changed` or `player_left`, no
  `game_starting` for the leaver, and the room is not dropped when it empties. The transition
  settles those seats: a failed start releases them, a successful one removes the room. The host
  runs the transition in its own handler and cannot leave during it, so a failed start never
  empties the room; `clear_transitioning` still drops a room left empty, as the manager's own rule.
* A slow or dead socket never holds up or costs another player anything. A room's members are its
  `RoomMember`s (the `LobbyPlayer` plus the room-only `ready` and `departed`), and a broadcast
  encodes once and enqueues on each member's connection (`lobby/AGENTS.md`, `players.py`). A
  handler ends normally on `ConnectionError`, which its next receive raises once the peer is gone,
  its writer dropped it, or a queued close went out. The joiner's own `room_joined` ack runs inside
  the handler's `try/finally`, so a failed ack frees the seat and the host.
* Every room expires `room_ttl_seconds` (300s) after creation unless it is transitioning. Each
  reaper tick removes every expired room and enqueues a 4002 close for each member in one pass, so
  one room's slow socket never delays another room's expiry. A failed reaper tick is logged and the
  next one still runs.
