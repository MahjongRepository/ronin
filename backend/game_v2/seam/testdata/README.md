# Game trace reference set

`traces.jsonl.gz` holds games played by mahjong-rs, one JSON line per fact, which the seam test
`TestPlayGameChecked_WhenReplayingTheReferenceTraces_ShouldOfferTakeAndEmitExactlyTheSame` replays
through the facade and the ported driver, comparing every line byte for byte.

Each game starts with a header line, `{"game":...}`, and the lines after it are, in play order,
every event the driver's sink records and every decision an agent answers:

- a seeded game, `{"game":"seeded","number":n,"seed":"<hex>"}`: seed `0x5a` repeated with `n`
  little-endian in its first 8 bytes, each seat a `RandomLegal` seeded `n*4+seat` when bit `seat`
  of `n` is 0 and `Tsumogiri` otherwise, the self-play agents;
- a fixed-wall game, `{"game":"<name>","walls":[[136 ids]...],"scripts":[[actions] x 4]}`: each
  seat plays the next action of its script whenever it is legal, and its default otherwise.

An event line is `{"to":"all"|seat,"event":"<kind>",<fields>}` and a decision line
`{"decide":seat,"context":{...},"legal":[...],"default":action,"action":action}`. Field names
and order are mahjong-rs's; tile ids and seats are numbers, an absent value is `null`, enum
values are snake-case names. An action is `"tsumo"`, `"ron"`, `"kyuushu"`, `"pass"`,
`{"discard":id}`, `{"riichi":id}`, `{"pon":[id,id]}`, `{"chi":[id,id]}` or
`{"kan":"closed"|"added"|"open","tile":id}`. `seam/trace_json_test.go` is the Go writer of the
same forms.

The set holds 16 seeded hanchans and eight fixed-wall games: pao, chankan, triple ron, four kans,
a riichi ron with a dealer renchan over three walls, kyuushu kyuuhai, four winds and four riichi.
They cover every event, round result, abort, decision context, action and value kind; the dumper
fails when one is missing and prints how often each appeared.

It was written by mahjong-rs's `game_traces` example at commit `ce617b3` (branch
`go-port-dumpers`; the engine is that of `0d8733f`). Regenerate it only when mahjong-rs's engine
changes on purpose, from the mahjong-rs repository root:

    cargo run --release -q -p mahjong-game --example game_traces | gzip -9n > traces.jsonl.gz
