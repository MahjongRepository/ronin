### 1. Object of the Game

The goal is to complete a winning hand composed of four sets and a pair. A standard winning hand contains 14 tiles (13
in hand plus the winning tile).

* Tile Definitions:
    * Simples: Suit tiles numbered 2 through 8.
    * Terminals: Suit tiles numbered 1 and 9.
    * Honors: Wind and Dragon tiles.
* Sets:
    * Sequence: Three consecutive tiles of the *same* suit. Note: Sequences cannot "wrap around" (e.g., 9-1-2 is
      invalid).
    * Triplet: Three identical tiles.
    * Quad: Four identical tiles declared as a set.
* Winning Condition: A hand must be complete and contain at least one *yaku* (scoring pattern). A hand without *yaku*
  cannot win.
* Exceptions: Two special hands do not follow the standard four-sets-and-a-pair structure: *Seven Pairs* and *Thirteen
  Orphans*.

### 2. Game Structure

* Rounds: A full game consists of two rounds: the East round and the South round (*Hanchan*). A shorter version
  consisting only of the East round is called *Tonpusen*.
* Dealer (East): Players take turns being the dealer. The player seated at the "East" position is the dealer for that
  hand.
* Hand Progression: A hand ends when a win is declared, the wall is exhausted (Exhaustive Draw), or an Abortive Draw
  occurs.
* Dealer Rotation and Repeats (Renchan):
    * Dealer Repeats: If the dealer wins the hand, is *tenpai* (waiting) at an exhaustive draw, or if an Abortive Draw
      occurs, they remain the dealer for the next hand.
    * Rotation: If the dealer does not win and is *noten* (not waiting) at an exhaustive draw, the position of the
      dealer rotates counter-clockwise to the next player.
* Counters (Honba):
    * If a hand ends in a draw or a dealer win, a *honba* counter is placed on the table. Each counter increases the
      value of the next winning hand by 300 points.
    * These counters accumulate and are cleared only when a non-dealer wins a hand.
* Game End Conditions:
    * Negative Score (Tobi): The game ends immediately if a player's score drops below zero (runs out of points).
    * Target Score: If the target score (typically 30,000) is not met by the end of the final round (South 4), the game
      may extend into a "West Round" (Sudden Death) until a player exceeds the target or the round ends.
    * Tie-breaking: When two or more players have the same score, the player closer to the starting dealer (起家,
      seat 0) ranks higher.

### 3. Turn Mechanics

Play proceeds counter-clockwise, starting with the dealer.

* Draw: A turn begins by drawing a tile from the wall.
* Discard: If the player does not declare a win or a quad, they must discard one concealed tile to end their turn.
* Discard Restrictions:
    * Discards are placed face-up in rows of six in front of the player. These discards act as a record for "Furiten"
      status and defensive safety.
    * Kuikae (Swap-calling): It is forbidden to claim a tile for a set and immediately discard the same tile (e.g.,
      calling Pon on a 5 and discarding a 5). It is also forbidden to claim a tile for a sequence and discard the tile
      that would complete the other end of that specific sequence (e.g., calling a 4 to make 2-3-4, then immediately
      discarding a 1).
* Dead Wall: A "Dead Wall" of 14 tiles is kept separate from the live wall. It provides replacement tiles for Quads and
  holds Dora indicators.

### 4. Claiming Tiles (Calling)

Players can interrupt the flow of play to claim the most recently discarded tile.

* Open vs. Closed State:
    * Closed: A hand is "Closed" if the player has not called any tiles from opponents. (Concealed Quads do not open a
      hand).
    * Open: Once a player claims a tile via Chii, Pon, or Daiminkan (Claimed Quad), the hand becomes "Open." An open
      hand is limited: some *yaku* are no longer valid, and others are reduced in value.
* Order of Precedence:
    1. Win (Ron): Highest priority. Any player can claim a discard for a win.
    2. Triplet/Quad (Pon/Kan): Second priority. Can be claimed from any player.
    3. Sequence (Chii): Lowest priority. Can only be claimed from the player immediately to the left.
