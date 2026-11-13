# Zone review: finding board problems yourself

A pass of the visual check or "looks fine" at one size proves nothing. Before you call board work done, review it
zone by zone the way an independent reviewer would, fix what you find, and repeat until no blocker or major is left.

## Shoot a matrix, not one shot

- Window shapes: a large 16:9 (`desktop-large`, 2560x1440), a 16:10 (`desktop-1440`), a near-4:3 (`window-900` or
  1024x768), a laptop browser window (`laptop-window-1366x657`) and a browser-boxed phone (`phone-11-safari`).
- States: an ordinary one (`board-full-hands`) and the densest (`board-worst`).
- Many problems only show on one shape (a gap on 16:10 alone, a card collapsing only on big screens).

## Measure every zone, at 2-3x crops

Zones: top, left and right strips (hand and melds); the four rivers; the centre; the plates and names; the own row;
the decisions band; corners and bars (dora card, counters, cog); the felt and its seams. For each, write down numbers
in the shot's pixels:

- **Gaps between neighbours:** top strip to top river; each river to the centre; river to plate; between meld groups
  and the hand in a strip; strip ends to the own row. A gap under ~8px on desktop reads as touching. Compare with the
  base board: a gap that shrank is a finding.
- **Sizes:** each zone's tile against the own tile. Nothing outside the own row may rival the own hand. Check the
  river-to-own ratio, plate height and tap area (at least 40px), and the dora tiles' size.
- **Drawn against reserved:** an edge, shadow or stack drawn thicker than the geometry reserves eats the gaps.
  Compare the CSS depth with what the solve reserves.
- **Consistency across shapes:** the same zone must keep the same placement and form at every size, such as the top
  inset, the dora card's layout or a strip's end. A layout choice that flips between sizes is a bug.
- **Consistency across zones:** the same tiles must read as the same material everywhere, flat and tilted alike. All
  tilted parts must share one camera, and flat parts must sit plausibly in front of it.

## Read the code for what the shots can't show

- **Stacking:** a `transform`, `filter` or `isolation` creates a stacking context. Children inside it lose their
  z-layer against everything outside, such as callouts under decisions.
- **Hidden misfits:** `overflow: clip` or `hidden` on a page hides overflow. The fit must be exact without it.
- **Solver behaviour:** probe the geometry across a grid of window sizes with a throwaway vitest in the scratchpad.
  Check that loops converge (a fixed iteration count with no check is a finding), that nothing letterboxes, and
  which placement branch each size takes. Then turn the important cases into real tests.
- **Cliffs against the base:** sweep thousands of sizes numerically, phones and desktops, on a regular grid and on an
  offset half-step grid, against the commit you started from. Diff own tile, river tile and tilt per size: a size
  that loses tile, goes flat, or flips back and forth against its neighbours is a finding, even below the
  smallest named viewport. A rule checked by a boolean (fits or not) misses a fallback that got worse; compare the
  fallback's placement too.
- **Motion:** compare a flight's start and landing pose with the slot's resting look (size, edge, rotation, skew), on
  every path a tile takes: replay and live game (a live hand is buttons, which the storybook hands are not), draw,
  discard, call and reflow. In WebKit, read flight frames from one persistent labelled screencast and seek twice per
  frame; a single seek can paint the previous position.
- **Machine load:** WebKit draws the tilted board in software at several cores per browser. Run one browser at a
  time and close it when done.

## Grade and loop

Grade each finding:
- **blocker:** broken, clipped or unusable;
- **major:** clearly wrong at a normal size, such as touching zones, collapsed chrome, a mismatched material, or
  something rivalling the own hand;
- **minor:** polish.

Fix the blockers and majors, reshoot the same matrix, and review again. Stop when your own review finds no blocker or
major. Then report the remaining minors honestly with your shots: the lead's independent reviewers run after you.
