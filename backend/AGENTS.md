# Backend

The lobby (`lobby/`) and the game server (`game_v2/`) share the SQLite database, the game ticket secret (the lobby signs tickets, the game server
verifies them) and the internal API secret (the lobby's bearer token on the game server's
credential-returning lookup).
