# Tournament API

The API an external tournament manager uses to start a ronin tournament's games and follow how they end. Only the
tournament's owner can call it. Error values are English and stable; match on them, not on HTTP reason phrases.

## Authentication

The owner generates an API token on the lobby's `/settings` page. It is shown once; generating again rotates it and
the old token stops working. Send it as the `X-API-Key` header on both HTTP routes and on the events socket
handshake. The token grants everything the account can do, so keep it secret.

The two HTTP routes (`POST /api/tournaments/{id}/games` and `GET /api/tournaments/{id}`) accept only the key: a
request without a valid `X-API-Key` gets `401 {"error": "API key required"}`. Send no session cookie: a cookie takes
precedence over the key, so such a request gets the same 401. A tournament that does not exist, or that the key's
account does not own, gets `404 {"error": "tournament_not_found"}` on them. A deleted tournament is gone with its
games: it answers the same 404, and its open events sockets are closed. The events socket has its own rules (see
Events).

## Players

Players take part by opening the tournament's page (`/tournaments/{id}`, the shareable link); while it is open they
are online. The API addresses them by username, matched exactly and case-sensitively against the online usernames.
A player whose game starts leaves the online list at once and comes back online by returning to the page.

## Start games: `POST /api/tournaments/{id}/games`

```json
{"games": [["east", "south", "west", "north"], ["alice", "bob", "carol", "dave"]]}
```

Each table is four distinct usernames, seated in list order: the first is East, then South, West and North. The
manager shuffles seats itself. One request holds 1 to 40 tables, and the body may be at most 4096 bytes; a larger body
gets `413 {"error": "Request body too large"}` and starts nothing.

A malformed body (wrong shape, a table not of four non-empty names, a name repeated in one table, more than 40 tables)
gets one `400 {"error": "..."}` and starts nothing.

Otherwise the answer is `200` with one result per table, in request order. The tables start one after another and
each fails alone, so the other tables still start:

```json
{
  "results": [
    {"game_id": "5c0e...", "players": ["east", "south", "west", "north"]},
    {"error": "players_not_online", "players": ["carol"]}
  ]
}
```

| `error` | Meaning |
| --- | --- |
| `players_not_online` | `players` lists the names not online on the tournament page, including a player a previous table of the same request just started. |
| `players_in_game` | `players` lists the names already in a pending or playing game. |
| `player_in_game` | The game server refused the table because a player is in a game (a race the check above missed); no names. |
| `game_server_full` | The game server holds its capacity of games (100 pending plus playing); retry later. |
| `game_server_unavailable`, `game_server_error`, `internal_error` | The game could not be created; retry later. |

`game_id` is also the game's log (replay) id.

## Snapshot: `GET /api/tournaments/{id}`

```json
{
  "id": "...",
  "name": "Spring Cup",
  "online": ["alice", "bob"],
  "games": [
    {
      "game_id": "5c0e...",
      "players": ["east", "south", "west", "north"],
      "created_at": 1794393000.0,
      "ended_at": 1794395400.0,
      "end_reason": "completed",
      "result": [
        {"name": "west", "seat": 0, "user_id": "...", "score": 41000, "final_score": 51},
        {"name": "east", "seat": 2, "user_id": "...", "score": 28000, "final_score": 8},
        {"name": "north", "seat": 1, "user_id": "...", "score": 19000, "final_score": -21},
        {"name": "south", "seat": 3, "user_id": "...", "score": 12000, "final_score": -38}
      ]
    }
  ]
}
```

`online` is in the order the players came online. `games` is oldest first, `players` East to North. `created_at` and
`ended_at` are epoch seconds. `ended_at`, `end_reason` and `result` are `null` until the game has ended.

- `end_reason` is `completed`, `abandoned` (no player stayed connected) or `error` (the game failed on a server
  error).
- For a completed game, `result` is the final standings in placement order: `score` is the raw score, `final_score`
  the uma/oka-adjusted one. For any other end it lists the four players with `null` scores and no placement.
- `seat` in `result` is the game engine's seat index (0 to 3), not a wind: the first dealer's seat is drawn by the
  game, so East may sit at any index (seat 2 in the example). Only `players` runs East to North.
- `user_id` is the player's lobby account id (empty for an AI seat).
- A completed game has a full replay, a game that ended in `error` may have a partial one, and an abandoned game has
  none.

## Events: `/ws/tournaments/{id}/events`

A WebSocket for the owner, opened with the `X-API-Key` header (no `Origin` header is needed with a key); a signed-in
owner's session cookie also works when the handshake carries the lobby's own `Origin`. It only sends; anything the
client sends is ignored. Several may be open at once. Every message is a JSON object with a `type`:

- `presence` — `{"type": "presence", "players": [...], "count": n}`: who is online. Sent first on connect, then on
  every change.
- `game_started` — `{"type": "game_started", "game_id": "...", "players": [east, south, west, north]}`.
- `game_ended` — `{"type": "game_ended", "game_id": "...", "players": [east, south, west, north], "end_reason":
  "...", "result": [...]}`, with `end_reason` and `result` as in the snapshot, except that `result` entries carry no
  `user_id` (the event also reaches every player on the tournament page). It arrives within a few seconds of the
  game's end.
- `error` — `{"type": "error", "message": "tournament_not_found"}`: the tournament does not exist or the socket's
  account does not own it. The socket then closes with code 4000.
- `error` — `{"type": "error", "message": "tournament_deleted"}`: the owner deleted the tournament on its page. The
  socket then closes with code 4000.

A handshake with neither a valid key nor a session, or a cookie handshake with a foreign `Origin`, is refused with
HTTP 403 before the socket opens; the two cases look the same on the wire.

## Reconciliation and limits

Events are not stored or replayed: a socket only sees what happens while it is open. To follow a tournament without
gaps, connect the events socket first, then read the snapshot, and on a reconnect read the snapshot again.

A game that never started (nobody joined it within the game server's pending timeout) or that was lost to a game
server crash never gets an end: it stays with a `null` `ended_at` in the snapshot and no `game_ended` is sent for it.
Deleting a tournament does not stop its running games: they play on, and no `game_ended` is sent for them.
