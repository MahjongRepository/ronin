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

const (
	CloseGameEnded     CloseCode = 1000
	CloseInvalidAction CloseCode = 1008
	CloseInternalError CloseCode = 1011
	CloseAuthTimeout   CloseCode = 4001
	CloseReplaced      CloseCode = 4002
)

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

type Seating int

const (
	SeatingShuffled Seating = iota
	SeatingFixed
)

type Agent interface {
	Decide(ctx context.Context, view play.SeatView) (play.Action, error)
}

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

var (
	ErrGameExists    = errors.New("a game with this id already exists")
	ErrGameWithdrawn = errors.New("the game was withdrawn")
	ErrPlayerPlaying = errors.New("a player is already in a game")
	ErrAtCapacity    = errors.New("the server is at capacity")
	ErrShuttingDown  = errors.New("the server is shutting down")
	ErrPlayerCount   = errors.New("a game seats one to four players")
)

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
