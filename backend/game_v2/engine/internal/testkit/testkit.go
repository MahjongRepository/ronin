// Package testkit stages and drives games for the engine's scenario tests: tile ids from mpsz
// notation, a wall laid out from the hands, draws and dead wall a test names, the scripted actions
// that play it, and the events a test reads back. It never asserts: a helper returns its value or
// the error that stopped it, and the test asserts.
//
// It is imported only by external test packages, as package game_test, since it imports game.
//
// Ported from mahjong-rs's mahjong-game at commit 0d8733f: the shared helpers of its integration
// tests, tests/common.
package testkit

import (
	"errors"
	"slices"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/wall"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	deadWallStart    = wall.LiveWallSize
	firstDrawSlot    = tile.SeatCount * wall.StartingHandSize
	dealRoundSize    = 16
	dealBlocks       = 3
	dealBlockSize    = 4
	finalDealStart   = dealBlocks * dealRoundSize
	doraSlot         = 2
	firstKanDoraSlot = 3
	firstUraSlot     = 9
	maxRinshan       = 4
	maxKanDora       = 4
	maxUra           = 5
)

// Copies returns the tile ids of the tiles in mpsz, each kind's copies counted from first: the
// n-th repeat of a kind in mpsz takes copy first+n. A ParseTiles error for invalid notation, a
// CopyOutOfRangeError for a kind repeated past its fourth copy.
func Copies(first int, mpsz string) ([]tile.TileID, error) {
	parsed, err := tile.ParseTiles(mpsz)
	if err != nil {
		return nil, err
	}

	var seen [tile.KindCount]int
	ids := make([]tile.TileID, 0, len(parsed))
	for _, parsedTile := range parsed {
		kind := parsedTile.Kind()
		id, ok := tile.NewTileID(int(kind)*tile.CopiesPerKind + first + seen[kind])
		if !ok || first < 0 || first+seen[kind] >= tile.CopiesPerKind {
			return nil, CopyOutOfRangeError{Notation: mpsz}
		}
		ids = append(ids, id)
		seen[kind]++
	}
	return ids, nil
}

// CopyOutOfRangeError reports notation that repeats a kind past its fourth copy.
type CopyOutOfRangeError struct {
	Notation string
}

func (e CopyOutOfRangeError) Error() string {
	return strconv.Quote(e.Notation) + " repeats a kind past its copies"
}

type builder struct {
	err error
}

func (b *builder) copies(first int, mpsz string) []tile.TileID {
	ids, err := Copies(first, mpsz)
	b.err = errors.Join(b.err, err)
	return ids
}

func (b *builder) tile(first int, mpsz string) tile.TileID {
	return append(b.copies(first, mpsz), tile.TileID{})[0]
}

// StartWall is a wall laid out by role: each seat's dealt hand, by seat, at most 13 tiles; the
// live draws after the deal, in order; up to 4 rinshan tiles in draw order; the first dora
// indicator; up to 4 kan dora indicators; and up to 5 ura indicators. Every tile it leaves out
// fills the free places in id order.
type StartWall struct {
	Hands   [tile.SeatCount][]tile.TileID
	Draws   []tile.TileID
	Rinshan []tile.TileID
	Dora    play.Option[tile.TileID]
	KanDora []tile.TileID
	Ura     []tile.TileID
}

// UnplacedTiles returns every tile id w does not place, in id order.
func (w StartWall) UnplacedTiles() []tile.TileID {
	placed := w.placedTiles()
	var free []tile.TileID
	for _, id := range tile.AllTileIDs() {
		if !slices.Contains(placed, id) {
			free = append(free, id)
		}
	}
	return free
}

func (w StartWall) placedTiles() []tile.TileID {
	var placed []tile.TileID
	for _, held := range w.Hands {
		placed = append(placed, held...)
	}
	placed = append(placed, w.Draws...)
	placed = append(placed, w.Rinshan...)
	if w.Dora.OK {
		placed = append(placed, w.Dora.Value)
	}
	placed = append(placed, w.KanDora...)
	return append(placed, w.Ura...)
}

type placement struct {
	slot int
	id   tile.TileID
}

