package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"maps"
	"os"
	"path/filepath"
	"slices"
	"sync"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/auth"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replayfile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/server"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	timeGrain           = 250 * time.Millisecond
	ticketSecret        = "seat-scenarios-ticket-secret"
	ticketLifetime      = time.Hour
	startConfirmTimeout = 10 * time.Second
)

func scenarioTiming() session.Timing {
	timing := session.DefaultTiming()
	timing.BaseTurn = 5 * time.Second
	timing.RoundAdvance = 10 * time.Second
	timing.GameStartConfirm = startConfirmTimeout
	timing.AITurnDelay = 0
	return timing
}

func secs(seconds float64) time.Duration {
	return time.Duration(seconds * float64(time.Second))
}

type seatedGame struct {
	gameID     string
	rounds     []stagedWall
	firstRound uint32
	clock      *virtualClock
	manager    *session.Manager
	router     *server.Router
	db         *store.DB
	dir        string
	clients    map[string]*seatClient

	mu          sync.Mutex
	err         error
	disconnects []*clientSocket
	dealt       fillerDealers
	latest      uint32
}

type gameSetup struct {
	gameID  string
	players []string
	rounds  []stagedWall
	start   play.Option[play.StartPosition]
	dealers fillerDealers
}

func openSeatedGame(ctx context.Context, logger *slog.Logger, setup gameSetup) (*seatedGame, error) {
	dealer := tile.Seats()[0]
	if setup.start.OK {
		dealer = setup.start.Value.Dealer
	}

	if setup.rounds[0].dealer != dealer {
		return nil, fmt.Errorf("%s: a staged game's first round is dealt from seat %d, not %d",
			setup.gameID, dealer.Index(), setup.rounds[0].dealer.Index())
	}

	engineSetup, err := stagedSetup(stagedSeed(), setup.rounds, setup.start, setup.dealers)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", setup.gameID, err)
	}

	dir, err := os.MkdirTemp("", "seat-scenario-")
	if err != nil {
		return nil, err
	}

	db, err := store.Open(ctx, filepath.Join(dir, "game.db"), logger)
	if err != nil {
		return nil, errors.Join(err, os.RemoveAll(dir))
	}

	g := &seatedGame{
		gameID: setup.gameID, rounds: setup.rounds, firstRound: setup.start.Value.RoundNumber,
		clock: &virtualClock{}, db: db, dir: dir,
		clients: map[string]*seatClient{}, dealt: fillerDealers{},
	}
	g.manager, err = session.New(ctx, session.Config{
		Timing:   scenarioTiming(),
		Capacity: 1,
		DB:       db,
		Replays:  replayfile.New(filepath.Join(dir, "replays")),
		Logger:   logger,
		Clock:    g.clock,
		Seeds:    stagedSeed,
		Setup:    func(engine.Seed) engine.Setup { return engineSetup },
	})
	if err != nil {
		return nil, errors.Join(err, db.Close(), os.RemoveAll(dir))
	}

	g.router = server.NewRouter(g.manager, ticketSecret, logger, g.clock.Now)

	specs := make([]session.PlayerSpec, 0, len(setup.players))
	for _, name := range setup.players {
		ticket := auth.SignTicket(auth.Ticket{
			UserID: "user-" + name, Username: name, RoomID: setup.gameID,
			ExpiresAt: float64(g.clock.Now().Add(ticketLifetime).UnixNano()) / float64(time.Second),
		}, ticketSecret)
		g.clients[name] = &seatClient{game: g, name: name, ticket: ticket}
		specs = append(specs, session.PlayerSpec{Name: name, UserID: "user-" + name, Ticket: ticket})
	}

	g.runAt(0, func() error { return g.manager.CreatePendingGame(setup.gameID, specs, session.SeatingShuffled) })
	return g, nil
}

func (g *seatedGame) close(ctx context.Context) error {
	return errors.Join(g.manager.Shutdown(ctx), g.db.Close(), os.RemoveAll(g.dir))
}

func (g *seatedGame) fail(err error) {
	g.mu.Lock()
	defer g.mu.Unlock()

	if g.err == nil {
		g.err = fmt.Errorf("%s: %w", g.gameID, err)
	}
}

func (g *seatedGame) failure() error {
	g.mu.Lock()
	defer g.mu.Unlock()

	return g.err
}

func (g *seatedGame) observeDeal(payload wire.Map) {
	roundNumber, numbered := payload.Int(wire.KeyRoundNumber)
	dealerIndex, named := payload.Int(wire.KeyDealer)
	dealer, valid := tile.NewSeat(dealerIndex)
	if !isEvent(payload, wire.EventRoundStarted) || !numbered || !named || !valid || roundNumber < 0 {
		return
	}

	g.mu.Lock()
	defer g.mu.Unlock()

	g.dealt[uint32(roundNumber)] = dealer
	g.latest = uint32(roundNumber)
}

