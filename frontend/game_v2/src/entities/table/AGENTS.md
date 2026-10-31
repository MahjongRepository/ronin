# Table entity

The game table model and board UI. `entities/client` steps it; views read the tables it produces.

- `applyEvent` is the table's only transition: readonly state in, a new table out. Nothing in this slice folds a
  sequence of events.
- The table holds what its source showed, never a second model per source: a live seat knows only its own tiles, so
  other hands are counts; a replay shows every hand. Another seat's draw moves the table when its notice arrives,
  never inferred from a later discard. A draw of a tile the hand already holds is a reconnect's re-send: it takes
  nothing from the wall.
- A kan open to chankan shows as declared (`kan_declared`) before it resolves, with no replacement draw or dora; the
  meld that completes it takes nothing more from the hand.
- **Out of order is a desync.** `PHASES_TAKING` checks every event's phase before any handler runs. A handler that
  meets an impossible state throws `DesyncError`, never returns the state unchanged: the live client recovers from
  that error alone.
- **Scores come from the server.** A round end's wire `scores` are pre-payment and post-deposit; settle each player at
  that score plus `scoreChanges`, never from the prior state, so a deposit is never deducted twice. Riichi cost
  (`riichiCost`) and a collected stick's value (`riichiStickValue`) are separate game settings. A snapshot's scores
  already hold every deposit and a game end's standings the leftover sticks paid; take both as they are. The game's
  end takes the server's placement and uma/oka, never recomputed; leftover sticks are the server's `lr`, never the
  table's count. A table out of step (`inStep`) names no last round in how the game ended.
- A limit's name (`handLimitName`) comes from the points paid, never from han; yakuman vs kazoe from the server's
  per-yaku flag, never the id.
- A round's name is its number within its wind (`roundInWind`), from the dealer's distance to the first dealer.
- The latest discard is the server's on reconnect (`ld`); the client never infers it.
- An AI stand-in for an absent human (`aiStandIn`, "Away") is never shown as an AI participant ("AI").
- The board marks no tile playable and no offer source: that is the client mapper's.
- The seating panel is the game's start and its end: the seats in wind order before the first deal, then in
  placement order with their scores and uma/oka results once the game ends.
- `model/replay-file.ts` refuses a file whose version is not `REPLAY_VERSION` and reports a bad or live-only line,
  never skipping it into a recording that looks whole.
