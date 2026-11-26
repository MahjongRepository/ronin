package session

import (
	"cmp"
	"context"
	"log/slog"
	"slices"
	"strings"
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

type Manager struct {
	cfg      Config
	storeCtx context.Context
	log      *slog.Logger
	wg       sync.WaitGroup
	inFlight sync.WaitGroup
	stats    counters
	delays   lagWindow

	mu        sync.Mutex
	closed    bool
	games     map[string]*listing
	tickets   map[string]*listing
	withdrawn map[string]time.Time
	conns     map[string]*connEntry
	observed  map[string]*observerEntry
}

type listing struct {
	game    *game
	players []PlayerSpec
	claims  map[string]*seatClaim
	started play.Option[StartedGame]
}

type connEntry struct {
	conn      Connection
	bound     *participant
	authTimer func() bool
}

type counters struct {
	reconnects           atomic.Int64
	takeovers            atomic.Int64
	resyncs              atomic.Int64
	turnTimeouts         atomic.Int64
	meldTimeouts         atomic.Int64
	roundAdvanceTimeouts atomic.Int64
	aiReplacements       atomic.Int64
}

// Stats is the session's event totals since the Manager was made, process-wide and never per
// user.
type Stats struct {
	Reconnects           int64
	Takeovers            int64
	Resyncs              int64
	TurnTimeouts         int64
	MeldTimeouts         int64
	RoundAdvanceTimeouts int64
	AIReplacements       int64
}

// GameCounts is how many games the registry holds: pending ones, waiting for their players, and
// playing ones.
type GameCounts struct {
	Pending int
	Playing int
}

// StartedGame is a game playing as the lobby lists it: its id, its start, its game type and every
// seat's name East to North, from the first dealer, AI players included.
type StartedGame struct {
	GameID    string
	StartedAt time.Time
	GameType  string
	Names     [tile.SeatCount]string
}

// Playing is the game a user plays, the game ticket of their participant in it and the seat
// version a client must name to take that seat over.
type Playing struct {
	GameID      string
	Ticket      string
	SeatVersion int
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
		observed:  map[string]*observerEntry{},
	}
}

// Stats returns the session's event totals.
func (m *Manager) Stats() Stats {
	return Stats{
		Reconnects:           m.stats.reconnects.Load(),
		Takeovers:            m.stats.takeovers.Load(),
		Resyncs:              m.stats.resyncs.Load(),
		TurnTimeouts:         m.stats.turnTimeouts.Load(),
		MeldTimeouts:         m.stats.meldTimeouts.Load(),
		RoundAdvanceTimeouts: m.stats.roundAdvanceTimeouts.Load(),
		AIReplacements:       m.stats.aiReplacements.Load(),
	}
}

// QueueDelayMax returns, in milliseconds, the longest a routed message waited for its game to take
// it in the last minute, and false when no message was routed to a game in that time.
func (m *Manager) QueueDelayMax() (float64, bool) {
	return m.delays.worstMillis(m.cfg.Clock.Now())
}

// Capacity returns how many pending and playing games the registry holds at most.
func (m *Manager) Capacity() int {
	return m.cfg.Capacity
}

// GameCounts returns how many pending and playing games the registry holds; a game leaves it the
// moment its end is claimed or Shutdown begins.
func (m *Manager) GameCounts() GameCounts {
	m.mu.Lock()
	defer m.mu.Unlock()

	var counts GameCounts
	for _, l := range m.games {
		if l.started.OK {
			counts.Playing++
		} else {
			counts.Pending++
		}
	}

	return counts
}

// PlayingGames returns every game playing, pending ones left out, oldest start first; a game leaves
// the list the moment its end is claimed or Shutdown begins.
func (m *Manager) PlayingGames() []StartedGame {
	m.mu.Lock()
	defer m.mu.Unlock()

	var games []StartedGame
	for _, l := range m.games {
		if l.started.OK {
			games = append(games, l.started.Value)
		}
	}

	slices.SortFunc(games, func(a, b StartedGame) int {
		return cmp.Or(a.StartedAt.Compare(b.StartedAt), strings.Compare(a.GameID, b.GameID))
	})

	return games
}

func (m *Manager) PlayingGame(userID string) (Playing, bool) {
	m.mu.Lock()
	defer m.mu.Unlock()

	return m.playingLocked(userID)
}

