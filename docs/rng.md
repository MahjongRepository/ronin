# Game randomness

How a game gets its random outcomes: the wall of each round, the first dealer and the seating. The
code is `backend/game/logic/rng.py`; the wall cut is in `wall.py`; `make measure-wall` measures it.

## One seed per game

Each game starts with 96 random bytes (768 bits) from the operating system (`secrets.token_bytes`),
stored as 192 hex characters. Everything random in the game is computed from this seed, so the
replay file stores the seed and can replay the game from it.

The seed is secret while the game runs and public with the replay after it. Anyone can recompute
every wall from it and compare with the log.

## The word stream

Random values are never read from the seed directly. Each use has its own stream of 64-bit words:

```
SHAKE256( domain || seed || extra )
```

SHAKE256 is a hash that can produce as many output bytes as needed. The domain is a fixed string
per use, so the three uses never share words:

| use | domain | extra |
|---|---|---|
| wall and dice of a round | `ronin-wall-shake256-v1:` | the round number |
| first dealer | `ronin-dealer-shake256-v1:` | none |
| seating | `ronin-seat-shake256-v1:` | none |

The round number grows after every hand, renchan included, so every hand reads a different stream.
With a secret random seed the words are unpredictable, which is why the seed stays secret until the
game ends.

## Uniform numbers

To get a number in `[0, n)`, the engine reads a 64-bit word, throws it away if it falls in the
small incomplete bucket at the top of the 64-bit range, and otherwise returns `word mod n`. This is
rejection sampling: every value in `[0, n)` is exactly equally likely. Plain `word mod n`, which
Tenhou's published sample uses, makes small values slightly more likely.

## The wall of a round

The 136 tile ids (four copies of 34 types; ids 16, 52 and 88 are the red fives) are shuffled with
Fisher-Yates: for each position `i` from 0 to 134, draw a uniform `j` in `[i, 136)` and swap `i`
with `j`. With uniform draws every ordering is equally likely. Then two dice are drawn from the same
stream.

The shuffled list is the ring of 68 stacks: stack `k` holds `shuffled[2k]` on top and
`shuffled[2k+1]` below, and seat `s` owns stacks `17s..17s+16`. The dice pick the break; the seven
stacks from the break are the dead wall (two rinshan stacks, then five dora stacks), and the live
wall starts left of the break. Hands are dealt from the front of the live wall, four tiles at a
time from the dealer, then one each; the dealer's first draw is the next tile.

## The first dealer

The dealer stream simulates the two-throw rule of the table: seat 0 throws two dice, the sum picks a
temporary dealer; that seat throws again, and the sum picks the first dealer. This is slightly
uneven on purpose, as at a real table: the seats get 326, 324, 322 and 324 chances out of 1296,
within 0.16 percentage points of 25%. Seating is random too, so each player still has a 25% chance
of being the first dealer.

## Seating

The seat stream shuffles the four seats with the same Fisher-Yates routine. Players take the first
entries of the result in input order; the remaining seats go to AI players. The replay loader
inverts this permutation, so the seating rule is part of the replay format.

## Versioning

`RNG_VERSION` (`shake256-v1`) is written into every replay. Any change to the above is a new
version. The replay loader rejects other versions, so an old replay needs the code that recorded it.

## How much randomness there is

| quantity | bits |
|---|---|
| orderings of 136 labelled tiles | 772.6 |
| walls that look different (copies of a type are the same, red fives differ) | 622.7 |
| seed | 768 |

For one round the seed has more bits than there are different walls, so the seed size does not
limit which walls can appear. For a whole game all rounds come from one seed, so not every
combination of walls across rounds is reachable. That is true of any seeded generator, is not
detectable in play, and a longer seed would not change it.

The seed proves that the game matches the seed. It does not prove that the server did not pick the
seed. Proving that needs a commitment before the game (a hash of the seed, or a published list of
hashes as Tenhou does); the engine does not do this today.

## Measured results

`make measure-wall` samples games through these functions and compares each statistic with its
expected value. The default run (5000 games of 4 rounds, 20000 walls, experiment seed 0, about
three seconds) reports for `shake256-v1`:

