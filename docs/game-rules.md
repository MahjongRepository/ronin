# Ronin Game Rules

Standard Japanese Riichi Mahjong (4-player). This document lists the specific rules and settings that define Ronin's ruleset, separated into fixed mechanics (inherent to the game) and configurable settings (adjustable per ruleset).

---

## Basic Mechanics

Rules fundamental to Riichi Mahjong that cannot be configured via settings.

### Wall & Draws

- Dead wall (wanpai): Exactly 14 tiles maintained at all times. When a player draws a rinshan (replacement) tile after a kan, the last tile of the live wall moves to the dead wall to maintain 14.
- Exhaustive draw: Occurs when the live wall reaches 0 tiles (all non-dead-wall tiles have been drawn).
- 1-han minimum (shibari): A winning hand must contain at least one valid yaku excluding dora. Dora alone cannot satisfy the win condition.

### Calls & Turn Order

- Call precedence: Ron > Pon/Kan > Chi; among same-type calls, closer counter-clockwise to discarder wins (for chankan, to the kan caller)
- A player who can both ron and call a meld (chi, pon or kan) on the same discard is offered all of them and may choose either. Calling the meld instead declines the ron, with the same temporary furiten as passing; any other player's ron still takes precedence over the meld.
- Last discard restriction: The final discard of a hand (when no tiles remain in the live wall after the draw) cannot be called for chi, pon, or kan — only ron is allowed.
- Four kans restriction: The replacement discard of a fourth kan that makes a Four Kans abortive draw cannot be called for chi, pon, or kan — only ron is allowed. (No meld arises on the discard declaring a fourth riichi either: the other three players are in riichi and cannot call.)
- Tsumo wins on a self-drawn tile, including a kan replacement draw and the dealer's initial hand. Claiming a discard for chi or pon does not provide a tsumo opportunity.

### Riichi