func (m *Manager) playingLocked(userID string) (Playing, bool) {
	for id, l := range m.games {
		for _, spec := range l.players {
			if spec.UserID == userID {
				return Playing{GameID: id, Ticket: spec.Ticket, SeatVersion: l.claims[spec.Ticket].version}, true
			}
		}
	}

	return Playing{}, false
}

func (m *Manager) CreatePendingGame(gameID string, players []PlayerSpec, seating Seating) error {
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

	if expires, withdrawn := m.withdrawn[gameID]; withdrawn && expires.After(m.cfg.Clock.Now()) {
		return ErrGameWithdrawn
	}

	g := newGame(m, gameID, players, seating)
	l := &listing{game: g, players: players, claims: newSeatClaims(players)}
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

func (m *Manager) WithdrawGame(gameID string) bool {
	for {
		g, found := m.listedOrWithdrawn(gameID)
		if !found {
			return true
		}

		withdrawn, answered := ask(g, g.withdraw)
		if answered {
			return withdrawn
		}
	}
}

func (m *Manager) listedOrWithdrawn(gameID string) (*game, bool) {
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

func (m *Manager) Join(conn Connection, ticket string, claim play.Option[messaging.Claim]) {
	g, registered := m.pathGame(conn)
	if !registered {
		return
	}

	posted := g != nil && g.postAndWait(func() {
		g.serve(conn, "join failed", func() error { return g.join(conn, ticket, claim) })
	})
	if !posted {
		sendSessionError(m.log, conn, messaging.SessionJoinGameNotFound, "Game not found")
	}
}

func (m *Manager) pathGame(conn Connection) (*game, bool) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.registeredLocked(conn) == nil {
		return nil, false
	}

	if l := m.games[conn.GameID()]; l != nil {
		return l.game, true
	}

	return nil, true
}

func (m *Manager) reconnecting(conn Connection, ticket string) (*game, play.Option[sessionRefusal], bool) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.registeredLocked(conn) == nil {
		return nil, play.Option[sessionRefusal]{}, false
	}

	switch l := m.tickets[ticket]; {
	case l == nil:
		return nil, play.Some(sessionRefusal{code: messaging.SessionReconnectNoSession, message: noLiveGame}), true
	case l.game.id != conn.GameID():
		return nil, play.Some(sessionRefusal{
			code: messaging.SessionReconnectGameMismatch, message: "Session token is not valid for this game",
		}), true
	default:
		return l.game, play.Option[sessionRefusal]{}, true
	}
}

type seatBinding struct {
	registered  bool
	participant *participant
	replaced    Connection
	refused     play.Option[sessionRefusal]
	fenced      bool
}

func (m *Manager) bindJoining(g *game, conn Connection, ticket string, claim play.Option[messaging.Claim]) seatBinding {
	m.mu.Lock()
	defer m.mu.Unlock()

	entry := m.registeredLocked(conn)
	if entry == nil {
		return seatBinding{}
	}

	p, refused := m.joiningLocked(g, entry, ticket)
	if refused.OK {
		return seatBinding{registered: true, refused: refused}
	}

	return m.claimLocked(p, entry, claim)
}

func (m *Manager) claimLocked(p *participant, entry *connEntry, claim play.Option[messaging.Claim]) seatBinding {
	if !m.tickets[p.spec.Ticket].claims[p.spec.Ticket].take(claim) {
		m.evictLocked(entry.conn)
		return seatBinding{registered: true, participant: p, fenced: true}
	}

	return seatBinding{registered: true, participant: p, replaced: m.bindLocked(p, entry)}
}

func (m *Manager) joiningLocked(g *game, entry *connEntry, ticket string) (*participant, play.Option[sessionRefusal]) {
	switch l := m.tickets[ticket]; {
	case entry.bound != nil:
		return nil, play.Some(sessionRefusal{code: messaging.SessionAlreadyInGame, message: "Connection already in a game"})
	case l == nil:
		return nil, play.Some(sessionRefusal{code: messaging.SessionJoinGameNoSession, message: "No session for this ticket"})
	case l.game != g:
		return nil, play.Some(sessionRefusal{
			code: messaging.SessionReconnectGameMismatch, message: "Session token is not valid for this game",
		})
	}

	return g.byTicket(ticket), play.Option[sessionRefusal]{}
}

