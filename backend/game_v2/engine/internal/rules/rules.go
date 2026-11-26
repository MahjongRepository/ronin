// Package rules holds the rulesets a game plays under. A Ruleset holds only the settings the engine
// reads; a mechanic no ruleset varies is a constant in the package that uses it, and becomes a
// field when a ruleset needs it changed.
package rules

import (
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// Ruleset is the settings of one ruleset, scores in points and Uma in thousands. ShakkinRiichi lets a
// riichi be declared with fewer points than the stick, paying it into a negative score.
type Ruleset struct {
	StartingScore         int
	TargetScore           int
	WinningScoreThreshold int
	Tobi                  Tobi
	Agariyame             bool // the last hand's dealer, leading after a win or tenpai, ends the game instead of repeating
	WestRound             bool

	Uma                         [tile.SeatCount]int // placement bonus
	LeftoverRiichiSticksToFirst bool
	SplitTiedPlaces             bool
	RoundFinalPoints            bool

	RiichiMinWall          int // live wall tiles a riichi declaration needs left
	RiichiStickValue       int
	ShakkinRiichi          bool
	RiichiKanKeepsReadings bool
	HonbaValue             int // repeat counter, added to every win

	AkaDora                      tile.AkaDora // red fives, each an extra dora
	KanDoraImmediateForClosedKan bool         // turned at the kan, not at the next discard
	KanDoraImmediateForOpenKan   bool         // turned at the kan, not at the next discard

	OpenTanyao    bool // all simples (tanyao) counts in an open hand; kuitan
	DoubleYakuman bool // 13-wait kokushi, single-wait suuankou, 9-wait chuuren and big four winds pay double
	KazoeYakuman  bool // counted yakuman: 13+ han without a yakuman yaku pays a yakuman, else sanbaiman
	KiriageMangan bool // 4 han 30 fu and 3 han 60 fu round up to mangan
	Renhou        Renhou

	FuForOpenPinfu      bool // an open hand of pinfu shape gets 2 fu, reaching 30
	FuForPinfuTsumo     bool // pinfu (no-points hand) by self-draw still gets the 2 tsumo fu
	FuForDoubleWindPair int  // a pair of the wind that is both the seat and the round wind

	Atamahane               bool // of several rons on one discard only the nearest after the discarder wins
	MultiRonSticksToNearest bool // else each ron winner takes the honba and its own riichi stick, the nearest the rest
	PaoHonbaFromDiscarder   bool
	NagashiMangan           bool // at a draw, a river of only terminals and honors, none called, pays mangan

	AbortKyuushuKyuuhai bool // nine kinds of terminals and honors in the first hand may abort it
	AbortFourWinds      bool // all four first discards the same wind (suufon renda)
	AbortFourRiichi     bool // all four players in riichi (suucha riichi)
	AbortFourKans       bool // four kans by two or more players (suukaikan)
	AbortTripleRon      bool // three players ron one discard (sanchahou)
}

// Tobi is which score busts a player and ends the game at once.
type Tobi uint8

const (
	TobiOff       Tobi = iota
	TobiBelowZero      // a score under 0 busts; exactly 0 plays on
)

// Busts reports whether score busts a player under t.
func (t Tobi) Busts(score int) bool {
	switch t {
	case TobiBelowZero:
		return score < 0
	case TobiOff:
	}

	return false
}

// Renhou is what a non-dealer's ron before their first draw, with no call made, is worth.
type Renhou uint8

const (
	RenhouOff Renhou = iota
	RenhouMangan
)

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
	switch ruleset {
	case play.RulesetTenhou:
		return Tenhou(), true
	case play.RulesetRRC:
		return RRC(), true
	}

	return Ruleset{}, false
}
