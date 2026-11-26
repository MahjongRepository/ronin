package play

import "github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"

// CallSource is what a call prompt offers a tile from.
type CallSource uint8

const (
	SourceDiscard CallSource = iota
	SourceAddedKan
	SourceClosedKan
)

// DecisionContext is where the awaited seat stands: TurnAfterDraw, TurnAfterCall or Call.
//
//sumtype:decl
type DecisionContext interface {
	isDecisionContext()
}

// TurnAfterDraw is the seat's turn after a draw: the drawn tile, whether it came from the dead
// wall, and whether it was the last live tile.
type TurnAfterDraw struct {
	Drawn   tile.TileID
	Rinshan bool
	Haitei  bool
}

// TurnAfterCall is the seat's turn after its own call; Kuikae holds the kinds kuikae forbids it
// to discard.
type TurnAfterCall struct {
	Kuikae []tile.Kind
}

// Call is a call prompt on Tile from seat From; Houtei when it is the last discard of the round.
type Call struct {
	Tile   tile.TileID
	From   tile.Seat
	Source CallSource
	Houtei bool
}

func (TurnAfterDraw) isDecisionContext() {}
func (TurnAfterCall) isDecisionContext() {}
func (Call) isDecisionContext()          {}

// Decision is the single source of a seat's current prompt: where it stands, every action the
// engine accepts from it now in Legal, and the action a timeout plays in Default, never a win and
// never a call.
type Decision struct {
	Seat    tile.Seat
	Context DecisionContext
	Legal   []Action
	Default Action
}

// Awaiting is what the game waits for: AwaitingDealt, AwaitingTurn, AwaitingCall,
// AwaitingRoundOver or AwaitingGameOver.
//
//sumtype:decl
type Awaiting interface {
	isAwaiting()
}

// AwaitingDealt waits for the dealer's first draw of a round just dealt.
type AwaitingDealt struct{}

// AwaitingTurn waits for the turn of Seat.
type AwaitingTurn struct {
	Seat tile.Seat
}

// AwaitingCall lists the seats still to answer in seat order. A claim can close another seat's offer.
type AwaitingCall struct {
	Seats []tile.Seat
}

// AwaitingRoundOver waits for the next round to be dealt.
type AwaitingRoundOver struct{}

// AwaitingGameOver waits for nothing more.
type AwaitingGameOver struct{}

func (AwaitingDealt) isAwaiting()     {}
func (AwaitingTurn) isAwaiting()      {}
func (AwaitingCall) isAwaiting()      {}
func (AwaitingRoundOver) isAwaiting() {}
func (AwaitingGameOver) isAwaiting()  {}
