# Views

The route views: the live game's driver, the replay page and the storybook, each a controller instance per mount
(`frontend/game_v2/AGENTS.md`).

## The live game (`game.ts`)

- The driver alone executes the dispatcher's effects, in order, queueing events raised meanwhile behind the current
  one, and keeps one timer armed to the state's next wake.
- A step, effect or render that throws ends the client as failed on the page, socket closed, error on the console;
  never leave the queue stuck. A protocol failure never throws out of the dispatcher, so a throw is a client bug.

## The replay page (`replay.ts`, `replay-input.ts`)

- A view holds no state machine: the page's screen and every transition are the replay slice's (`stepReplayPage`).
  The view stamps each input with the clock's time, draws the screen it gets back, runs the IO it asks for after
  drawing, and keeps one timer armed to `replayPageDeadline`. `replay-input.ts` maps keys, wheel and pointer to
  inputs. The board is the slice's `ReplayBoard`; the view adds only the page around it.
- It finds the slices' parts (round list, its toggle, the board's panel and notices, step buttons) only by the
  selectors and attributes those slices export, never by their classes.
- The address names position and viewpoint, never reading preferences. It is written with `history.replaceState` at
  most once per 500 ms (Safari's history limit), keeping the page's other parameters (such as `debug`); a pending write is
  flushed on page hide and dropped on dispose.
- A step button's press acts on pointer down or the key, so the click that follows is dropped; never let a step fire
  twice. Fields, input-method composition, modifiers and nested controls' own keys are never the page's.
- The load retries a 404 a few times: the game end reaches players before the server saves the replay.
- Only a `DesyncError` while reading counts as a damaged recording; any other throw is a bug and shows the
  cannot-be-shown screen.
- A render that removes or disables the focused control returns focus to the root.