* Procedure:
    1. Clearly call the action ("Chii", "Pon", "Kan", or "Ron").
    2. Reveal the matching tiles from the hand.
    3. Take the discarded tile and place it with the revealed tiles. The claimed tile is rotated to indicate who
       discarded it (left, opposite, or right).
    4. Discard a tile (except when declaring a claimed quad or winning).

### 5. Quads (Kan)

A quad is a set of four identical tiles. It must be declared to function as a set.

* Types of Quads:
    * Concealed Quad (Ankan): Revealing four identical concealed tiles from the hand. This set is considered "concealed"
      for scoring purposes.
    * Claimed Quad (Daiminkan): Calling "Kan" on an opponent's discard when holding three matching tiles.
    * Extended Quad (Shouminkan): Adding a drawn tile to a previously melded triplet (Pon).
* Limits: A maximum of four quads can be declared in a single hand. If four quads are declared by the *same* player,
  play continues. If four quads are declared by *two or more different* players, the hand ends in an Abortive Draw.

#### 5a. Concealed Quad (Ankan) Flow

Declared during the player's own turn (after drawing), using four identical tiles from hand.

1. Player declares Ankan, reveals the four tiles.
2. New Kan Dora indicator is revealed **immediately** (before discard).
3. Player draws a replacement tile (*Rinshanpai*) from the Dead Wall.
4. Dead Wall Adjustment: the last tile of the live wall is moved to the Dead Wall (maintains 14 tiles).
5. Player may now:
    * Declare **another** Concealed/Extended Quad if the replacement tile completes a set of four (repeat from step 1).
    * Declare *Tsumo* if the replacement tile completes a winning hand (*Rinshan Kaihou*).
    * Discard a tile to end the turn.
6. The hand remains closed. Ippatsu is cleared for all players.

*Note:* Consecutive Concealed Quads are allowed without discarding between them, each revealing a new Dora indicator
immediately. The only limits are four quads per hand and at least two tiles remaining in the live wall.

#### 5b. Claimed Quad (Daiminkan) Flow

Declared by claiming an opponent's discarded tile when holding three matching tiles. Opens the hand.

1. Player calls Kan on the discard, reveals the three tiles from hand plus the claimed tile.
2. Player draws a replacement tile (*Rinshanpai*) from the Dead Wall.
3. Dead Wall Adjustment: the last tile of the live wall is moved to the Dead Wall (maintains 14 tiles).
4. Player may now:
    * Declare *Tsumo* if the replacement tile completes a winning hand (*Rinshan Kaihou*). The Kan Dora is
      **not** revealed (the hand ends before the discard).
    * Discard a tile.
5. **After the discard passes** (is not claimed for Ron):
    * The new Kan Dora indicator is revealed.
    * If the discard is claimed for Ron, the Kan Dora indicator is **not** revealed.

*Note:* The deferred Dora reveal applies even if the discard is subsequently claimed for a meld (Pon/Chi). The Dora
indicator is revealed once the discard survives the Ron check, regardless of whether another player then calls a meld.

#### 5c. Extended Quad (Shouminkan) Flow

Declared during the player's own turn by adding a drawn fourth tile to an existing open triplet (Pon).

1. Player declares Shouminkan, adds the tile to the existing Pon.
2. **Chankan check:** opponents who are waiting on the added tile may declare Ron (*Chankan*).
    * If Chankan succeeds: the quad is **not** completed. No Kan Dora is revealed. Ippatsu is **not** cleared (the
      kan never happened). The Chankan winner scores with 1 extra han for the *Chankan* yaku.
    * If all opponents decline Chankan: continue to step 3.
