package play

import "github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"

// Visibility is who may see an event: every seat, or one seat only. Its zero value includes no
// seat, so an event emitted without one is hidden rather than shown to the table.
type Visibility struct {
	seat   tile.Seat
	single bool
	all    bool
}

// ToAll returns the Visibility of every seat.
func ToAll() Visibility {
	return Visibility{all: true}
}

// ToSeat returns the Visibility of seat only.
func ToSeat(seat tile.Seat) Visibility {
	return Visibility{seat: seat, single: true}
}

// Seat returns the only seat that may see; false when every seat or no seat may.
func (v Visibility) Seat() (tile.Seat, bool) {
	return v.seat, v.single
}

// All reports whether every seat may see.
func (v Visibility) All() bool {
	return v.all
}

// Includes reports whether seat may see.
func (v Visibility) Includes(seat tile.Seat) bool {
	return v.all || (v.single && v.seat == seat)
}

// Emitted is one fact of the game and who may see it.
type Emitted struct {
	To    Visibility
	Event Event
}

// Event is one fact of a game: GameStarted, RoundStarted, Drew, DrewNotice, Discarded,
// RiichiDeposited, FuritenChanged, Called, PaoAssigned, DoraRevealed, RoundEnded or GameEnded.
//
//sumtype:decl
type Event interface {
	isEvent()
}

// GameStarted reports the game set up: the first dealer and the two throws that chose it, the
// ruleset it plays under, whether that ruleset tells the red fives apart and the points a riichi
// stick is worth. Seen by all.
type GameStarted struct {
	FirstDealer      tile.Seat
	Dice             [2]tile.Dice
	Ruleset          Ruleset
	AkaDora          tile.AkaDora
	RiichiStickValue int
}

// RoundStarted reports a round dealt, one event per seat with that seat's own hand, the dora
// indicators and the live tiles left. Seen by Seat only.
type RoundStarted struct {
	Seat           tile.Seat
	Header         RoundHeader
	Scores         [tile.SeatCount]int
	Hand           []tile.TileID
	DoraIndicators []tile.TileID
	LiveTiles      int
}

// Drew reports that Seat drew Tile, from the dead wall when Rinshan. Seen by Seat only.
type Drew struct {
	Seat    tile.Seat
	Tile    tile.TileID
	Rinshan bool
}

// DrewNotice reports that Seat drew a tile. Seen by each other seat, one event each.
type DrewNotice struct {
	Seat    tile.Seat
	Rinshan bool
}

// Discarded reports that Seat discarded Tile; Tsumogiri when it is the tile just drawn, Riichi
// when the discard declares riichi. Seen by all.
type Discarded struct {
	Seat      tile.Seat
	Tile      tile.TileID
	Tsumogiri bool
	Riichi    bool
}

// RiichiDeposited reports that Seat's riichi discard passed every ron and its stick is on the
// table: its Score and the RiichiSticks after it. Seen by all.
type RiichiDeposited struct {
	Seat         tile.Seat
	Score        int
	RiichiSticks int
}

// FuritenChanged reports Seat's furiten as it now shows to the seat. Seen by Seat only.
type FuritenChanged struct {
	Seat    tile.Seat
	Furiten bool
}

// Called reports that Seat declared Meld: after a chi or pon its turn has no draw, after a kan a
// rinshan draw once no chankan robs it. Seen by all.
type Called struct {
	Seat tile.Seat
	Meld MeldView
}

// PaoAssigned reports that Liable fed the call just made that completes Seat's third dragon or
// fourth wind set, so pays for its yakuman. Seen by all.
type PaoAssigned struct {
	Seat   tile.Seat
	Liable tile.Seat
}

// DoraRevealed reports a kan dora indicator turned over. Seen by all.
type DoraRevealed struct {
	Indicator tile.TileID
}

// RoundEnded reports the round ended: its result, the scores after it and the riichi sticks left
// on the table. Seen by all.
type RoundEnded struct {
	Result       RoundResult
	Scores       [tile.SeatCount]int
	RiichiSticks int
}

// GameEnded reports the game ended, right after its last RoundEnded. Seen by all.
type GameEnded struct {
	Standings Standings
}

func (GameStarted) isEvent()     {}
func (RoundStarted) isEvent()    {}
func (Drew) isEvent()            {}
func (DrewNotice) isEvent()      {}
func (Discarded) isEvent()       {}
func (RiichiDeposited) isEvent() {}
func (FuritenChanged) isEvent()  {}
func (Called) isEvent()          {}
func (PaoAssigned) isEvent()     {}
func (DoraRevealed) isEvent()    {}
func (RoundEnded) isEvent()      {}
func (GameEnded) isEvent()       {}

// MeldKind is what kind of meld a MeldView is.
type MeldKind uint8

const (
	MeldChi MeldKind = iota
	MeldPon
	MeldOpenKan
	MeldAddedKan
	MeldClosedKan
)

// MeldView is a declared meld as the table sees it: every tile of it, the called one included,
// sorted by id; the tile called from a discard, for an added kan the one its pon called; the seat
// whose discard was called; and for an added kan the copy it raised its pon with. A closed kan has
// neither Called nor From, and only an added kan has Added.
type MeldView struct {
	Kind   MeldKind
	Tiles  []tile.TileID
	Called Option[tile.TileID]
	From   Option[tile.Seat]
	Added  Option[tile.TileID]
}

// Call returns the call that declared m: a chi or pon with its two tiles from the hand, or an open
// kan. False for an added or closed kan, which no call of a discard declares, and for a chi or pon
// whose tiles are not its called tile and two more.
func (m MeldView) Call() (MeldCall, bool) {
	if m.Kind == MeldOpenKan {
		return OpenKanCall{}, true
	}

	if (m.Kind != MeldChi && m.Kind != MeldPon) || !m.Called.OK {
		return nil, false
	}

	var held [2]tile.TileID
	count := 0
	for _, t := range m.Tiles {
		if t == m.Called.Value {
			continue
		}

		if count == len(held) {
			return nil, false
		}

		held[count] = t
		count++
	}

	if count != len(held) {
		return nil, false
	}

	if m.Kind == MeldChi {
		return ChiCall{Held: held}, true
	}

	return PonCall{Held: held}, true
}

// MeldCall is a meld call a seat answered its prompt with: PonCall, ChiCall or OpenKanCall.
//
//sumtype:decl
type MeldCall interface {
	isMeldCall()
}

// PonCall is a pon with its two held tiles.
type PonCall struct {
	Held [2]tile.TileID
}

// ChiCall is a chi with its two held tiles.
type ChiCall struct {
	Held [2]tile.TileID
}

// OpenKanCall is an open kan of the prompt's discard.
type OpenKanCall struct{}

func (PonCall) isMeldCall()     {}
func (ChiCall) isMeldCall()     {}
func (OpenKanCall) isMeldCall() {}

// RiverTile is a discard as it lies in its seat's river: Tsumogiri when it was the tile just
// drawn, Riichi when it declared the seat's riichi.
type RiverTile struct {
	Tile      tile.TileID
	Tsumogiri bool
	Riichi    bool
}

// RoundHeader is where a round stands in the game, fixed when it is dealt: RoundNumber counts
// every hand of the game from 0, repeats included; RoundInWind is the round within its wind, 1 to
// 4; RiichiSticks are the sticks on the table at the deal; Dice broke the round's wall.
type RoundHeader struct {
	RoundNumber  uint32
	Wind         tile.Wind
	RoundInWind  int
	Dealer       tile.Seat
	Honba        int
	RiichiSticks int
	Dice         tile.Dice
}
