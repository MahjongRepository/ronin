# Tournament API

The API an external tournament manager uses to start a ronin tournament's games and follow how they end. Only the
tournament's owner can call it. Error values are English and stable; match on them, not on HTTP reason phrases.

## Authentication

The owner generates an API token on the lobby's `/settings` page. It is shown once; generating again rotates it and
the old token stops working. Send it as the `X-API-Key` header on every request and on the events socket handshake.

The API accepts only the key: a request without a valid `X-API-Key` gets `401 {"error": "API key required"}`. Send no
session cookie: a cookie takes precedence over the key, so such a request gets the same 401. The token grants
everything the account can do, so keep it secret.

A tournament that does not exist, or that the key's account does not own, gets
`404 {"error": "tournament_not_found"}` on every route below.

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
        {"name": "west", "seat": 2, "user_id": "...", "score": 41000, "final_score": 51},
        {"name": "east", "seat": 0, "user_id": "...", "score": 28000, "final_score": 8}
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
  the uma/oka-adjusted one. For any other end it is the players in seat order with `null` scores.
- A replay exists only for a completed game.

## Events: `/ws/tournaments/{id}/events`

A WebSocket for the owner, opened with the `X-API-Key` header (no `Origin` header is needed with a key). It only
sends; anything the client sends is ignored. Several may be open at once. Every message is a JSON object with a
`type`:

- `presence` — `{"type": "presence", "players": [...], "count": n}`: who is online. Sent first on connect, then on
  every change.
- `game_started` — `{"type": "game_started", "game_id": "...", "players": [east, south, west, north]}`.
- `game_ended` — `{"type": "game_ended", "game_id": "...", "players": [east, south, west, north], "end_reason":
  "...", "result": [...]}`, with `end_reason` and `result` as in the snapshot. It arrives within a few seconds of the
  game's end.
- `error` — `{"type": "error", "message": "tournament_not_found"}`, then the socket closes with code 4000. A handshake
  without a valid key is refused with 4001.

## Reconciliation and limits

Events are not stored or replayed: a socket only sees what happens while it is open. To follow a tournament without
gaps, connect the events socket first, then read the snapshot, and on a reconnect read the snapshot again.

A game that never started (nobody joined it within the game server's pending timeout) or that was lost to a game
server crash never gets an end: it stays with a `null` `ended_at` in the snapshot and no `game_ended` is sent for it.
