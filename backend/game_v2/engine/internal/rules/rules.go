// Package rules holds the rulesets a game plays under. A Ruleset holds only the settings the engine
// reads; a mechanic no ruleset varies is a constant in the package that uses it, and becomes a
// field when a ruleset needs it changed.
package rules

import (
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// Ruleset is the settings of one ruleset. Scores are in points; Uma is in thousands of points,
// first place to fourth. HonbaValue is what each honba counter adds to a win, which a tsumo's
// payers split evenly. MaxRonWinners is how many rons on one discard win, the seats nearest the
// discarder first: 1 is head bump.
type Ruleset struct {
	StartingScore         int
	TargetScore           int
	WinningScoreThreshold int
	Tobi                  bool // bust: a score below TobiThreshold ends the game at once
	TobiThreshold         int
	Agariyame             bool // the last hand's dealer, leading after a win or tenpai, ends the game instead of repeating

	Uma                         [tile.SeatCount]int // placement bonus
	LeftoverRiichiSticksToFirst bool
	RoundFinalPoints            bool

	RiichiMinWall    int // live wall tiles a riichi declaration needs left
	RiichiStickValue int
	HonbaValue       int // repeat counter, added to every win

	AkaDora                      tile.AkaDora // red fives, each an extra dora
	KanDoraImmediateForClosedKan bool         // turned at the kan, not at the next discard
	KanDoraImmediateForOpenKan   bool         // turned at the kan, not at the next discard

	OpenTanyao    bool // all simples (tanyao) counts in an open hand; kuitan
	DoubleYakuman bool // 13-wait kokushi, single-wait suuankou, 9-wait chuuren and big four winds pay double
	KazoeYakuman  bool // counted yakuman: 13+ han without a yakuman yaku pays a yakuman, else sanbaiman
	KiriageMangan bool // 4 han 30 fu and 3 han 60 fu round up to mangan

	FuForOpenPinfu      bool // an open hand of pinfu shape gets 2 fu, reaching 30
	FuForPinfuTsumo     bool // pinfu (no-points hand) by self-draw still gets the 2 tsumo fu
	FuForDoubleWindPair int  // a pair of the wind that is both the seat and the round wind

	MaxRonWinners int
	NagashiMangan bool // at a draw, a river of only terminals and honors, none called, pays mangan

	AbortKyuushuKyuuhai bool // nine kinds of terminals and honors in the first hand may abort it
	AbortFourWinds      bool // all four first discards the same wind (suufon renda)
	AbortFourRiichi     bool // all four players in riichi (suucha riichi)
	AbortFourKans       bool // four kans by two or more players (suukaikan)
	AbortTripleRon      bool // three players ron one discard (sanchahou)
}

// Known reports whether ruleset names a ruleset.
func Known(ruleset play.Ruleset) bool {
	_, known := lookup(ruleset)
	return known
}

// Of returns the settings of ruleset. It panics with a play.EngineFaultError for a ruleset Known
// refuses, which no game holds past its setup.
func Of(ruleset play.Ruleset) Ruleset {
	settings, known := lookup(ruleset)
	if !known {
		panic(play.EngineFaultError{Err: UnknownRulesetError{Ruleset: ruleset}})
	}

	return settings
}

// UnknownRulesetError reports a Ruleset that names no ruleset.
type UnknownRulesetError struct {
	Ruleset play.Ruleset
}

func (e UnknownRulesetError) Error() string {
	return "unknown ruleset " + strconv.Itoa(int(e.Ruleset))
}

func lookup(ruleset play.Ruleset) (Ruleset, bool) {
	switch ruleset { //nolint:gocritic // a switch, so exhaustive flags a ruleset added without its case
	case play.RulesetTenhou:
		return Tenhou(), true
	}

	return Ruleset{}, false
}