// Tiles returns w as the 136 tile ids of a wall dealt by dealer, in the layout of a Fixed wall
// source. A WallLayoutError when a role holds more tiles than it has places or a tile is placed
// twice.
func (w StartWall) Tiles(dealer tile.Seat) ([tile.TileIDCount]tile.TileID, error) {
	var tiles [tile.TileIDCount]tile.TileID
	for _, role := range []struct {
		name         string
		count, limit int
	}{
		{"hand", longest(w.Hands), wall.StartingHandSize},
		{"draws", len(w.Draws), deadWallStart - firstDrawSlot},
		{"rinshan", len(w.Rinshan), maxRinshan},
		{"kan dora", len(w.KanDora), maxKanDora},
		{"ura", len(w.Ura), maxUra},
	} {
		if role.count > role.limit {
			return tiles, WallLayoutError{Reason: "too many " + role.name + " tiles: " + strconv.Itoa(role.count)}
		}
	}

	placed := w.placedTiles()
	for i, id := range placed {
		if slices.Contains(placed[:i], id) {
			return tiles, WallLayoutError{Reason: "tile " + strconv.Itoa(id.Index()) + " is placed twice"}
		}
	}

	var filled [tile.TileIDCount]bool
	for _, p := range w.placements(dealer) {
		tiles[p.slot], filled[p.slot] = p.id, true
	}
	free := w.UnplacedTiles()
	for slot := range tiles {
		if !filled[slot] {
			tiles[slot], free = free[0], free[1:]
		}
	}
	return tiles, nil
}

func (w StartWall) placements(dealer tile.Seat) []placement {
	var placements []placement
	for _, seat := range tile.Seats() {
		for i, id := range w.Hands[seat.Index()] {
			placements = append(placements, placement{dealSlot(seat.DistanceFrom(dealer), i), id})
		}
	}
	for i, id := range w.Draws {
		placements = append(placements, placement{firstDrawSlot + i, id})
	}
	for i, id := range w.Rinshan {
		placements = append(placements, placement{deadWallStart + rinshanSlots()[i], id})
	}
	if w.Dora.OK {
		placements = append(placements, placement{deadWallStart + doraSlot, w.Dora.Value})
	}
	for i, id := range w.KanDora {
		placements = append(placements, placement{deadWallStart + firstKanDoraSlot + i, id})
	}
	for i, id := range w.Ura {
		placements = append(placements, placement{deadWallStart + firstUraSlot + i, id})
	}
	return placements
}

func rinshanSlots() [maxRinshan]int {
	return [maxRinshan]int{0, 7, 1, 8}
}

func dealSlot(offset, i int) int {
	if block := i / dealBlockSize; block < dealBlocks {
		return block*dealRoundSize + offset*dealBlockSize + i%dealBlockSize
	}
	return finalDealStart + offset
}

func longest(hands [tile.SeatCount][]tile.TileID) int {
	most := 0
	for _, held := range hands {
		most = max(most, len(held))
	}
	return most
}

// WallLayoutError reports a StartWall that cannot be laid out.
type WallLayoutError struct {
	Reason string
}

func (e WallLayoutError) Error() string {
	return "start wall: " + e.Reason
}

// FixedSetup returns the wall source of the one wall w, dealt from the start position's dealer or
// seat 0.
func FixedSetup(w StartWall, start play.Option[play.StartPosition]) (play.WallSource, error) {
	dealer := tile.Seats()[0]
	if start.OK {
		dealer = start.Value.Dealer
	}
	tiles, err := w.Tiles(dealer)
	return play.Fixed{Walls: [][tile.TileIDCount]tile.TileID{tiles}}, err
}

// BegunGame returns the game dealt from w alone, its dealer's first draw made.
func BegunGame(w StartWall, start play.Option[play.StartPosition]) (game.Game, error) {
	source, err := FixedSetup(w, start)
	if err != nil {
		return game.Game{}, err
	}

	g, _, err := game.New(source, start)
	return g, err
}

// SeatAction is one action of a seat.
type SeatAction struct {
	Seat   tile.Seat
	Action play.Action
}

// RefusedError reports a scripted action the game refused.
type RefusedError struct {
	SeatAction
	Refusal play.Refusal
}

func (e RefusedError) Error() string {
	return "seat " + strconv.Itoa(e.Seat.Index()) + "'s action of kind " + strconv.Itoa(int(e.Action.Kind())) +
		" is refused: " + e.Refusal.Code.String()
}

