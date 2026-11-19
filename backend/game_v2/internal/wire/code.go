package wire

// EventType is a record's kind, the value of KeyEventType: an event of the game, an opening built
// for one seat's decision (EventCallPrompt, EventTurn), or a replay-only line (EventSeatControl,
// apart from the live codes). A code is never renumbered or reused.
type EventType uint8

// The event types.
const (
	EventMeld           EventType = 0
	EventDraw           EventType = 1
	EventDiscard        EventType = 2
	EventCallPrompt     EventType = 3
	EventRoundEnd       EventType = 4
	EventRiichiDeclared EventType = 5
	EventDoraRevealed   EventType = 6
	EventError          EventType = 7
	EventGameStarted    EventType = 8
	EventRoundStarted   EventType = 9
	EventGameEnd        EventType = 10
	EventFuriten        EventType = 11
	EventTurn           EventType = 12
	EventDrawNotice     EventType = 13
	EventPaoAssigned    EventType = 14
	EventSeatControl    EventType = 101
)

// ResultType is how a round ended, the value of KeyResultType on a round end. A ron carries its one
// or two wins under KeyWinners, and an exhaustive draw its nagashi mangan rivers; codes 2 and 5,
// the double ron and nagashi mangan of replay version 0.4-dev, are retired.
type ResultType uint8

// The result types.
const (
	ResultTsumo          ResultType = 0
	ResultRon            ResultType = 1
	ResultExhaustiveDraw ResultType = 3
	ResultAbortiveDraw   ResultType = 4
)

// SeatControlReason is why an AI player stands in for a participant: it left during play, or it
// never joined.
type SeatControlReason uint8

// The seat control reasons.
const (
	SeatControlLeft   SeatControlReason = 0
	SeatControlAbsent SeatControlReason = 1
)

// CallType is a call prompt's type: the seat may ron (and meld instead when it can), only meld, or
// rob a kan.
type CallType uint8

// The call types.
const (
	CallRon     CallType = 0
	CallMeld    CallType = 1
	CallChankan CallType = 2
)

// MeldCallType is a meld a call prompt offers.
type MeldCallType uint8

// The meld call types.
const (
	MeldCallPon     MeldCallType = 0
	MeldCallChi     MeldCallType = 1
	MeldCallOpenKan MeldCallType = 2
)

// PlayerAction is an action a draw offers its seat.
type PlayerAction uint8

// The player actions.
const (
	ActionDiscard  PlayerAction = 0
	ActionRiichi   PlayerAction = 1
	ActionTsumo    PlayerAction = 2
	ActionKan      PlayerAction = 3
	ActionAddedKan PlayerAction = 4
	ActionKyuushu  PlayerAction = 5
)

// GameType is the length of a game: only the hanchan is played; code 1, the tonpuusen, is retired.
type GameType uint8

// GameHanchan is the east and south game.
const GameHanchan GameType = 0
