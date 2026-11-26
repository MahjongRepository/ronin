package rules

import "github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"

// Tenhou returns the default ruleset, modelled on tenhou.net's four-player hanchan with red fives.
func Tenhou() Ruleset {
	return Ruleset{
		StartingScore:         25000,
		TargetScore:           30000,
		WinningScoreThreshold: 30000,
		Tobi:                  true, // bust: a score below TobiThreshold ends the game at once
		TobiThreshold:         0,
		Agariyame:             true, // the last hand's dealer, leading after a win or tenpai, ends the game instead of repeating

		Uma:                         [tile.SeatCount]int{20, 10, -10, -20}, // placement bonus
		LeftoverRiichiSticksToFirst: true,
		RoundFinalPoints:            false,

		RiichiMinWall:    4, // live wall tiles a riichi declaration needs left
		RiichiStickValue: 1000,
		HonbaValue:       300, // repeat counter, added to every win

		AkaDora:                      tile.AkaDoraEnabled, // red fives, each an extra dora
		KanDoraImmediateForClosedKan: true,                // turned at the kan, not at the next discard
		KanDoraImmediateForOpenKan:   false,               // turned at the kan, not at the next discard

		OpenTanyao:    true,  // all simples (tanyao) counts in an open hand; kuitan
		DoubleYakuman: false, // 13-wait kokushi, single-wait suuankou, 9-wait chuuren and big four winds pay double
		KazoeYakuman:  true,  // counted yakuman: 13+ han without a yakuman yaku pays a yakuman, else sanbaiman
		KiriageMangan: false, // 4 han 30 fu and 3 han 60 fu round up to mangan

		FuForOpenPinfu:      true,  // an open hand of pinfu shape gets 2 fu, reaching 30
		FuForPinfuTsumo:     false, // pinfu (no-points hand) by self-draw still gets the 2 tsumo fu
		FuForDoubleWindPair: 4,     // a pair of the wind that is both the seat and the round wind

		MaxRonWinners: 2,
		NagashiMangan: true, // at a draw, a river of only terminals and honors, none called, pays mangan

		AbortKyuushuKyuuhai: true, // nine kinds of terminals and honors in the first hand may abort it
		AbortFourWinds:      true, // all four first discards the same wind (suufon renda)
		AbortFourRiichi:     true, // all four players in riichi (suucha riichi)
		AbortFourKans:       true, // four kans by two or more players (suukaikan)
		AbortTripleRon:      true, // three players ron one discard (sanchahou)
	}
}
