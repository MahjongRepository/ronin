package rules

import "github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"

// RRC returns the Russian riichi community's rules (Регламент RRC, version 2.0 of 4 July 2026) with
// no tournament variation.
func RRC() Ruleset {
	return Ruleset{
		StartingScore:         30000,
		TargetScore:           30000,
		WinningScoreThreshold: 30000,
		Tobi:                  TobiOff,
		Agariyame:             false, // the last hand's dealer, leading after a win or tenpai, ends the game instead of repeating
		WestRound:             false,

		Uma:                         [tile.SeatCount]int{30, 10, -10, -30},
		LeftoverRiichiSticksToFirst: true,
		SplitTiedPlaces:             true,
		RoundFinalPoints:            false,

		RiichiMinWall:          4, // live wall tiles a riichi declaration needs left
		RiichiStickValue:       1000,
		ShakkinRiichi:          true, // riichi with fewer points than the stick, into a negative score
		RiichiKanKeepsReadings: true,
		HonbaValue:             300,

		AkaDora:                      tile.AkaDoraEnabled,
		KanDoraImmediateForClosedKan: true,
		KanDoraImmediateForOpenKan:   true,

		OpenTanyao:    true,
		DoubleYakuman: false, // 13-wait kokushi, single-wait suuankou, 9-wait chuuren and big four winds pay double
		KazoeYakuman:  true,  // counted yakuman: 13+ han without a yakuman yaku pays a yakuman, else sanbaiman
		KiriageMangan: false, // 4 han 30 fu and 3 han 60 fu round up to mangan
		Renhou:        RenhouMangan,

		FuForOpenPinfu:      true,  // an open hand of pinfu shape gets 2 fu, reaching 30
		FuForPinfuTsumo:     false, // pinfu (no-points hand) by self-draw still gets the 2 tsumo fu
		FuForDoubleWindPair: 4,     // a pair of the wind that is both the seat and the round wind

		Atamahane:               false,
		MultiRonSticksToNearest: false,
		PaoHonbaFromDiscarder:   true,
		NagashiMangan:           false, // at a draw, a river of only terminals and honors, none called, pays mangan

		AbortKyuushuKyuuhai: false, // nine kinds of terminals and honors in the first hand may abort it
		AbortFourWinds:      false, // all four first discards the same wind (suufon renda)
		AbortFourRiichi:     false,
		AbortFourKans:       false, // four kans by two or more players (suukaikan)
		AbortTripleRon:      false,
	}
}
