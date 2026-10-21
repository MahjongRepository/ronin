# Table entity

The game table model and board UI. The replay view runs on it.

* `TableState` / `PlayerState` (`model/types.ts`) hold the table. `applyEvent(state, event)`
  returns a new state: no mutation, exhaustive dispatch ending in `assertNever`. The draw, discard
  and meld handlers throw on an impossible state (a missing tile, player or caller); a new check
  throws the same way rather than returning the state unchanged. The other handlers tolerate a
  missing player or result.
* `buildTimeline(events)` precomputes every state (`states[i + 1]` follows `events[i]`);
  `buildActionSteps` folds bookkeeping events (`dora_revealed`, `game_started`, the first draw of a
  round) into the preceding step; `buildNavigationIndex` maps steps to rounds and turns.
* `lib/board-mapper.ts` turns a `TableState` into the `BoardDisplayState` the `ui/` components
  render, rotating seats so the dealer sits at the bottom.
* `ReplayEvent` is the subset of events stored in replays; `call_prompt`, `error` and `furiten` never
  appear there.
* Import it through `index.ts`; it may use `entities/tile`, never the reverse.