func (g *seatedGame) stagedRound(roundNumber uint32) (stagedWall, int, bool) {
	index := int(roundNumber) - int(g.firstRound)
	if index < 0 || index >= len(g.rounds) {
		return stagedWall{}, index, false
	}

	return g.rounds[index], index, true
}

func (g *seatedGame) latestRound() uint32 {
	g.mu.Lock()
	defer g.mu.Unlock()

	return g.latest
}

func (g *seatedGame) dealtDealers() fillerDealers {
	g.mu.Lock()
	defer g.mu.Unlock()

	return maps.Clone(g.dealt)
}

func (g *seatedGame) queueDisconnect(socket *clientSocket) {
	g.mu.Lock()
	defer g.mu.Unlock()

	g.disconnects = append(g.disconnects, socket)
}

func (g *seatedGame) nextDisconnect() (*clientSocket, bool) {
	g.mu.Lock()
	defer g.mu.Unlock()

	if len(g.disconnects) == 0 {
		return nil, false
	}

	socket := g.disconnects[0]
	g.disconnects = g.disconnects[1:]
	return socket, true
}

func (g *seatedGame) settle() {
	for {
		g.manager.Settle()
		socket, ok := g.nextDisconnect()
		if !ok {
			return
		}

		g.manager.Disconnect(socket)
	}
}

func (g *seatedGame) runAt(at time.Duration, step func() error) {
	if g.failure() != nil {
		return
	}

	now := g.clock.elapsed()
	switch {
	case at < now:
		g.fail(fmt.Errorf("a step at %v after the clock reached %v", at, now))
		return
	case at%timeGrain != 0:
		g.fail(fmt.Errorf("a step at %v, not a multiple of %v", at, timeGrain))
		return
	case g.clock.armedAt(at):
		g.fail(fmt.Errorf("a step at %v, the moment a server timer fires", at))
		return
	}

	for {
		fire, due := g.clock.takeDue(at)
		if !due {
			break
		}

		fire()
		g.settle()
	}

	g.clock.advanceTo(at)
	err := step()
	if err != nil {
		g.fail(err)
	}

	g.settle()
	g.requireNoRefusal()
}

func (g *seatedGame) waitUntil(at time.Duration) {
	g.runAt(at, func() error { return nil })
}

func (g *seatedGame) client(name string) *seatClient {
	return g.clients[name]
}

func (g *seatedGame) requireNoRefusal() {
	for _, name := range slices.Sorted(maps.Keys(g.clients)) {
		if err := g.clients[name].problem(); err != nil {
			g.fail(err)
		}
	}
}

func (g *seatedGame) transcripts(scenario string, names ...string) ([]transcript, error) {
	g.requireNoRefusal()
	if err := g.failure(); err != nil {
		return nil, err
	}

	transcripts := make([]transcript, 0, len(names))
	for _, name := range names {
		c := g.clients[name]
		seat, events := c.recorded()
		if !seat.OK {
			return nil, fmt.Errorf("%s: %s never learned its seat", g.gameID, name)
		}

		transcripts = append(transcripts, transcript{
			scenario: scenario, gameID: g.gameID, seat: seat.Value.Index(), events: events,
		})
	}

	return transcripts, nil
}

type env struct {
	logger *slog.Logger
}

const maxDealerPasses = 8

func (e env) play(
	ctx context.Context, s *staging, setup gameSetup, script func(g *seatedGame) ([]transcript, error),
) ([]transcript, error) {
	if s.err != nil {
		return nil, s.err
	}

	setup.dealers = fillerDealers{}
	for range maxDealerPasses {
		g, err := openSeatedGame(ctx, e.logger, setup)
		if err != nil {
			return nil, err
		}

		transcripts, playErr := script(g)
		playErr = errors.Join(playErr, s.err)
		dealt := g.dealtDealers()
		closeErr := g.close(ctx)
		if closeErr != nil {
			return nil, errors.Join(playErr, closeErr)
		}

		if s.err != nil || fillersMatch(setup.rounds, setup.start, setup.dealers, dealt) {
			return transcripts, playErr
		}

		setup.dealers = dealt
	}

	return nil, fmt.Errorf("%s: the seed's later rounds found no dealers in %d passes", setup.gameID, maxDealerPasses)
}

func fillersMatch(
	rounds []stagedWall, start play.Option[play.StartPosition], planned, dealt fillerDealers,
) bool {
	first := firstFillerRound(rounds, start)
	lastStaged := rounds[len(rounds)-1].dealer
	for roundNumber, dealer := range dealt {
		if roundNumber >= first && planned.of(roundNumber, lastStaged) != dealer {
			return false
		}
	}

	return true
}

func alone(gameID string, rounds ...stagedWall) gameSetup {
	return gameSetup{gameID: gameID, players: []string{player}, rounds: rounds}
}

func withRobber(gameID string, rounds ...stagedWall) gameSetup {
	return gameSetup{gameID: gameID, players: []string{player, robber}, rounds: rounds}
}

func (g gameSetup) from(start play.StartPosition) gameSetup {
	g.start = play.Some(start)
	return g
}
