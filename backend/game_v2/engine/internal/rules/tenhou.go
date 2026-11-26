package rules

import "github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"

// Tenhou returns the default ruleset, modelled on tenhou.net's four-player hanchan with red fives.
func Tenhou() Ruleset {
	return Ruleset{
		StartingScore:         25000,
		TargetScore:           30000,
		WinningScoreThreshold: 30000,
		Tobi:                  TobiBelowZero,
		Agariyame:             true, // the last hand's dealer, leading after a win or tenpai, ends the game instead of repeating
		WestRound:             true,

		Uma:                         [tile.SeatCount]int{20, 10, -10, -20},
		LeftoverRiichiSticksToFirst: true,
		SplitTiedPlaces:             false,
		RoundFinalPoints:            false,

		RiichiMinWall:          4, // live wall tiles a riichi declaration needs left
		RiichiStickValue:       1000,
		ShakkinRiichi:          false, // riichi with fewer points than the stick, into a negative score
		RiichiKanKeepsReadings: false,
		HonbaValue:             300,

		AkaDora:                      tile.AkaDoraEnabled,
		KanDoraImmediateForClosedKan: true,
		KanDoraImmediateForOpenKan:   false,

		OpenTanyao:    true,
		DoubleYakuman: false, // 13-wait kokushi, single-wait suuankou, 9-wait chuuren and big four winds pay double
		KazoeYakuman:  true,  // counted yakuman: 13+ han without a yakuman yaku pays a yakuman, else sanbaiman
		KiriageMangan: false, // 4 han 30 fu and 3 han 60 fu round up to mangan
		Renhou:        RenhouOff,

		FuForOpenPinfu:      true,  // an open hand of pinfu shape gets 2 fu, reaching 30
		FuForPinfuTsumo:     false, // pinfu (no-points hand) by self-draw still gets the 2 tsumo fu
		FuForDoubleWindPair: 4,     // a pair of the wind that is both the seat and the round wind

		Atamahane:               false,
		MultiRonSticksToNearest: true,
		PaoHonbaFromDiscarder:   false,
		NagashiMangan:           true, // at a draw, a river of only terminals and honors, none called, pays mangan

		AbortKyuushuKyuuhai: true, // nine kinds of terminals and honors in the first hand may abort it
		AbortFourWinds:      true, // all four first discards the same wind (suufon renda)
		AbortFourRiichi:     true,
		AbortFourKans:       true, // four kans by two or more players (suukaikan)
		AbortTripleRon:      true,
	}
}
