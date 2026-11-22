# Game randomness

This document explains how a game gets its random results: the wall of each round, the first dealer
and the seats of the players.

- `backend/game_v2/engine/internal/rng` in the Go engine holds the seed. From the seed it makes the
  order of the seats, the first dealer, and the shuffle and dice of each round.
- `engine/internal/wall` splits the shuffled tiles into the live wall and the dead wall.
- The session (`backend/game_v2/internal/session`) creates the seed and gives the players their
  seats. It does this through the seed functions of the engine facade.
- `make measure-wall` measures the results with `backend/game_v2/cmd/measurewall`.

## One seed per game

Each game starts with a seed: 96 random bytes (768 bits) from the operating system (Go's
`crypto/rand`). When the seed is shown or parsed, it is written as 192 hex characters. All random
results of the game are computed from this seed. The replay file stores the 96 bytes, so the game
can be replayed from them.

The seed is secret while the game runs. After the game it is public, in the replay. Anyone can then
compute every wall from the seed and compare it with the log.

## The word stream

The engine never reads random values from the seed directly. Each use has its own stream of 64-bit
words:

```
SHAKE256( domain || seed || extra )
```

SHAKE256 is a hash function that can give as many output bytes as needed. `||` means that the parts
are joined one after another. The domain is a fixed text, different for each use, so two uses never
get the same words:

| use | domain | extra |
|---|---|---|
| wall and dice of a round | `ronin-wall-shake256-v1:` | the round number |
| first dealer | `ronin-dealer-shake256-v1:` | none |
| seating | `ronin-seat-shake256-v1:` | none |

The round number goes up by one after every hand, also after a renchan (a hand where the dealer
stays). So every hand reads a different stream. The seed is secret and random, so nobody can
predict the words. This is why the seed must stay secret until the game ends.

## Uniform numbers

To get a number from 0 to n-1, the engine reads a 64-bit word. The number of possible words, 2^64,
is usually not a multiple of n, so the highest words form an incomplete group. If the word is in
this group, the engine skips it and reads the next word. Otherwise it returns `word mod n`. This
method is called rejection sampling. With it, every number from 0 to n-1 has exactly the same
chance. Plain `word mod n`, without the skip, gives small numbers a slightly higher chance.

## The wall of a round

There are 136 tile ids: four copies of each of the 34 tile types. Ids 16, 52 and 88 are the red
fives. The engine shuffles the ids with the Fisher-Yates method: for each position `i` from 0 to
134, it picks a uniform random `j` from `i` to 135 and swaps the tiles at `i` and `j`. Because the
picks are uniform, every order of the tiles has the same chance. After the shuffle, the engine
rolls two dice from the same stream.

The shuffled list forms a ring of 68 stacks. Stack `k` has `shuffled[2k]` on top and
`shuffled[2k+1]` under it. Seat `s` owns stacks `17s` to `17s+16`. The dice choose where the ring
is broken. The seven stacks that start at the break are the dead wall: first two rinshan stacks,
then five dora stacks. The live wall starts to the left of the break. The hands are dealt from the
front of the live wall: four tiles to each seat in turn, starting with the dealer, three times, and
then one tile to each seat. The dealer's first draw is the next tile.

## The first dealer

The dealer stream copies the two-throw rule of a real table. Seat 0 throws two dice, and the sum
chooses a temporary dealer. That seat throws again, and the second sum chooses the first dealer.
Like at a real table, this is a little uneven on purpose: out of 1296 possible results, the four
seats get 326, 324, 322 and 324. Each seat is within 0.16 percentage points of 25%. The seating is
random too, so each player still has a 25% chance to be the first dealer.

## Seating

The seat stream shuffles the four seats with the same Fisher-Yates method. The players get the
first seats of the result, in the order the players are listed. AI players get the other seats.
This decides the seats of a live game. A replay records the name at each seat, and the replay
loader puts each name back in its recorded seat. So the seating rule is not part of the replay
format.

A game created with `fixed_seats` (used for tournament tables) does not read the seat stream. The
players sit in the order they are listed, starting at the seat of the first dealer from the seed:
the first player is East, the next is South, then West and North. The first dealer still comes
from the dealer stream. The replay records the name at each seat like in any other game, so it
does not store a seating mode.

## Versioning

