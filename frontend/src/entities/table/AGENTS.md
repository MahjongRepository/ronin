# Table entity

The game table model and board UI. The replay view and the storybook run on it.

- `TableState` / `PlayerState` (`model/types.ts`) hold the table; `applyEvent` (`model/`) returns
  the next state. The draw, discard and meld handlers throw on an impossible state (a missing tile,
  player or caller); a new check throws the same way rather than returning the state unchanged. The
  other handlers tolerate a missing player or result.
- `buildTimeline` precomputes the state after every event; `buildActionSteps` picks the replay's
  stop points, folding bookkeeping events (a new dora, game start, the first draw of a round) into
  the neighbouring step so navigation lands on meaningful moments; `buildNavigationIndex` maps
  steps to rounds and turns.
- `lib/board-mapper.ts` turns a `TableState` into the display state the `ui/` components render,
  rotating seats so the dealer sits at the bottom.
- `ReplayEvent` is the subset of protocol events a replay stores; prompts, errors and furiten
  notices never appear there.
