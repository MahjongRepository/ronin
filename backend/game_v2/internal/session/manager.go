package session

import (
	"context"
	"log/slog"
	"sync"
	"sync/atomic"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	authTimeout  = 10 * time.Second
	withdrawnTTL = 24 * time.Hour
)

// Manager is the registry of live games and connections. Its methods are safe for concurrent use;
// each connection's own calls (Connect, Join, Act, Disconnect) come in the order its socket read
// them.
type Manager struct {
	cfg      Config
	storeCtx context.Context
	log      *slog.Logger
	wg       sync.WaitGroup
	stats    counters

	mu        sync.Mutex
	closed    bool
	games     map[string]*listing
	tickets   map[string]*listing
	withdrawn map[string]time.Time
	conns     map[string]*connEntry
}

type listing struct {
	game    *game
	players []PlayerSpec
	playing bool
}

type connEntry struct {
	conn      Connection
	bound     *participant
	authTimer func() bool
}

type counters struct {
	reconnects     atomic.Int64
	takeovers      atomic.Int64
	resyncs        atomic.Int64
	turnTimeouts   atomic.Int64
	meldTimeouts   atomic.Int64
	pauseTimeouts  atomic.Int64
	aiReplacements atomic.Int64
}

// Stats is the session's event totals since the Manager was made, process-wide and never per
// user.
type Stats struct {
	Reconnects          int64
	Takeovers           int64
	Resyncs             int64
	TurnTimeouts        int64
	MeldTimeouts        int64
	RoundAdvanceTimeout int64
	AIReplacements      int64
}

// GameCounts is how many games the registry holds: pending ones, waiting for their players, and
// playing ones.
type GameCounts struct {
	Pending int
	Playing int
}

// Playing is the game a user plays and the game ticket of their participant in it.
type Playing struct {
	GameID string
	Ticket string
}

func newManager(ctx context.Context, cfg Config) *Manager {
	return &Manager{
		cfg:       cfg,
		storeCtx:  ctx,
		log:       cfg.Logger,
		games:     map[string]*listing{},
		tickets:   map[string]*listing{},
		withdrawn: map[string]time.Time{},
		conns:     map[string]*connEntry{},
	}
}

// Stats returns the session's event totals.
func (m *Manager) Stats() Stats {
	return Stats{
		Reconnects:          m.stats.reconnects.Load(),
		Takeovers:           m.stats.takeovers.Load(),
		Resyncs:             m.stats.resyncs.Load(),
		TurnTimeouts:        m.stats.turnTimeouts.Load(),
		MeldTimeouts:        m.stats.meldTimeouts.Load(),
		RoundAdvanceTimeout: m.stats.pauseTimeouts.Load(),
		AIReplacements:      m.stats.aiReplacements.Load(),
	}
}

// GameCounts returns how many pending and playing games the registry holds; a game leaves it the
// moment its end is claimed.
func (m *Manager) GameCounts() GameCounts {
	m.mu.Lock()
	defer m.mu.Unlock()

	var counts GameCounts
	for _, l := range m.games {
		if l.playing {
			counts.Playing++
		} else {
			counts.Pending++
		}
	}
	return counts
}

// PlayingGame returns the game a user plays and their participant's ticket: a user plays a game
// from its creation, pending included, until its end is claimed, connected or not, so the lobby
// keeps them out of rooms and can hand them back their ticket.
func (m *Manager) PlayingGame(userID string) (Playing, bool) {
	m.mu.Lock()
	defer m.mu.Unlock()

	return m.playingLocked(userID)
}

func (m *Manager) playingLocked(userID string) (Playing, bool) {
	for id, l := range m.games {
		for _, spec := range l.players {
			if spec.UserID == userID {
				return Playing{GameID: id, Ticket: spec.Ticket}, true
			}
		}
	}
	return Playing{}, false
}

// CreatePendingGame registers a pending game waiting for its players' JOIN_GAME, its pending
// timeout armed. In one step it refuses a player already playing (ErrPlayerPlaying), a full
// registry (ErrAtCapacity), a taken id (ErrGameExists), a withdrawn id (ErrGameWithdrawn), no
// player or more than four (ErrPlayerCount), and any game once Shutdown began (ErrShuttingDown).
func (m *Manager) CreatePendingGame(gameID string, players []PlayerSpec) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	switch {
	case m.closed:
		return ErrShuttingDown
	case len(players) == 0 || len(players) > tile.SeatCount:
		return ErrPlayerCount
	case m.anyPlayingLocked(players):
		return ErrPlayerPlaying
	case len(m.games) >= m.cfg.Capacity:
		return ErrAtCapacity
	case m.games[gameID] != nil:
		return ErrGameExists
	}
	if _, withdrawn := m.withdrawn[gameID]; withdrawn {
		return ErrGameWithdrawn
	}

	g := newGame(m, gameID, players)
	l := &listing{game: g, players: players}
	m.games[gameID] = l
	for _, spec := range players {
		m.tickets[spec.Ticket] = l
	}
	m.wg.Go(g.run)
	g.log.Info("pending game created", "expected_count", len(players))
	return nil
}

func (m *Manager) anyPlayingLocked(players []PlayerSpec) bool {
	for _, spec := range players {
		if _, playing := m.playingLocked(spec.UserID); playing {
			return true
		}
	}
	return false
}

// WithdrawGame drops a game its creator gave up on, whether or not its creation has arrived, and
// reports false when it keeps it: a game someone joined, or one already playing. A pending game
// nobody joined is abandoned at once; the id is refused for a ticket's lifetime from then on, so
// a creation that arrives after the withdrawal never registers.
func (m *Manager) WithdrawGame(gameID string) bool {
	for {
		g, found := m.withdrawLocked(gameID)
		if !found {
			return true
		}

		withdrawn, answered := ask(g, g.withdraw)
		if answered {
			return withdrawn
		}
	}
}

