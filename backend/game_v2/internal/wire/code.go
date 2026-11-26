package wire

// A code is never renumbered or reused.
type EventType uint8

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

type ResultType uint8

const (
	ResultTsumo          ResultType = 0
	ResultRon            ResultType = 1
	ResultExhaustiveDraw ResultType = 3
	ResultAbortiveDraw   ResultType = 4
)

type AbortReason string

const (
	AbortNineTerminals AbortReason = "nine_terminals"
	AbortFourWinds     AbortReason = "four_winds"
	AbortFourRiichi    AbortReason = "four_riichi"
	AbortFourKans      AbortReason = "four_kans"
	AbortTripleRon     AbortReason = "triple_ron"
)

type SeatControlReason uint8

const (
	SeatControlLeft   SeatControlReason = 0
	SeatControlAbsent SeatControlReason = 1
)

type CallType uint8

const (
	CallRon     CallType = 0
	CallMeld    CallType = 1
	CallChankan CallType = 2
)

type MeldCallType uint8

const (
	MeldCallPon     MeldCallType = 0
	MeldCallChi     MeldCallType = 1
	MeldCallOpenKan MeldCallType = 2
)

type PlayerAction uint8

const (
	ActionDiscard  PlayerAction = 0
	ActionRiichi   PlayerAction = 1
	ActionTsumo    PlayerAction = 2
	ActionKan      PlayerAction = 3
	ActionAddedKan PlayerAction = 4
	ActionKyuushu  PlayerAction = 5
)

type GameType uint8

const GameHanchan GameType = 0

const (
	YakuIDDora    = 120
	YakuIDAkaDora = 121
	YakuIDUraDora = 122
)

const (
	HandLimitNone         = "none"
	HandLimitKazoeYakuman = "kazoe_yakuman"
)
