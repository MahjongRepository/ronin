# Views

The route views: the live game's driver, the replay page and the storybook. Each is a controller instance per mount
(the app's `AGENTS.md`, App).

## The live game (`game.ts`)

- The driver alone executes the dispatcher's effects, in order, queueing the events raised while they run behind the
  current one, and keeps one timer armed to the state's next wake (`shared/lib`'s `createDeadlineTimer`, shared with
  the replay page), which comes back as a tick. It keeps the socket's silence limit on the client's policy
  (`entities/client/AGENTS.md`, Desync).
- A step, an effect or a render (its own redraws, a load's or a command's, included) that throws ends the client as
  failed, on the page, with the socket closed and the error on the console whatever the debug log, rather than
  leaving its queue stuck; where drawing the failed state throws too, the page shows a bare notice with a reload and
  draws nothing more. A socket factory that throws is reported as a failed connection. A protocol failure never
  throws out of the dispatcher, so what does is a bug in the client.
- The live standings lead to the last result, this game's replay from the player's seat (the page's `v` kept), the
  game history and the lobby (the leave intent); the view is given the links (`GameLinks`).

## The replay page (`replay.ts`, `replay-page.ts`, `replay-input.ts`)

- It opens where its address says, else on the first deal, and moves only through the table slice's cursor functions
  (`entities/table/AGENTS.md`); its view state is the cursor, the seat at the bottom, the round list's openness, the
  pinned plate, autoplay, a held step button, the wheel's gesture and whether the other hands hide.
- Every transition of the page, its load's answers and failure screen included, is one pure reducer the page owns
  (`replay-page.ts`, never the table slice, which has no other consumer of it): an input stamped with the clock's
  logical time in, the screen and the IO it asks for out (the address written, the reader's settings saved, the focus
  moved), which the view runs after drawing. Autoplay's next move and a hold's next repeat are deadlines in the
  screen, as the live client's are: the view keeps one timer armed to the earliest (`replayPageDeadline`), which comes
  back as a tick, and a tick before it does nothing. The reducer reads no DOM: what a key, the wheel or a held
  button's pointer means is the input mapping's (`replay-input.ts`), and the view keeps the IO, the DOM focus, the
  pointer capture and the timer.
- Autoplay, a held step button (repeating from a pointer's press, under its capture, waiting while the pointer is off
  it) and a turning wheel all pause where a result shows (each page of a double ron) and at the end, and autoplay also
  stops on any move the reader makes, as the page hides and on dispose; any other move and autoplay's start end a
  hold. A press's step is its own, so only the click that press ends in is dropped, never a keyboard's or an
  assistive technology's. The wheel steps by gesture, not by event (`shared/lib/wheel-steps.ts`): a first step at a
  mouse notch's distance, then each further stretch and beat, a rest or a turn back starting over.
- Keys are the root's: arrows step and move rounds, Home/End go to either end, Space switches autoplay except on a
  control it activates itself, V and H (by key position) switch the view and the hands, each switch once per press;
  Enter and Space on a step button are that step, prevented so the button never clicks too, and so held they pause as
  a held arrow does; a field, an input method's composition, a modifier, the round list's and the standings' own keys
  and the keys that scroll a round's result scrolling in its panel are never the page's. A render that takes away or
  disables the focused control gives the focus back to the root.
- The viewpoint switch moves the seat at the bottom and the address's `seat`, never the cursor or a result's page.
  Hiding the hands draws the board and the narration as the bottom seat sees them. That and autoplay's speed are the
  reader's settings (read by `entities/table/model/replay-prefs.ts`, kept by the entry in `localStorage` through
  `shared/lib`'s `localStore`, the defaults when it is blocked), never the address: the address names a position, and a shared link imposes no way of
  reading it.
- Its IO stays at the edge, given by `index.ts`: the load, which asks again on 404 after 500, 1000 and 2000 ms (the
  game end reaches players before the server saves the replay) and is aborted with its waiting retry on dispose; and
  the address, kept on the position shown with `history.replaceState` at most once per 500 ms (Safari's history
  limit), the page's other parameters (`v=2`) kept, a waiting write flushed as the page hides and dropped on dispose,
  since a dispose follows a navigation.
- A replay it cannot show (not found after the retries, refused, unreachable, another version, no deal) gets a screen
  saying why with the way back to the game history and the lobby, and a retry where one may help: only a failed fetch
  counts as unreachable, while a throw in reading or drawing the replay, as it loads or at any later move (a press, a
  key, the wheel, a hold's or autoplay's timer), says it cannot be shown, its error on the console, with no retry,
  autoplay and a hold stopped. Reading takes only a `DesyncError` as a damaged recording (`entities/client`'s
  `readReplayTimeline`); any other throw is a bug, so it reaches that screen rather than passing for damage.
- The wheel steps only over the board, outside the round list, the standings' rounds, the notices' place and a
  round's result scrolling in its panel, and only where a step goes; anywhere else it scrolls. The narration is read
  out by a live region of its own, polite and left empty while autoplay runs (`styles/AGENTS.md`, the replay's
  controls).
- The replay's standings lead to the game history and the lobby, and each round's row is a button to its result
  (`roundResultCursor`), after which the focus returns to the replay's root, so its arrow keys go on.
