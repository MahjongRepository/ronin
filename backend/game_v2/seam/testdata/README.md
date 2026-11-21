# Recorded games

`traces.jsonl.gz` holds recorded reference games, one JSON line per fact. The replay tests
(`internal/replay`) read each game's header and the action of every decision line and play them
through this engine; the event lines are no longer compared with anything, and this engine's events
differ from them on purpose (a furiten change is not shown at a discard that ends the round).

Each game starts with a header line, `{"game":...}`, and the lines after it are, in play order,
every event the driver's sink records and every decision an agent answers:

- a seeded game, `{"game":"seeded","number":n,"seed":"<hex>"}`: seed `0x5a` repeated with `n`
  little-endian in its first 8 bytes, each seat a `RandomLegal` seeded `n*4+seat` when bit `seat`
  of `n` is 0 and `Tsumogiri` otherwise, the self-play agents;
- a fixed-wall game, `{"game":"<name>","walls":[[136 ids]...],"scripts":[[actions] x 4]}`: each
  seat plays the next action of its script whenever it is legal, and its default otherwise.

An event line is `{"to":"all"|seat,"event":"<kind>",<fields>}` and a decision line
`{"decide":seat,"context":{...},"legal":[...],"default":action,"action":action}`. Tile ids and
seats are numbers, an absent value is `null`, enum
values are snake-case names. An action is `"tsumo"`, `"ron"`, `"kyuushu"`, `"pass"`,
`{"discard":id}`, `{"riichi":id}`, `{"pon":[id,id]}`, `{"chi":[id,id]}` or
`{"kan":"closed"|"added"|"open","tile":id}`.

The set holds 16 seeded hanchans and eight fixed-wall games: pao, chankan, triple ron, four kans,
a riichi ron with a dealer renchan over three walls, kyuushu kyuuhai, four winds and four riichi.
They cover every event, round result, abort, decision context, action and value kind.

It is a fixed input: do not regenerate it.