func (m *Manager) bindReconnecting(g *game, conn Connection, ticket string, claim play.Option[messaging.Claim]) seatBinding {
	m.mu.Lock()
	defer m.mu.Unlock()

	entry := m.registeredLocked(conn)
	switch {
	case entry == nil:
		return seatBinding{}
	case entry.bound != nil:
		return seatBinding{registered: true, refused: play.Some(sessionRefusal{
			code: messaging.SessionReconnectAlreadyActive, message: "Connection already in a game",
		})}
	}

	return m.claimLocked(g.byTicket(ticket), entry, claim)
}

func (m *Manager) bindLocked(p *participant, entry *connEntry) Connection {
	replaced := p.conn
	if replaced != nil {
		m.evictLocked(replaced)
	}

	p.conn = entry.conn
	entry.bound = p
	entry.authTimer()
	return replaced
}

func (m *Manager) Act(conn Connection, message messaging.GameActionMessage) {
	g := m.boundGame(conn)
	if g == nil {
		return
	}

	g.postRouted(func() {
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

func (m *Manager) evict(conn Connection) {
	m.mu.Lock()
	defer m.mu.Unlock()

	m.evictLocked(conn)
}

func (m *Manager) markWithdrawn(gameID string) {
	m.mu.Lock()
	defer m.mu.Unlock()

	m.withdrawn[gameID] = m.cfg.Clock.Now().Add(withdrawnTTL)
}

func (m *Manager) markPlaying(g *game, started StartedGame) {
	m.mu.Lock()
	defer m.mu.Unlock()

	m.sweepObservedLocked(m.cfg.Clock.Now())
	if l := m.games[g.id]; l != nil && l.game == g {
		l.started = play.Some(started)
		m.observed[g.id] = &observerEntry{timeline: g.observed}
	}
}

func (m *Manager) release(g *game, conns []Connection) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if l := m.games[g.id]; l != nil && l.game == g {
		delete(m.games, g.id)
	}

	for _, p := range g.participants {
		if l := m.tickets[p.spec.Ticket]; l != nil && l.game == g {
			delete(m.tickets, p.spec.Ticket)
		}
	}

	for _, conn := range conns {
		m.evictLocked(conn)
	}

	m.sweepObservedLocked(m.cfg.Clock.Now())
	if entry := m.observed[g.id]; entry != nil && entry.timeline == g.observed {
		entry.expiresAt = play.Some(g.end.endedAt.Add(m.cfg.ObserveDelay + observedRetention))
	}
}

func (m *Manager) binding(conn Connection) (bound *participant, registered bool) {
	m.mu.Lock()
	defer m.mu.Unlock()

	entry := m.registeredLocked(conn)
	if entry == nil {
		return nil, false
	}

	return entry.bound, true
}

func (m *Manager) boundGame(conn Connection) *game {
	bound, registered := m.binding(conn)
	switch {
	case !registered:
		return nil
	case bound == nil:
		sendSessionError(m.log, conn, messaging.SessionNotInGame, "You must join a game first")
		return nil
	}

	return bound.game
}

func (m *Manager) Disconnect(conn Connection) {
	p := m.evictBound(conn)
	if p == nil {
		return
	}

	p.game.post(func() {
		p.game.serve(conn, "disconnect failed", func() error { return p.game.disconnected(p, conn) })
	})
}

func (m *Manager) Settle() {
	m.inFlight.Wait()
}

func (m *Manager) Shutdown(ctx context.Context) error {
	for _, g := range m.close() {
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

func (m *Manager) close() []*game {
	m.mu.Lock()
	defer m.mu.Unlock()

	m.closed = true
	for _, entry := range m.conns {
		entry.authTimer()
	}

	games := make([]*game, 0, len(m.games))
	for _, l := range m.games {
		games = append(games, l.game)
	}

	clear(m.conns)
	clear(m.games)
	clear(m.tickets)
	return games
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
	log.Warn(logSessionErrorSent, "error_code", string(code), "error_message", message)
	err := send(conn, messaging.SessionError(code, message, play.Option[int]{}))
	if err != nil {
		log.Error("encode session error", "error", err)
	}
}
