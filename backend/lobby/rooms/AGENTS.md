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
  instead of waiting. It then signs a ticket per human, calls the game server's `POST /games` (with
  `num_ai_players` from the bot seats), and sends each player `game_starting`. On failure it clears
  `transitioning`, which resets the ready flags, and rebroadcasts the room state.
* Every room expires `room_ttl_seconds` (300s) after creation unless it is transitioning; the
  manager's reaper removes it and `on_room_expired` disconnects its players.
