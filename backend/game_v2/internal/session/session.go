// Package session runs the live games: the registry of pending and playing games, and one
// goroutine per game that owns everything about it, from its participants and their connections to
// the engine game, the waits it opens, the pacing timers, the AI players and the one end.
//
// A Manager is the registry. Connections, timers and lobby calls reach a game only through its
// goroutine, one step at a time, so a game's state needs no lock; the registry's own maps (games,
// tickets, connections and what each is bound to) sit behind one mutex, under which the operations
// that span games stay atomic: a game's creation with its checks, its end claim releasing its
// tickets, a binding racing an eviction. A timer's firing reaches the game as a step of its own and
// is dropped when the timer was cancelled or re-armed meanwhile.
//
// Sends and closes only queue on the Connection, so no step waits on a client. Every time the
// session reads, its timers included, comes from its Clock.
//
// Ported from ronin's Python session manager, its models, timers, seating, AI player and replay
// collector.
package session

import (
	"context"
	"crypto/rand"
	"errors"
	"log/slog"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replayfile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
)

// Timing is the pacing of every game: the free base time of a turn or call, the bank a seat's
// turns and calls share past it, reset to full at each hand's first wait, the round advance pause
// per result shown, how long a pending game waits for its players, the game start's confirmation
// (zero skips it, and the dealer draws at once) and the delay ahead of each AI player's turn (zero
// plays them at once).
type Timing struct {
	BaseTurn         time.Duration
	InitialBank      time.Duration
	RoundAdvance     time.Duration
	PendingGame      time.Duration
	GameStartConfirm time.Duration
	AITurnDelay      time.Duration
}

// DefaultTiming returns the production pacing: 10 s turns over a 20 s bank, 15 s per round result,
// 30 s for a pending game, 10 s to confirm the start and 1 s ahead of each AI turn.
func DefaultTiming() Timing {
	return Timing{
		BaseTurn:         10 * time.Second,
		InitialBank:      20 * time.Second,
		RoundAdvance:     15 * time.Second,
		PendingGame:      30 * time.Second,
		GameStartConfirm: 10 * time.Second,
		AITurnDelay:      time.Second,
	}
}

// Clock is where the session reads time and arms its timers. AfterFunc runs f on its own goroutine
// once d has passed and returns the function that cancels it, which reports whether it stopped f
// from running.
type Clock interface {
	Now() time.Time
	AfterFunc(d time.Duration, f func()) (stop func() bool)
}

// SystemClock returns the Clock of the time package.
func SystemClock() Clock {
	return systemClock{}
}

type systemClock struct{}

func (systemClock) Now() time.Time {
	return time.Now()
}

func (systemClock) AfterFunc(d time.Duration, f func()) func() bool {
	return time.AfterFunc(d, f).Stop
}

// CloseCode is the WebSocket close code the session closes a connection with.
type CloseCode int

// The close codes: a normal end, a protocol violation, a server fault, a connection that never
// authenticated, and one replaced by its participant's newer one, whose client stops reconnecting.
const (
	CloseGameEnded     CloseCode = 1000
	CloseInvalidAction CloseCode = 1008
	CloseInternalError CloseCode = 1011
	CloseAuthTimeout   CloseCode = 4001
	CloseReplaced      CloseCode = 4002
)

// Connection is one client socket as the session sees it: its id, the game id of its URL, and its
// queued sends and close. Send and Close never wait on the socket and never fail for a dead or slow
// one; Close is idempotent and nothing is sent after it. Both are safe for concurrent use.
type Connection interface {
	ID() string
	GameID() string
	Send(readOnlyData []byte)
	Close(code CloseCode, reason string)
}

// PlayerSpec is one expected human of a game: its name, its lobby user id, and the game ticket the
// lobby signed for it, which keys its participant for the whole game.
type PlayerSpec struct {
	Name   string
	UserID string
	Ticket string
}

// Seating is how a game seats its players. The zero value, SeatingShuffled, seats them by the
// seed's seat permutation; SeatingFixed seats them in input order from the seed's first dealer, the
// first East, then South, West and North.
type Seating int

const (
	SeatingShuffled Seating = iota
	SeatingFixed
)

// Agent answers the decisions of AI seats. Decide gets the AI seat's view, its decision included,
// and returns the action to play. Each call runs on a goroutine of its own, and a game waits for
// one answer at a time, its turns and calls alike, and stops waiting once the base turn time
// passed: ctx is done then, when the answer is no longer wanted, and when the game ends, and Decide
// must return once it is. One Agent serves every game of a Manager, and a call whose answer a game
// stopped waiting for may still run when the game asks its next, so Decide is called concurrently
// and must be safe for concurrent use. An error, a missed deadline or an action the decision does
// not offer plays the decision's default instead; a panic fails the game.
type Agent interface {
	Decide(ctx context.Context, view play.SeatView) (play.Action, error)
}