- Riichi stick value: 1,000 points per stick
- Minimum points for declaration: 1,000
- Riichi bet on interrupted declaration: Not paid (void if discard is ron'd)
- Riichi discard claimed for a meld: Riichi stands. Ippatsu is lost.
- Riichi at exactly 1,000 points: Allowed (player goes to 0 points; game continues unless another player wins and triggers tobi)
- Minimum wall tiles for declaration: 4
- After riichi is established, every discard must be the tile just drawn. The player may instead declare a legal win or a permitted concealed kan. The declaration discard itself may be any tile that keeps the hand tenpai.
- Concealed quad during riichi (ankan): Allowed only if it doesn't change the hand's waiting tiles or set interpretation. Applies to concealed kan only — shouminkan is blocked during riichi. The drawn tile must be the kan tile.
- Riichi sticks on exhaustive/abortive draw: Remain on the table for the next hand. Awarded to 1st place at game end if uncollected.

### Furiten

- Furiten prohibits ron, including chankan, on every winning tile. It does not prohibit an otherwise legal tsumo.
- Furiten scope: Based on the player's full discard history — all tiles the player has discarded this hand, regardless of whether another player subsequently claimed them. Only the player's own discards count: tiles in their melds, and tiles they called from others, are not their discards.
- Discard furiten: Permanent while wait includes a previously discarded tile
- Temporary furiten: Triggered when another player's discard, or an added-kan tile open to chankan, completes the player's hand and the player does not win on it: by passing, by calling a meld on it instead, or because Ron was not possible (no yaku, or already furiten). A riichi player gets riichi furiten instead. Resets on player's next discard.
- Riichi furiten: Permanent for the rest of the hand (never clears)
- Furiten riichi declaration: Allowed (player may declare riichi while in furiten; can only win by tsumo)

### Ippatsu

- Any call (chi, pon, or kan) by any player clears Ippatsu for all riichi players.

### Kan (Quads)

- Minimum wall tiles for kan: 2
- Kan after pon/chi on same turn: Not allowed (kan requires a drawn tile)
- Consecutive concealed quads: Allowed without discarding between them (each reveals a new Dora indicator immediately)
- Four quads by same player: Play continues (does NOT trigger abortive draw)
- Four quads by different players (2+): Abortive draw (Four Kans, below)

#### Kan Dora Timing

| Quad Type             | Dora Reveal Timing                           | On Rinshan Kaihou | On Ron of Discard    |
|-----------------------|----------------------------------------------|-------------------|----------------------|
| Concealed (Ankan)     | Immediately after declaration                | Dora applies      | N/A (before discard) |
| Claimed (Daiminkan)   | After replacement discard passes (not ron'd) | Dora not revealed | Dora not revealed    |
| Extended (Shouminkan) | After replacement discard passes (not ron'd) | Dora not revealed | Dora not revealed    |

Deferred Dora reveal applies even if the discard is subsequently claimed for a meld (Pon/Chi); the reveal triggers once the Ron check passes.

#### Chankan (Robbing a Quad)

- Allowed on extended quads (shouminkan). Chankan scores as Ron with 1 extra han for the Chankan yaku.
- On concealed quads (ankan), only Kokushi Musou may rob — no other hand qualifies.
- Ippatsu is not cleared (the quad is treated as never having occurred)
- Kan dora indicator is NOT flipped (the kan is treated as never having occurred)

### Dora Indicators

- Indicator→dora mapping (the indicated dora is the next tile in sequence):
  - Suited tiles: 1→2→3→4→5→6→7→8→9→1
  - Wind tiles: East→South→West→North→East
  - Dragon tiles: White (Haku)→Green (Hatsu)→Red (Chun)→White
- Red fives are inherently 1 dora each, independent of indicators. If a dora indicator also points to 5, a red five counts as 2 dora (1 inherent + 1 from indicator).
- Ura dora are revealed only when a riichi or double riichi player wins.

### Scoring Fundamentals

- Honba (ron): +300 points per counter
- Honba (tsumo): +100 points per counter per losing player (300 total, same as ron)
- Payment rounding: All individual payments rounded UP to the nearest 100 points
- Noten penalty (exhaustive draw only): 3,000 points total redistributed (split evenly among noten payers, distributed evenly to tenpai players). No noten payments on abortive draws.
- Keishiki tenpai (形式聴牌): Counts as tenpai for noten payments, except pure karaten (all 4 copies in own hand/melds). Waiting for a tile where all 4 copies are visible in others' discards/melds still counts as tenpai.
- Goshashonyu rounding (五捨六入): ≤500 rounds toward zero, ≥600 rounds away
- Tie-breaking: When players have equal final scores, the player closer counter-clockwise to the starting dealer ranks higher. The starting dealer is chosen by dice from the game seed, so it is not always seat 0.
- Double ron riichi sticks: the winner closest counter-clockwise to the discarder receives them. For chankan the kan caller takes the discarder's role.

### Liability (Pao)

- Applies to: Big Three Dragons, Big Four Winds. Does NOT apply to Suukantsu (Four Quads).
- Trigger: Discarding the tile that completes the third dragon set or fourth wind set
- Liability covers only the value of the liable yakuman (Big Three Dragons, or Big Four Winds at its double-yakuman value when double yakuman is enabled). Any other yakuman in the same hand (e.g. All Honors) is settled normally.
- Tsumo: Liable player pays the liable yakuman's whole value and the whole honba bonus. The other yakuman's value is paid as an ordinary tsumo by all three players, the liable player included. Example: dealer Big Three Dragons + All Honors (96,000) — liable player pays 48,000 + 16,000, the other two pay 16,000 each.
- Ron off a player other than the liable one: Liable player pays half the liable yakuman's value and the whole honba bonus; the discarder pays the other half and any other yakuman's value. Example: the same dealer hand by ron — liable player pays 24,000, discarder 72,000.
- Ron off the liable player: They pay the full hand value and honba bonus, as an ordinary ron
- Riichi sticks go to the winner as usual. In a double ron each winner is settled separately: liability applies only to the winner it is for, whose honba bonus the liable player pays (unless they are the discarder); the discarder pays the other winner's honba bonus.
- With a lowered set threshold, a winning hand that does not score the liable yakuman carries no liability: the win is settled normally, so the would-be liable player still pays their ordinary share on a tsumo, or in full when they dealt in.

### Dealer Rotation

- Dealer repeats (renchan): On dealer win, dealer tenpai at exhaustive draw, or abortive draw
- Dealer rotates: When dealer is noten at exhaustive draw
- Honba counter: Increments by 1 on dealer repeat, exhaustive draw, and abortive draw. Resets to 0 only when the dealer is not among the winners. If dealer wins (even as one of multiple winners in double ron), honba increments (renchan).

### West Round (Sudden Death)

Applies when the game type and winning score threshold settings allow the game to extend past the primary wind rounds (e.g., Hanchan with 30,000 threshold — if no player reaches 30,000 after South round ends, the game enters West wind).

- End condition: The game ends at the first moment any player's score reaches the winning score threshold (checked after every hand result — win, draw, or noten payments).
- Dealer renchan in West round: If the dealer wins or is tenpai at exhaustive draw, renchan applies — but if any player (including the dealer) has reached the threshold, the game ends immediately regardless of renchan.
- Rotation continues normally through West-1, West-2, West-3, West-4. If no player reaches the threshold by the end of West-4, the game ends and the player closest to the threshold wins (standard tie-breaking applies).

### Yaku Special Cases

- Tenhou (Blessing of Heaven): Dealer yakuman on initial 14-tile draw
- Chiihou (Blessing of Earth): Non-dealer yakuman on first self-draw. Any call (meld) by any player interrupts.
- Haitei Raoyue (Under the Sea): 1-han, win on last wall tile (tsumo)
- Houtei Raoyui (Under the River): 1-han, win on last discard (ron)
- Rinshan Kaihou: Win on replacement tile after any quad type
- Ryuuiisou (All Green): Yakuman; green tiles only (2, 3, 4, 6, 8 sou and/or hatsu). Hatsu not required.
- Double Riichi: Riichi on very first uninterrupted discard (2 han). Interrupted by any call (chi, pon, kan, including concealed kan) by any player before the declaration.
- Nagashi Mangan: Treated as special draw; requires all discards are terminals/honors with none claimed. Only opponent's claiming of player's discards invalidates — player may call others' tiles and still qualify. Payment equivalent to mangan tsumo: if non-dealer achieves it, 4,000 from dealer and 2,000 from each non-dealer; if dealer achieves it, 4,000 from each non-dealer. No honba bonus is paid during settlement, but the honba counter increments by 1 for the next hand (same as exhaustive draw). Riichi sticks on the table are not collected (carry to next hand). Dealer rotation follows exhaustive draw rules (dealer keeps seat if tenpai).

---

## Configurable Settings

Rules that could theoretically be adjusted through game settings. Current Ronin defaults shown.

### Game Structure

- Game type: Hanchan (East + South rounds); also supports East-only (Tonpusen)
- Number of players: 4
- Starting score: 25,000
- Target score: 30,000
- Winning score threshold: 30,000 (distinct from target score; controls game-end check after primary wind completes)
- Uma: 10-20
- Oka: Enabled (25,000/30,000) — each player contributes (target_score - starting_score) = 5,000 points; total oka of 20,000 goes to 1st place
- Tobi (negative score): Game ends immediately. Tobi threshold: Below 0 points (0 points does not end the game)
- Agariyame (dealer stops in all-last while leading): Disabled
- Tenpaiyame (dealer stops in all-last if leading and tenpai at exhaustive draw): Disabled

### Yaku Toggles

- Open Tanyao (Kuitan): Allowed
- Ippatsu: Enabled
- Atozuke (gaining yaku upon winning tile claim): Allowed
- Renhou (Blessing of Man): 5-han (mangan level); non-dealer Ron before first draw, no calls by any player

### Call Rules

- Kuikae (swap-calling): Not allowed
  - Same-tile restriction: For the discard immediately after pon or chi, cannot discard the same tile type that was claimed
  - Suji restriction: For the discard immediately after chi, also forbid the tile that would complete a sequence with the two tiles contributed from hand: calling 1m with 23m forbids discarding 4m; calling 4m with 23m forbids 1m. Calling the middle tile (2m with 13m) adds no suji restriction.
  - Red and ordinary fives share a tile type for kuikae.
  - A chi is legal only if at least one legal discard remains after the meld is formed; a chi shape that would leave only kuikae-forbidden tiles is not offered and is rejected. A pon can never leave such a hand.
- Multiple Ron (Double Ron): Allowed (2 players win simultaneously); riichi sticks from previous rounds go to the winner closest counter-clockwise to the discarder. Both winners receive the honba bonus (+300 per counter each) — the discarder pays the honba bonus to each winner separately. When disabled, Head Bump (Atama Hane) applies: only the player closest counter-clockwise to the discarder wins, and only they receive riichi sticks. For chankan the kan caller takes the discarder's role in both rules.

### Dora

- Omote dora (face-up indicators): Enabled
- Ura Dora: Enabled (revealed on Riichi win; tiles underneath Dora and Kan Dora indicators)
- Red dora (Akadora): 3 (one per suit, #5 tiles)
- Kan dora: Enabled
- Kan ura dora: Enabled

### Abortive Draws

- Kyuushu Kyuuhai (player choice): Any player may declare kyuushu kyuuhai with at least nine distinct terminal/honor types among their 14 tiles on their initial turn, before discarding, provided no player has made a chi, pon, or kan (including concealed kan). Other players' ordinary discards do not end eligibility, and the drawn tile counts toward the nine types. Not automatic — the server must offer this as an action.
- Four Winds: All four players discard the same wind on first turn
- Four Riichi: After fourth riichi succeeds (if no one wins on the discard). A ron on the declaration discard stands, and the fourth riichi stick is not deposited.
- Four Kans: Four kans declared by two or more players. The fourth kan completes as usual: its declarer draws the replacement tile and may win by rinshan kaihou, or discards. If that discard is ronned, the ron stands; otherwise the hand ends in an abortive draw once the discard passes (it cannot be called for a meld, and any deferred kan dora is revealed first). A fourth kan that is robbed (an added kan by chankan, or a closed kan by kokushi musou) never completes, so the ron stands. If the replacement discard also declares the fourth riichi, the abort is reported as Four Riichi. One player holding all four kans plays on, and no fifth kan can be declared.
- Triple Ron: Three opponents declare Ron on the same discard or on the same added-kan tile (chankan); no score changes. Being able to ron is not enough: each eligible player is offered the call, and if one of them passes, the other two win by double ron (or head bump when double ron is disabled).

### Yakuman Options

- Double Yakuman hands:
    - Daburu Kokushi Musou (13-sided wait)
    - Suuankou Tanki (pair wait)
    - Daburu Chuuren Poutou (9-sided wait)
    - Daisuushii (Big Four Winds)
- Multiple yakuman stacking: Allowed (e.g., Daisuushii + Tsuuiisou = double yakuman)
- Kazoe Yakuman (13+ han): Single yakuman only. Dora (including red, kan, and ura dora) count toward the 13-han threshold.
- Yakuman hands and dora: Dora do not add han to yakuman hands. Yakuman scoring is fixed regardless of additional dora in the hand.
- Maximum yakuman: Sextuple yakuman (6x)

### Scoring Options

- Double wind pair: 4 fu
- Chiitoitsu: Fixed 25 fu, 2 han
- Pinfu tsumo: 0 fu (no additional fu for pinfu tsumo)
- Open pinfu: 2 fu (fu added for open pinfu hands)
- Kiriage Mangan (rounded mangan): Enabled. 4-han/30-fu and 3-han/60-fu hands score as mangan (8,000/12,000) instead of exact values (7,700/11,600).