// Script plays actions in turn and returns the game after them and every event they caused. A
// RefusedError stops it at the first refused action, with the game and events before it.
func Script(g game.Game, actions ...SeatAction) (game.Game, []play.Emitted, error) {
	var events []play.Emitted
	for _, a := range actions {
		next, batch, refusal := g.Act(a.Seat, a.Action)
		if refusal.OK {
			return g, events, RefusedError{SeatAction: a, Refusal: refusal.Value}
		}
		g, events = next, append(events, batch...)
	}
	return g, events, nil
}

// TurnSeat returns the seat whose turn the game awaits; false when it awaits no turn.
func TurnSeat(g game.Game) (tile.Seat, bool) {
	turn, ok := g.Awaiting().(play.AwaitingTurn)
	return turn.Seat, ok
}

// Drawn returns the tile the turn seat drew; false when the game awaits no turn after a draw.
func Drawn(g game.Game) (tile.TileID, bool) {
	seat, _ := TurnSeat(g)
	decision, _ := g.Decision(seat)
	draw, ok := decision.Context.(play.TurnAfterDraw)
	return draw.Drawn, ok
}

// NoDrawnTileError reports a step that needs a turn after a draw where the game awaits none.
type NoDrawnTileError struct{}

func (NoDrawnTileError) Error() string {
	return "the game awaits no turn after a draw"
}

// DiscardDrawn has the turn seat discard the tile it drew, turns times. A NoDrawnTileError stops
// it where no turn after a draw is awaited.
func DiscardDrawn(g game.Game, turns int) (game.Game, []play.Emitted, error) {
	var events []play.Emitted
	var err error
	for i := 0; i < turns && err == nil; i++ {
		seat, _ := TurnSeat(g)
		drawn, ok := Drawn(g)
		if !ok {
			return g, events, NoDrawnTileError{}
		}

		var batch []play.Emitted
		g, batch, err = Script(g, SeatAction{seat, play.DiscardAction(drawn)})
		events = append(events, batch...)
	}
	return g, events, err
}

// NotInPlayError reports a step that needs a round in play where none is.
type NotInPlayError struct{}

func (NotInPlayError) Error() string {
	return "no round is in play"
}

// PlayDefaultsWhileLiveTilesExceed plays every awaited seat's default action until liveTiles or
// fewer live tiles are left. A NotInPlayError stops it when the round ends first.
func PlayDefaultsWhileLiveTilesExceed(g game.Game, liveTiles int) (game.Game, error) {
	var err error
	for err == nil && g.LiveTiles() > liveTiles {
		seats := awaitedSeats(g.Awaiting())
		if len(seats) == 0 {
			return g, NotInPlayError{}
		}

		actions := make([]SeatAction, 0, len(seats))
		for _, seat := range seats {
			action, _ := g.DefaultAction(seat)
			actions = append(actions, SeatAction{seat, action})
		}
		g, _, err = Script(g, actions...)
	}
	return g, err
}

func awaitedSeats(awaiting play.Awaiting) []tile.Seat {
	switch a := awaiting.(type) {
	case play.AwaitingTurn:
		return []tile.Seat{a.Seat}
	case play.AwaitingCall:
		return a.Seats
	case play.AwaitingRoundOver, play.AwaitingGameOver:
	}
	return nil
}

// NoPonError reports a seat that answers no call prompt or holds fewer than two copies of its
// tile's kind.
type NoPonError struct{}

func (NoPonError) Error() string {
	return "the seat has no pon to call"
}

// FirstPon returns the pon of seat's call prompt with the first two held copies of its tile's
// kind, in hand order. A NoPonError when seat answers no prompt or holds no pair of the kind.
func FirstPon(g game.Game, seat tile.Seat) (play.Action, error) {
	decision, _ := g.Decision(seat)
	call, ok := decision.Context.(play.Call)
	held := slices.Collect(tile.HeldCopies(g.Hand(seat), call.Tile.Kind()))
	if !ok || len(held) < 2 {
		return play.Action{}, NoPonError{}
	}
	return play.PonAction([2]tile.TileID{held[0], held[1]}), nil
}