// Config is what a Manager runs on. DB and Logger are required; a nil Clock is SystemClock, a nil
// Seeds draws each game's seed from crypto/rand, a nil Setup deals every game from its seed, and a
// nil Agent plays each AI decision's default, asked like any Agent off the game's goroutine.
// Setup turns a game's seed into its engine setup, for a harness that stages its walls.
// DiscardHold gives, per discard and per closed or added kan, how long the session holds what
// follows it (the next draw, a call's outcome, the round's end) so that one nobody could answer and
// one answered within the hold look alike; a call still open then is waited out instead, so a slow
// answer still shows. Nil holds nothing.
// Pick returns a random index below the count it is given, and must be safe for concurrent use. With
// it the session plays a pon, a chi or a closed kan with copies picked among those that look the
// same (engine.Game.Disguised), and a timeout or an AI player's default after the seat's own call
// discards a picked legal tile, so neither tells the table the seat's hand order. Nil plays every
// action as named and the engine's own default.
// ObserveDelay is how long after the session collects a replay record an observer may get it; zero
// is DefaultObserveDelay.
type Config struct {
	Timing   Timing
	Capacity int
	DB       *store.DB
	Replays  replayfile.Dir
	Logger   *slog.Logger
	Clock    Clock
	Seeds    func() engine.Seed
	Setup    func(engine.Seed) engine.Setup
	Agent    Agent

	DiscardHold  func() time.Duration
	Pick         func(n int) int
	ObserveDelay time.Duration
}

// The errors CreatePendingGame returns.
var (
	ErrGameExists    = errors.New("a game with this id already exists")
	ErrGameWithdrawn = errors.New("the game was withdrawn")
	ErrPlayerPlaying = errors.New("a player is already in a game")
	ErrAtCapacity    = errors.New("the server is at capacity")
	ErrShuttingDown  = errors.New("the server is shutting down")
	ErrPlayerCount   = errors.New("a game seats one to four players")
)

// ErrConfig is returned by New for a Config it cannot run on.
var ErrConfig = errors.New("invalid session config")

func (c Config) validated() (Config, error) {
	t := c.Timing
	switch {
	case c.DB == nil || c.Logger == nil:
		return c, ErrConfig
	case t.BaseTurn < 0 || t.GameStartConfirm < 0 || t.AITurnDelay < 0:
		return c, ErrConfig
	case t.InitialBank <= 0 || t.RoundAdvance <= 0 || t.PendingGame <= 0 || c.Capacity <= 0:
		return c, ErrConfig
	case c.ObserveDelay < 0:
		return c, ErrConfig
	}
	if c.ObserveDelay == 0 {
		c.ObserveDelay = DefaultObserveDelay
	}
	if c.Clock == nil {
		c.Clock = SystemClock()
	}
	if c.Seeds == nil {
		c.Seeds = randomSeed
	}
	if c.Setup == nil {
		c.Setup = seededSetup
	}
	if c.Agent == nil {
		c.Agent = defaultAgent{pick: c.Pick}
	}
	return c, nil
}

type defaultAgent struct {
	pick func(n int) int
}

func (a defaultAgent) Decide(_ context.Context, view play.SeatView) (play.Action, error) {
	return disguisedDefault(view.Decision.Value, a.pick), nil
}

func disguisedDefault(decision play.Decision, pick func(n int) int) play.Action {
	if _, afterCall := decision.Context.(play.TurnAfterCall); !afterCall || pick == nil {
		return decision.Default
	}

	var discards []play.Action
	for _, action := range decision.Legal {
		if action.Kind() == play.ActionDiscard {
			discards = append(discards, action)
		}
	}
	if len(discards) == 0 {
		return decision.Default
	}
	return discards[pick(len(discards))]
}

func randomSeed() engine.Seed {
	var seed engine.Seed
	_, _ = rand.Read(seed[:])
	return seed
}

func seededSetup(seed engine.Seed) engine.Setup {
	return engine.Setup{Walls: play.Seeded{Seed: seed}}
}

// New returns a Manager on cfg. Store writes run under ctx, which must outlive every game: cancel
// it only to cut the shutdown's drain short.
func New(ctx context.Context, cfg Config) (*Manager, error) {
	cfg, err := cfg.validated()
	if err != nil {
		return nil, err
	}
	return newManager(ctx, cfg), nil
}
