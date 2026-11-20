package offer

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/score"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// Furiten is the flags that forbid a seat's ron, and the value it is shown. Temporary is a ron
// passed or missed, cleared by the seat's next discard; Riichi a ron a riichi seat passed or
// missed, lasting the round; Shown the value the seat was last shown. The zero value is no
// furiten.
type Furiten struct {
	Temporary bool
	Riichi    bool
	Shown     bool
}

// BlocksRon reports whether the flags forbid a ron.
func (f Furiten) BlocksRon() bool {
	return f.Temporary || f.Riichi
}

// DeclineRon returns f after its seat answered its ron prompt without the ron: temporary
// furiten, and riichi furiten too when inRiichi.
func (f Furiten) DeclineRon(inRiichi bool) Furiten {
	f.Temporary = true
	f.Riichi = f.Riichi || inRiichi
	return f
}

// MissRon returns f after its seat's winning tile passed without a ron prompt: riichi furiten
// when inRiichi, else temporary furiten.
func (f Furiten) MissRon(inRiichi bool) Furiten {
	if inRiichi {
		f.Riichi = true
	} else {
		f.Temporary = true
	}
	return f
}

// IsDiscardFuriten reports whether the seat has discarded one of its waits.
func IsDiscardFuriten(waits tile.Kinds, river []play.RiverTile) bool {
	return slices.ContainsFunc(river, func(discard play.RiverTile) bool { return waits.Contains(discard.Tile.Kind()) })
}

// RonCandidate is the seat a ron or chankan is judged for: its concealed tiles, melds, river and
// furiten flags.
type RonCandidate struct {
	Hand    []tile.TileID
	Melds   []play.MeldView
	River   []play.RiverTile
	Furiten Furiten
}

func (c RonCandidate) waits() tile.Kinds {
	return hand.Waits(countsOfDistinctIDs(c.Hand), countsOfDistinctIDs(meldedTiles(c.Melds)))
}

func (c RonCandidate) isBlocked(waits tile.Kinds) bool {
	return c.Furiten.BlocksRon() || IsDiscardFuriten(waits, c.River)
}

// RonOutcome is what a discard is to a seat it might complete.
type RonOutcome uint8

// The ron outcomes: the tile does not complete the hand; it completes the hand but furiten or no
// yaku forbids the ron; or the ron is offered.
const (
	RonNotComplete RonOutcome = iota
	RonMissed
	RonOffered
)

// DiscardRon returns whether candidate is offered the ron on a discarded tile in situation,
// scored with no dora since dora never makes a yaku. It panics with a play.EngineFaultError when
// the scorer rejects the completed hand for anything but no yaku.
func DiscardRon(candidate RonCandidate, discard tile.TileID, situation score.Situation) RonOutcome {
	if !Completes(candidate.Hand, discard) {
		return RonNotComplete
	}
	if candidate.isBlocked(candidate.waits()) {
		return RonMissed
	}

	scoring := Scoring{Situation: situation, Melds: candidate.Melds}
	if _, ok := OfferedValue(candidate.Hand, discard, scoring); !ok {
		return RonMissed
	}
	return RonOffered
}

// MayRobKan reports whether candidate may rob a kan of kind on its tile: it waits on the tile, is
// not furiten, and on a closed kan holds a thirteen orphans wait.
func MayRobKan(candidate RonCandidate, kind play.KanKind, robbed tile.TileID) bool {
	waits := candidate.waits()
	return waits.Contains(robbed.Kind()) &&
		!candidate.isBlocked(waits) &&
		(kind == play.KanAdded || IsKokushiTenpai(candidate.Hand))
}

// RonWin returns how a ron on a call prompt's tile with liveTiles left is won: houtei on the last
// discard, chankan on a kan's tile, else ron.
func RonWin(source play.CallSource, liveTiles int) score.Win {
	if IsHoutei(liveTiles, source) {
		return score.WinHoutei
	}
	if source == play.SourceDiscard {
		return score.WinRon
	}
	return score.WinChankan
}

// BaseSituation returns what a win is scored with besides the tiles, with no first turn, honba or
// riichi sticks.
func BaseSituation(win score.Win, seatWind, roundWind tile.Wind, riichi play.Option[play.Riichi]) score.Situation {
	return score.Situation{Win: win, Riichi: riichi, SeatWind: seatWind, RoundWind: roundWind}
}