func (m *Manager) withdrawLocked(gameID string) (*game, bool) {
	m.mu.Lock()
	defer m.mu.Unlock()

	now := m.cfg.Clock.Now()
	for id, expires := range m.withdrawn {
		if !expires.After(now) {
			delete(m.withdrawn, id)
		}
	}

	l := m.games[gameID]
	if l == nil {
		m.withdrawn[gameID] = now.Add(withdrawnTTL)
		return nil, false
	}
	return l.game, true
}

// Connect registers a new connection, which must authenticate with JOIN_GAME or RECONNECT within
// the auth timeout or be closed.
func (m *Manager) Connect(conn Connection) {
	m.mu.Lock()
	defer m.mu.Unlock()

	entry := &connEntry{conn: conn}
	entry.authTimer = m.cfg.Clock.AfterFunc(authTimeout, func() { m.closeUnauthenticated(conn) })
	m.conns[conn.ID()] = entry
}

func (m *Manager) closeUnauthenticated(conn Connection) {
	if !m.evictUnbound(conn) {
		return
	}
	m.log.Info(logAuthTimeout, "connection_id", conn.ID())
	conn.Close(CloseAuthTimeout, "auth_timeout")
}

func (m *Manager) evictUnbound(conn Connection) bool {
	m.mu.Lock()
	defer m.mu.Unlock()

	entry := m.registeredLocked(conn)
	if entry == nil || entry.bound != nil {
		return false
	}
	delete(m.conns, conn.ID())
	return true
}

func (m *Manager) registeredLocked(conn Connection) *connEntry {
	entry := m.conns[conn.ID()]
	if entry == nil || entry.conn != conn {
		return nil
	}
	return entry
}

func (m *Manager) evictLocked(conn Connection) {
	entry := m.registeredLocked(conn)
	if entry == nil {
		return
	}
	delete(m.conns, conn.ID())
	entry.authTimer()
}

// Join binds a connection to its participant in the connection's pending game, replacing the
// connection the participant still has; the last expected join starts the game. A JOIN_GAME on a
// connection the session already evicted is dropped unanswered.
func (m *Manager) Join(conn Connection, ticket string) {
	m.mu.Lock()
	registered := m.registeredLocked(conn) != nil
	l := m.games[conn.GameID()]
	m.mu.Unlock()

	if !registered {
		return
	}
	if l == nil || !l.game.post(func() { l.game.serve(conn, "join failed", func() error { return l.game.join(conn, ticket) }) }) {
		sendSessionError(m.log, conn, messaging.SessionJoinGameNotFound, "Game not found")
	}
}

// Act runs a game action of the participant a connection is bound to: a round confirmation goes
// to the session's pause, any other action to the game. A connection bound to no participant is
// answered not_in_game, and one the session evicted nothing.
func (m *Manager) Act(conn Connection, message messaging.GameActionMessage) {
	g := m.boundGame(conn)
	if g == nil {
		return
	}
	g.post(func() {
		g.serve(conn, "game action failed", func() error { return g.gameAction(conn, message) })
	})
}

func (m *Manager) evictBound(conn Connection) *participant {
	m.mu.Lock()
	defer m.mu.Unlock()

	entry := m.registeredLocked(conn)
	if entry == nil {
		return nil
	}
	m.evictLocked(conn)
	return entry.bound
}

func (m *Manager) boundGame(conn Connection) *game {
	m.mu.Lock()
	entry := m.registeredLocked(conn)
	var bound *participant
	if entry != nil {
		bound = entry.bound
	}
	m.mu.Unlock()

	switch {
	case entry == nil:
		return nil
	case bound == nil:
		sendSessionError(m.log, conn, messaging.SessionNotInGame, "You must join a game first")
		return nil
	}
	return bound.game
}

// Disconnect evicts a closed connection and takes the participant bound to it out of its game: a
// pending game waits for its new JOIN_GAME, and in a playing game an AI player takes the seat, or,
// when nobody connected remains, the game is abandoned. The late disconnect of a connection the
// session already evicted or replaced touches no one.
func (m *Manager) Disconnect(conn Connection) {
	p := m.evictBound(conn)
	if p == nil {
		return
	}
	p.game.post(func() {
		p.game.serve(conn, "disconnect failed", func() error { return p.game.disconnected(p, conn) })
	})
}

// Shutdown stops the session once the server stopped serving: it refuses new games, cancels the
// auth timeouts, lets every game still registered vanish with no record, since a graceful stop ends
// games only through each socket's disconnect, and waits for every game's goroutine, finalizers
// and store writes included, until ctx is done.
func (m *Manager) Shutdown(ctx context.Context) error {
	m.mu.Lock()
	m.closed = true
	for _, entry := range m.conns {
		entry.authTimer()
	}
	games := make([]*game, 0, len(m.games))
	for _, l := range m.games {
		games = append(games, l.game)
	}
	m.mu.Unlock()

	for _, g := range games {
		g.post(g.vanish)
	}

	drained := make(chan struct{})
	go func() {
		m.wg.Wait()
		close(drained)
	}()
	select {
	case <-drained:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func send(conn Connection, m wire.Map) error {
	data, err := wire.Encode(m)
	if err != nil {
		return err
	}
	conn.Send(data)
	return nil
}

func sendSessionError(log *slog.Logger, conn Connection, code messaging.SessionErrorCode, message string) {
	log.Warn("session error sent to client", "error_code", string(code), "error_message", message)
	err := send(conn, messaging.SessionError(code, message, play.Option[int]{}))
	if err != nil {
		log.Error("encode session error", "error", err)
	}
}