| statistic | observed | expected |
|---|---|---|
| tile id by wall position, worst of 18496 cells, tail × cells | 0.57 | warn below 0.001 |
| adjacent tiles of the same type per wall | 3.001 | 3.000 |
| same-type pairs in a 13-tile hand | 1.731 | 1.733 |
| honours in a 13-tile hand | 2.682 | 2.676 |
| red fives in a 13-tile hand | 0.286 | 0.287 |
| positions with the same tile id in consecutive rounds | 1.008 | 1.000 |
| mean shanten of a 13-tile hand, engine / control | 3.582 / 3.574 | equal within noise |
| mean shanten of the dealer's 14 tiles, engine / control | 3.160 / 3.158 | equal within noise |
| dice, first-dealer seats, seat permutations | all ok | exact |
| identical walls in consecutive rounds | 0 of 15000 | 0 |

Starting-hand shanten of that run, as counts (80000 13-tile hands and 20000 dealer hands per side):

| shanten | 13 tiles, engine | 13 tiles, control | dealer's 14, engine | dealer's 14, control |
|---|---|---|---|---|
| -1 (complete) | | | 0 | 0 |
| 0 (tenpai) | 6 | 6 | 10 | 18 |
| 1 | 477 | 510 | 473 | 464 |
| 2 | 7447 | 7669 | 3819 | 3888 |
| 3 | 28950 | 28887 | 8866 | 8766 |
| 4 | 31950 | 31859 | 5699 | 5730 |
| 5 | 10490 | 10419 | 1106 | 1110 |
| 6 | 680 | 650 | 27 | 24 |

A warning in the report has at most a 0.1% chance per family under a correct generator, so it is a
reason to rerun with another `--experiment-seed`, not a finding. To test a change, save a run with
`--json`, change the code, and rerun with `--baseline` and a different experiment seed.

## Comparison with a naive shuffle

To show what the script catches, the same measurement was run once (throwaway code, not in the
repo) on the common wrong shuffle: for each position `i` from 0 to 135, swap it with
`randint(0, 135)` over the whole wall instead of `[i, 136)`. It looks random, but it produces
`136^136` equally likely swap sequences spread over `136!` orderings, which do not divide evenly.
Computed exactly, tile 1 lands on position 0 with 1.36 times its fair chance and tile 135 with
0.74 times; the engine's Fisher-Yates gives every tile exactly `1/136` at every position.

| statistic | engine, 20000 walls | naive, 20000 walls | naive, 100000 walls |
|---|---|---|---|
| tile id by position, worst cell z | 4.0, ok | 6.7, warn | 11.7, warn |
| tile type by position, worst cell z | 3.4, ok | 10.6, warn | 19.4, warn |
| adjacent tiles of the same type per wall (3.000) | 3.001 | 3.039 | 3.039, warn |
| same-type pairs in a 13-tile hand (1.733) | 1.731 | 1.740 | 1.746, warn |
| mean shanten of a 13-tile hand, vs control | 3.582 vs 3.574 | 3.568 vs 3.574 | 3.571 vs 3.581, warn |

The naive shuffle fails the position checks at the default size. Its effect on hands is small, a
few hundredths of a shanten, and shows only at 100000 walls: this is why the script measures tile
positions rather than only hand quality.

## Where the expected values come from

All references follow from one model: a uniformly random ordering of the 136 tiles and fair dice.
None come from the engine itself.

- **Tile by position, dora type, seat permutation:** uniform, by symmetry.
- **Adjacent same-type tiles:** 135 neighbouring pairs, each the same type with probability 3/135
  (three other copies among 135 tiles), so 3.0 per wall.
- **Same-type pairs in a hand:** C(13, 2) × 3/135 = 1.733.
- **Honours and red fives in a hand:** 13 × 28/136 = 2.676 and 13 × 3/136 = 0.287.
- **Consecutive rounds:** two independent walls agree at a position with probability 1/136, so 1.0
  of 136 positions.
- **Dice:** 1/6 per face; sums follow the triangle 1, 2, ..., 6, ..., 2, 1 out of 36.
- **First dealer:** the two-throw rule counted over all 1296 pairs of throws.
- **Shanten:** no formula exists, so the reference is the same shanten calculator run over hands
  from Python's `random.shuffle`. This compares the engine's shuffle with an independent one.
