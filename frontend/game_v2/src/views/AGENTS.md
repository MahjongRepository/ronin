# Views

The route views: the live game's driver, the replay page and the storybook, each a controller instance per mount
(`frontend/game_v2/AGENTS.md`).

## The live game (`game.ts`)

- The driver alone executes the dispatcher's effects, in order, queueing events raised meanwhile behind the current
  one, and keeps one timer armed to the state's next wake.
- A step, effect or render that throws ends the client as failed on the page, socket closed, error on the console;
  never leave the queue stuck. A protocol failure never throws out of the dispatcher, so a throw is a client bug.

## The replay page (`replay.ts`, `replay-page.ts`, `replay-input.ts`)

- Every page transition is one pure reducer (`replay-page.ts`): stamped input in, screen and requested IO out, which
  the view runs after drawing. Autoplay and a held button's repeat are deadlines in the screen behind one timer
  (`replayPageDeadline`). The reducer reads no DOM; `replay-input.ts` maps keys, wheel and pointer to inputs.
- It moves only through the replay slice's cursor functions.
- The address names position and viewpoint, never reading preferences. It is written with `history.replaceState` at
  most once per 500 ms (Safari's history limit), keeping the page's other parameters (`v=2`); a pending write is
  flushed on page hide and dropped on dispose.
- A step button's press acts on pointer down or the key, so the click that follows is dropped; never let a step fire
  twice. Fields, input-method composition, modifiers and nested controls' own keys are never the page's.
- The load retries a 404 a few times: the game end reaches players before the server saves the replay.
- Only a `DesyncError` while reading counts as a damaged recording; any other throw is a bug and shows the
  cannot-be-shown screen.
- A render that removes or disables the focused control returns focus to the root.