3. Player draws a replacement tile (*Rinshanpai*) from the Dead Wall.
4. Dead Wall Adjustment: the last tile of the live wall is moved to the Dead Wall (maintains 14 tiles).
5. Player may now:
    * Declare *Tsumo* if the replacement tile completes a winning hand (*Rinshan Kaihou*). The Kan Dora is
      **not** revealed (the hand ends before the discard).
    * Discard a tile.
6. **After the discard passes** (is not claimed for Ron):
    * The new Kan Dora indicator is revealed.
    * If the discard is claimed for Ron, the Kan Dora indicator is **not** revealed.

#### 5d. Kan Dora Timing Summary

| Quad Type              | Dora Reveal Timing                                  | On Rinshan Kaihou | On Ron of Discard |
|------------------------|-----------------------------------------------------|-------------------|-------------------|
| Concealed (Ankan)      | Immediately after declaration                       | Dora applies      | N/A (before discard) |
| Claimed (Daiminkan)    | After the replacement discard passes (not ron'd)    | Dora not revealed | Dora not revealed |
| Extended (Shouminkan)  | After the replacement discard passes (not ron'd)    | Dora not revealed | Dora not revealed |

### 6. Riichi

A player with a concealed hand that needs only one tile to win (*tenpai*) may declare *Riichi*.

* Requirements:
    * The hand must be fully concealed.
    * The player must be *tenpai*.
    * There must be at least four tiles remaining in the live wall.
* Procedure:
    1. Call "Riichi".
    2. Discard a tile rotated sideways.
    3. Place a 1,000-point betting stick on the table.
* Restrictions: Once Riichi is declared, the player cannot change the composition of their hand. They must discard every
  drawn tile unless it is a winning tile.
    * *Concealed Quads:* A player may declare a concealed quad on a drawn tile only if the quad does not change the
      hand's waiting tiles or the interpretation of the sets.
* Interruption: If an opponent claims the rotated Riichi discard for a win, the Riichi declaration is void and the 1,000
  points are not paid. If claimed for a set, the player must rotate their *next* discard to indicate the Riichi status.

### 7. Game States

* Tenpai: The state of waiting for one specific tile to complete the hand.
* Noten: The state of not being ready to win.
* Keishiki Tenpai (形式聴牌): Structural tenpai counts for noten payments at an exhaustive draw, even if all winning
  tiles are visible elsewhere (in other players' discards, etc.). Exception: pure karaten (all 4 copies of every
  winning tile are in the player's own hand and melds) is treated as noten.

### 8. Furiten

Furiten (振聴) prevents a player from winning by Ron (discard) under certain conditions. A player in furiten can
still win by Tsumo (self-draw).

* Discard Furiten (permanent): A player who has discarded a tile matching any of their current waits cannot call Ron.
  This furiten persists as long as the wait includes a previously discarded tile.
* Temporary Furiten: A player who passes on a Ron opportunity (including Chankan Ron) cannot call Ron until their next
  discard. This resets when the player makes their next discard.
* Riichi Furiten: A riichi player whose winning tile passes by (for any reason, including being already in furiten or
  explicitly passing) becomes permanently unable to call Ron for the rest of the hand. This never clears within the
  current hand.

### 9. Liability (Pao)

A specific penalty rule applies to the "Big Three Dragons" and "Big Four Winds" hands.

* Trigger: If a player discards the tile that allows an opponent to meld the third set of Dragons or the fourth set of
  Winds (completing the necessary sets for the Yakuman), that player becomes liable.
* Penalty:
    * If the hand is won by self-draw (Tsumo), the liable player pays the full score.
    * If the hand is won by discard (Ron) from another player, the liable player and the discarder split the payment
      50/50.

### 10. Winning

* Self-Draw (Tsumo): Winning on a tile drawn from the wall or dead wall.
* Discard (Ron): Winning on a tile discarded by an opponent.
* Robbing a Quad (Chankan): A player can win on a tile used by an opponent to declare an Extended Quad (adding to a
  Pon). This is treated as a win by discard (Ron). Robbing a *Concealed* Quad is only allowed to complete the *Thirteen
  Orphans* hand.
* Simultaneous Winners: If two players declare Ron on the same discard, both wins are accepted (Double Ron) and the
  discarder pays both winners. If all three opponents declare Ron on the same discard (Triple Ron), the hand ends in an
  Abortive Draw with no score changes.

### 11. End of Hand

A hand ends in one of three ways:

1. Win: One or more players declare a valid win.
    * *Ura Dora:* If a Riichi player wins, they reveal the tiles underneath the Dora and Kan Dora indicators (*Ura
      Dora*) for potential extra value.

2. Exhaustive Draw (Ryuukyoku): The wall is depleted and no one has won.
    * *Tenpai Check:* Players reveal if they are *tenpai* or *noten*. Riichi players must show their hands; others may
      choose to show or accept *noten* status.
    * *Penalty:* Players who are *noten* pay a penalty to those who are *tenpai* (Total 3,000 points exchanged).

3. Abortive Draw (Tochuu Ryuukyoku): The hand ends immediately, and a re-deal occurs (with a Renchan). Conditions
   include:
    * *Nine Terminal/Honors (Kyuushu Kyuuhai):* A player has 9+ unique terminal/honor tiles in their starting hand (
      first turn) and chooses to abort. (Must be declared before any other calls are made).
    * *Four Winds:* All four players discard the same wind tile on their first turn.
    * *Four Riichi:* All four players declare Riichi. The hand ends after the fourth declaration succeeds (provided no
      one wins on the discard).
    * *Four Kans:* Four quads are declared by two or more different players.
    * *Triple Ron:* All three opponents declare Ron on the same discard. The hand ends with no score changes.

### 12. Special Mechanics

* Dora: Specific tiles that add value to the hand.
    * Red Dora (Akadora): The set contains red versions of #5 tiles (one for each suit) which act as permanent Dora.
* Renhou (Blessing of Man): A non-dealer wins by Ron before their first draw, with no calls (including closed kans) having been made by any player. Scored as a 5-han yaku (mangan level).
* Double Yakuman: Four hands score as double yakuman (2x the base yakuman value):
    * Daburu Kokushi Musou (ダブル国士無双): Thirteen Orphans with a 13-sided wait (waiting on any of the 13 terminal/honor tiles).
    * Suuankou Tanki (四暗刻単騎): Four Concealed Triplets with a pair wait.
    * Daburu Chuuren Poutou (ダブル九蓮宝燈): Nine Gates with a 9-sided wait (1112345678999 + any tile in the suit).
    * Daisuushii (大四喜): Big Four Winds (four wind triplets).
    * Kazoe yakuman (13+ han from regular yaku) remains at single yakuman level.
* Nagashi Mangan: A special condition occurring at an Exhaustive Draw.
    * If a player's discard pile consists *only* of terminal and honor tiles, and none of their discards were claimed by opponents, they receive a special payment.
    * This is treated as a special draw, not a win. No Riichi sticks are collected, and no Honba is added.

### 13. Uma/Oka (End-Game Scoring)

After the game ends, raw scores are adjusted using the uma/oka system (25000点持ち/30000点返し, ウマ10-20).

* Oka (オカ): Each player starts with 25,000 but the target is 30,000. The difference of 5,000 per player (20,000 total, or 20 points after dividing by 1,000) is awarded as a bonus to 1st place.
* Uma (ウマ): Placement bonus/penalty applied after oka. Format 10-20 means 3rd-to-2nd pays 10, 4th-to-1st pays 20. Applied as: 1st +20, 2nd +10, 3rd -10, 4th -20.
* Calculation:
    1. Subtract target score (30,000) from each player's raw score.
    2. Divide by 1,000.
    3. Round using goshashōnyū (五捨六入): remainder of 500 or less rounds toward zero, remainder of 600 or more
       rounds away from zero.
    4. Add oka bonus (+20) to 1st place.
    5. Apply uma spread.
    6. Adjust 1st place score to ensure the sum of all final scores is zero.