Every replay stores `RNG_VERSION` (`shake256-v1`, the Go engine's `rng.Version`). A replay depends
on how the seed becomes the walls and the first dealer, so any change to that needs a new version.
The replay loader rejects other versions, so an old replay can only be loaded by the code that
recorded it. A change to the seating alone needs no new version, because a replay uses its recorded
names.

## How much randomness there is

| quantity | bits |
|---|---|
| orderings of 136 labelled tiles | 772.6 |
| walls that look different (copies of a type are the same, red fives differ) | 622.7 |
| seed | 768 |

For one round, the seed has more bits than there are different walls, so the seed size does not
limit which walls are possible. For a whole game, all rounds come from one seed, so not every
combination of walls over all rounds is possible. This is true for any generator that uses a seed.
Nobody can notice it in play, and a longer seed would not change it.

The seed proves that the game matches the seed. It does not prove that the server did not choose
the seed on purpose. To prove that, the server would have to commit to the seed before the game,
for example by publishing a hash of the seed or a list of hashes. The session does not do this
today.

## Measured results

`make measure-wall` samples games through these functions and compares each statistic with its
expected value. The default run (5000 games of 4 rounds, so 20000 walls, experiment seed 0, about
half a second) reports this for `shake256-v1`:

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

Shanten is how many tiles a hand is away from tenpai (ready): 0 is tenpai, and -1 is a complete
hand. These are the starting-hand shanten counts of the same run (80000 13-tile hands and 20000
dealer hands on each side):

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

If the generator is correct, each family of checks warns with a chance of at most 0.1%. So a
warning is a reason to run again with another `--experiment-seed`. It does not mean that a bug was
found. To test a change: save a run with `--json`, change the code, then run again with
`--baseline` and a different experiment seed.

## The Go sampler

`make measure-wall` runs `backend/game_v2/cmd/measurewall` over the seed functions of the Go
engine. It takes its engine seeds and its control shuffle from a Go copy of Python's
`random.Random`, seeded with fixed strings. So the same arguments always measure the same walls and
hands and print the same report.

The sampler was written to match the Python measurement it replaced: on the default run and on runs
with experiment seeds 1, 2 and 5, the two reports were the same except for the timing line.
`cmd/measurewall/testdata/python_report.txt` keeps the Python report of one small run (200 games of
3 rounds, experiment seed 5), and the `cmd/measurewall` tests check that the Go sampler still
prints it.

## Comparison with a naive shuffle

To show what the measurement can find, the same measurement was run once on a common wrong shuffle,
with throwaway code that is not in the repo. The wrong shuffle swaps each position `i` from 0 to
135 with a random position from the whole wall (`randint(0, 135)`), not from `i` to 135. It looks
random, but it has `136^136` equally likely swap sequences, and these cannot be spread evenly over
the `136!` possible orders. Computed exactly, tile 1 lands on position 0 with 1.36 times its fair
chance, and tile 135 with 0.74 times. The engine's Fisher-Yates gives every tile exactly a `1/136`
chance at every position.

| statistic | engine, 20000 walls | naive, 20000 walls | naive, 100000 walls |
|---|---|---|---|
| tile id by position, worst cell z | 4.0, ok | 6.7, warn | 11.7, warn |
| tile type by position, worst cell z | 3.4, ok | 10.6, warn | 19.4, warn |
| adjacent tiles of the same type per wall (3.000) | 3.001 | 3.039 | 3.039, warn |
| same-type pairs in a 13-tile hand (1.733) | 1.731 | 1.740 | 1.746, warn |
| mean shanten of a 13-tile hand, vs control | 3.582 vs 3.574 | 3.568 vs 3.574 | 3.571 vs 3.581, warn |

The naive shuffle already fails the position checks at the default size. Its effect on hands is
small, a few hundredths of a shanten, and it shows only at 100000 walls. This is why the
measurement checks tile positions and not only hand quality.

## Where the expected values come from

All expected values come from one model: a uniformly random order of the 136 tiles, and fair dice.
None of them come from the engine itself.

- **Tile by position, dora type, seat permutation:** uniform, because every position and seat is
  treated the same.
- **Adjacent same-type tiles:** a wall has 135 pairs of neighbouring tiles. Each pair has the same
  type with a chance of 3/135 (the three other copies among the other 135 tiles), so 3.0 per wall.
- **Same-type pairs in a hand:** C(13, 2) × 3/135 = 1.733.
- **Honours and red fives in a hand:** 13 × 28/136 = 2.676 and 13 × 3/136 = 0.287.
- **Consecutive rounds:** two independent walls have the same tile at a position with a chance of
  1/136, so 1.0 of the 136 positions.
- **Dice:** 1/6 for each face. The sums follow the triangle 1, 2, ..., 6, ..., 2, 1 out of 36.
- **First dealer:** the two-throw rule, counted over all 1296 pairs of throws.
- **Shanten:** there is no formula, so the reference runs the same shanten calculator over hands
  from Python's `random.shuffle` (copied into the sampler). This compares the engine's shuffle with
  an independent shuffle.
