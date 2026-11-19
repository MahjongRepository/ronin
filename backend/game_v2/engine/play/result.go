package play

import "github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"

// RoundResult is how a round ended: ExhaustiveDraw, Tsumo, Ron or Abortive.
//
//sumtype:decl
type RoundResult interface {
	isRoundResult()
	TotalScoreChanges() [tile.SeatCount]int
}

// ExhaustiveDraw is a round whose live wall ran out: each tenpai seat's hand and each nagashi
// mangan seat's river, in seat order, and the payments by seat, nagashi mangan ones in place of
// noten ones.
type ExhaustiveDraw struct {
	Tenpai       []ShownHand
	Nagashi      []NagashiRiver
	ScoreChanges [tile.SeatCount]int
}

// Tsumo is a round a seat won on its own draw.
type Tsumo struct {
	Win WinResult
}

// Ron is a round one or two seats won on Discarder's tile, the closer after it first; HeadBumped
// declared ron too but lost to them.
type Ron struct {
	Discarder  tile.Seat
	Wins       []WinResult
	HeadBumped []tile.Seat
}

// Abortive is a round aborted with no payments.
type Abortive struct {
	Kind AbortKind
}

func (ExhaustiveDraw) isRoundResult() {}
func (Tsumo) isRoundResult()          {}
func (Ron) isRoundResult()            {}
func (Abortive) isRoundResult()       {}

// TotalScoreChanges returns what the draw moved by seat.
func (r ExhaustiveDraw) TotalScoreChanges() [tile.SeatCount]int {
	return r.ScoreChanges
}

// TotalScoreChanges returns what the win moved by seat.
func (r Tsumo) TotalScoreChanges() [tile.SeatCount]int {
	return r.Win.ScoreChanges
}

// TotalScoreChanges returns what the round moved by seat, every win of a double ron together.
func (r Ron) TotalScoreChanges() [tile.SeatCount]int {
	var total [tile.SeatCount]int
	for _, win := range r.Wins {
		for seat, change := range win.ScoreChanges {
			total[seat] += change
		}
	}
	return total
}

// TotalScoreChanges returns nothing moved: an aborted round pays nobody.
func (Abortive) TotalScoreChanges() [tile.SeatCount]int {
	return [tile.SeatCount]int{}
}

// AbortKind is why a round was aborted, and the seats that caused it: KyuushuKyuuhai, FourWinds,
// FourRiichi, FourKans or TripleRon.
//
//sumtype:decl
type AbortKind interface {
	isAbortKind()
}

// KyuushuKyuuhai is Seat showing nine kinds of terminals and honors on its first uninterrupted
// turn; Hand is its whole hand of 14 tiles, in hand order.
type KyuushuKyuuhai struct {
	Seat tile.Seat
	Hand []tile.TileID
}

// FourWinds is the first four discards being the same wind.
type FourWinds struct{}

// FourRiichi is every seat declaring riichi; Hands are their hands, in seat order.
type FourRiichi struct {
	Hands []ShownHand
}

// FourKans is the fourth kan of the round, not all by one seat, whose replacement discard passed.
type FourKans struct{}

// TripleRon is three seats declaring ron on Discarder's Tile. Hands are the declaring seats'
// hands in caller order, the closest after the discarder first, without the ron tile; RobbedKan
// is the kan the rons robbed, absent for rons on a discard.
type TripleRon struct {
	Discarder tile.Seat
	Tile      tile.TileID
	Hands     []ShownHand
	RobbedKan Option[KanKind]
}

func (KyuushuKyuuhai) isAbortKind() {}
func (FourWinds) isAbortKind()      {}
func (FourRiichi) isAbortKind()     {}
func (FourKans) isAbortKind()       {}
func (TripleRon) isAbortKind()      {}

// ShownHand is a seat's hand shown when the round ends: a tenpai hand at an exhaustive draw, the
// riichi hands at four riichi and the declarers' hands at a triple ron. Hand holds the concealed
// tiles in hand order, Melds the declared melds in call order.
type ShownHand struct {
	Seat  tile.Seat
	Hand  []tile.TileID
	Melds []MeldView
}

// NagashiRiver is the river that earned a seat its nagashi mangan, every discard as it fell.
type NagashiRiver struct {
	Seat  tile.Seat
	River []RiverTile
}

// WinResult is one seat's win and what it was paid. Loser is the discarder on a ron, absent on a
// tsumo; Hand holds the concealed tiles without the winning tile, in hand order, and Melds the
// declared melds in call order. Value counts the dora; Limit is absent below mangan. Yaku is
// sorted by yaku id, the dora counted in Dora instead. UraIndicators are the ura dora indicators
// a riichi winner counted, empty without a riichi. Pao is the seat liable for the yakuman its
// discard completed, having fed the winner's third dragon or fourth wind pon. ScoreChanges is
// what this win moved by seat: the hand, the honba and the riichi sticks it took.
type WinResult struct {
	Winner        tile.Seat
	Loser         Option[tile.Seat]
	Hand          []tile.TileID
	Melds         []MeldView
	WinTile       tile.TileID
	Value         Value
	Limit         Option[Limit]
	Yaku          []YakuID
	Dora          DoraCount
	UraIndicators []tile.TileID
	Pao           Option[tile.Seat]
	ScoreChanges  [tile.SeatCount]int
}

// GameEndCause is the rule that ended a game: a score fell below the tobi threshold; South ended
// with a seat at the winning threshold, or its last dealer stopped in first place there; a seat
// reached the winning threshold in the West extension; West 4 ended with no seat at it; or every
// wall of a fixed-wall setup was dealt and the game asked for one more.
type GameEndCause uint8

// The game end causes.
const (
	EndTobi GameEndCause = iota
	EndLength
	EndTargetReached
	EndExtensionLimit
	EndFixedWallsDealt
)

// Standings are the end of a game: why it ended, the final scores by seat with the riichi sticks
// left on the table added to first place, the place of each seat from 1 to 4 (by score, a tie to
// the seat nearer after the first dealer), and the uma- and oka-adjusted points by seat in tenths
// of a point, 100 of score each, unrounded, summing to 0.
type Standings struct {
	Cause      GameEndCause
	Scores     [tile.SeatCount]int
	Placements [tile.SeatCount]int
	Points     [tile.SeatCount]int
}
