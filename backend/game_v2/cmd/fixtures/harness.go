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
	"strconv"
	"sync"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/auth"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/server"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	timeGrain           = 250 * time.Millisecond
	unseenDropCode      = 1006
	ticketPlaceholder   = "<game ticket>"
	ticketSecret        = "seat-scenarios-ticket-secret"
	ticketLifetime      = time.Hour
	startConfirmTimeout = 10 * time.Second
	kanClosed           = "closed"
	kanAdded            = "added"
	sessionErrorType    = "session_error"
	gameJoinedType      = "game_joined"
	gameReconnectedType = "game_reconnected"
	seatControlType     = "seat_control"
	labelReopened       = "reopened"
	labelDropped        = "dropped"
	labelKanChosen      = "kan chosen"
	labelPassed         = "passed"
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
		Replays:  store.NewReplays(filepath.Join(dir, "replays")),
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
	g.runAt(0, func() error { return g.manager.CreatePendingGame(setup.gameID, specs) })
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

type clientSocket struct {
	client *seatClient
	id     string

	mu     sync.Mutex
	closed bool
}

// ID returns the socket's own id.
func (s *clientSocket) ID() string {
	return s.id
}

// GameID returns the game id of the socket's URL.
func (s *clientSocket) GameID() string {
	return s.client.game.gameID
}

// Send hands one message the server sent to the client, decoded, unless the socket is closed.
func (s *clientSocket) Send(data []byte) {
	if s.isClosed() {
		return
	}
	m, err := wire.Decode(data)
	if err != nil {
		s.client.game.fail(fmt.Errorf("the server sent %s an undecodable message: %w", s.client.name, err))
		return
	}
	s.client.game.observeDeal(m)
	s.client.receive(s, m)
}

// Close ends the socket as the endpoint does: the client sees the close, and the server's
// disconnect runs once the step that closed it settled.
func (s *clientSocket) Close(code session.CloseCode, reason string) {
	if !s.markClosed() {
		return
	}
	s.client.lose(s, int(code), reason)
	s.client.game.queueDisconnect(s)
}

func (s *clientSocket) markClosed() (newlyClosed bool) {
	s.mu.Lock()
	defer s.mu.Unlock()

	newlyClosed = !s.closed
	s.closed = true
	return newlyClosed
}

func (s *clientSocket) isClosed() bool {
	s.mu.Lock()
	defer s.mu.Unlock()

	return s.closed
}

type seatClient struct {
	game   *seatedGame
	name   string
	ticket string

	mu         sync.Mutex
	seat       play.Option[tile.Seat]
	events     []transcriptEvent
	socket     *clientSocket
	opened     int
	waitID     play.Option[int]
	refusals   []wire.Map
	expected   []messaging.SessionErrorCode
	stagingErr error
}

func (c *seatClient) recorded() (play.Option[tile.Seat], []transcriptEvent) {
	c.mu.Lock()
	defer c.mu.Unlock()

	return c.seat, slices.Clone(c.events)
}

func (c *seatClient) problem() error {
	c.mu.Lock()
	defer c.mu.Unlock()

	switch {
	case c.stagingErr != nil:
		return c.stagingErr
	case len(c.refusals) > 0:
		return fmt.Errorf("%s was refused: %v", c.name, c.refusals[0])
	case len(c.expected) > 0:
		return fmt.Errorf("%s was never refused with %s", c.name, c.expected[0])
	}
	return nil
}

func (c *seatClient) record(kind string, fields wire.StrMap, label string) {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.recordLocked(kind, fields, label)
}

func (c *seatClient) recordLocked(kind string, fields wire.StrMap, label string) {
	c.events = append(c.events, transcriptEvent{at: c.game.clock.elapsed(), kind: kind, fields: fields, label: label})
}

func (c *seatClient) labelLast(label string) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if label != "" && len(c.events) > 0 {
		c.events[len(c.events)-1].label = label
	}
}

func (c *seatClient) receive(socket *clientSocket, payload wire.Map) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if socket != c.socket {
		return
	}
	c.recordLocked(kindReceived, wire.StrMap{{Key: "payload", Value: payload}}, "")
	if isRefusal(payload) {
		c.takeRefusal(payload)
	}
	if id, ok := payload.Int(wire.KeyWaitID); ok {
		c.waitID = play.Some(id)
	}
	if isEvent(payload, wire.EventGameStarted) || isSession(payload, gameReconnectedType) {
		if n, ok := payload.Int(wire.KeySeat); ok {
			seat, valid := tile.NewSeat(n)
			c.seat = play.Option[tile.Seat]{Value: seat, OK: valid}
		}
	}
	c.checkStaged(payload)
}

func (c *seatClient) checkStaged(payload wire.Map) {
	switch {
	case isEvent(payload, wire.EventRoundStarted):
		roundNumber, numbered := payload.Int(wire.KeyRoundNumber)
		dealer, named := payload.Int(wire.KeyDealer)
		staged, index, isStaged := c.game.stagedRound(uint32(max(0, roundNumber)))
		if numbered && named && isStaged && index > 0 && staged.dealer.Index() != dealer {
			c.stagingErr = fmt.Errorf("later round %d was staged for dealer %d, not %d",
				index-1, staged.dealer.Index(), dealer)
		}
	case isEvent(payload, wire.EventDraw):
		packed, ok := payload.Int(wire.KeyPackedMove)
		staged, _, isStaged := c.game.stagedRound(c.game.latestRound())
		if !ok || !isStaged {
			return
		}
		seat, drawn, err := wire.UnpackDraw(packed)
		index, isStagedDraw := staged.drawOf(drawn)
		if err == nil && isStagedDraw && staged.draws[index].seat != seat {
			c.stagingErr = fmt.Errorf("seat %d drew staged draw %d (staged for seat %d)",
				seat.Index(), index, staged.draws[index].seat.Index())
		}
	}
}

func (c *seatClient) takeRefusal(payload wire.Map) {
	code, _ := payload.Get(wire.KeySessionErrorCode)
	if len(c.expected) > 0 && code == wire.Str(c.expected[0]) {
		c.expected = c.expected[1:]
		return
	}
	c.refusals = append(c.refusals, payload)
}

func (c *seatClient) lose(socket *clientSocket, code int, reason string) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if socket != c.socket {
		return
	}
	c.socket = nil
	c.recordLocked(kindClosed, wire.StrMap{
		{Key: "code", Value: wire.Int(code)}, {Key: "reason", Value: wire.Str(reason)},
	}, "")
}

func (c *seatClient) newSocket(prefix string) *clientSocket {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.opened++
	return &clientSocket{client: c, id: c.name + prefix + strconv.Itoa(c.opened)}
}

func (c *seatClient) join() {
	c.game.runAt(0, func() error { return c.open(messaging.ClientJoinGame, "") })
}

func (c *seatClient) reconnect(at time.Duration) {
	c.game.runAt(at, func() error { return c.open(messaging.ClientReconnect, labelReopened) })
}

func (c *seatClient) identity(typ messaging.ClientMessageType) wire.Map {
	return wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(typ)},
		{Key: wire.KeyGameTicket, Value: wire.Str(c.ticket)},
	}
}

func (c *seatClient) open(typ messaging.ClientMessageType, label string) error {
	socket := c.newSocket("-")
	err := c.bind(socket, label)
	if err != nil {
		return err
	}
	c.game.manager.Connect(socket)

	message, err := asWire(c.identity(typ))
	if err != nil {
		return err
	}
	shown := slices.Clone(message)
	for i, f := range shown {
		if f.Key == wire.KeyGameTicket {
			shown[i].Value = wire.Str(ticketPlaceholder)
		}
	}
	c.record(kindSent, wire.StrMap{{Key: "message", Value: shown}}, "")
	c.game.router.Route(socket, message)
	return nil
}

func (c *seatClient) bind(socket *clientSocket, label string) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.socket != nil {
		return fmt.Errorf("%s opened a socket while one is open", c.name)
	}
	c.socket = socket
	c.recordLocked(kindOpened, nil, label)
	return nil
}

func (c *seatClient) currentWaitID() play.Option[int] {
	c.mu.Lock()
	defer c.mu.Unlock()

	return c.waitID
}

func (c *seatClient) expectRefusal(code messaging.SessionErrorCode) {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.expected = append(c.expected, code)
}

func asWire(m wire.Map) (wire.Map, error) {
	data, err := wire.Encode(m)
	if err != nil {
		return nil, err
	}
	return wire.Decode(data)
}

func (c *seatClient) currentSocket() (*clientSocket, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.socket == nil {
		return nil, fmt.Errorf("%s acted without an open socket", c.name)
	}
	return c.socket, nil
}

func (c *seatClient) dropUnseen(at time.Duration) {
	c.drop(at, false)
}

func (c *seatClient) dropSeen(at time.Duration) {
	c.drop(at, true)
}

func (c *seatClient) drop(at time.Duration, serverSees bool) {
	c.game.runAt(at, func() error {
		socket, err := c.currentSocket()
		if err != nil {
			return err
		}
		c.lose(socket, unseenDropCode, "")
		c.labelLast(labelDropped)
		if serverSees {
			c.game.manager.Disconnect(socket)
		}
		return nil
	})
}

func (c *seatClient) replacedByAnotherTab(at time.Duration, label string) {
	c.game.runAt(at, func() error {
		rival := c.newSocket("-rival-")
		c.game.manager.Connect(rival)
		message, err := asWire(c.identity(messaging.ClientReconnect))
		if err != nil {
			return err
		}
		c.game.router.Route(rival, message)
		c.game.settle()

		if _, closedErr := c.currentSocket(); closedErr == nil {
			return fmt.Errorf("%s: another tab reconnected, and this one's socket stayed open", c.name)
		}
		c.labelLast(label)
		return nil
	})
}

func (c *seatClient) act(at time.Duration, label string, action messaging.GameAction, fields ...wire.Field) {
	c.game.runAt(at, func() error {
		socket, err := c.currentSocket()
		if err != nil {
			return err
		}
		waitID := c.currentWaitID()
		if !waitID.OK {
			return fmt.Errorf("%s: game action %d before any wait was opened", c.name, action)
		}

		m := wire.Map{
			{Key: wire.KeyEventType, Value: wire.Int(messaging.ClientGameAction)},
			{Key: wire.KeyAction, Value: wire.Int(action)},
		}
		m = append(m, fields...)
		message, err := asWire(append(m, wire.Field{Key: wire.KeyWaitID, Value: wire.Int(waitID.Value)}))
		if err != nil {
			return err
		}
		c.record(kindSent, wire.StrMap{{Key: "message", Value: message}}, label)
		c.game.router.Route(socket, message)
		return nil
	})
}

func tileField(id tile.TileID) wire.Field {
	return wire.Field{Key: wire.KeyTileID, Value: wire.Int(id.Index())}
}

func heldField(first, second tile.TileID) wire.Field {
	return wire.Field{Key: wire.KeySequenceTiles, Value: wire.Array{wire.Int(first.Index()), wire.Int(second.Index())}}
}

func (c *seatClient) discard(at time.Duration, label string, id tile.TileID) {
	c.act(at, label, messaging.GameActionDiscard, tileField(id))
}

func (c *seatClient) riichi(at time.Duration, label string, id tile.TileID) {
	c.act(at, label, messaging.GameActionRiichi, tileField(id))
}

func (c *seatClient) tsumo(at time.Duration, label string) {
	c.act(at, label, messaging.GameActionTsumo)
}

func (c *seatClient) ron(at time.Duration, label string) {
	c.act(at, label, messaging.GameActionRon)
}

func (c *seatClient) pon(at time.Duration, label string, called, first, second tile.TileID) {
	c.act(at, label, messaging.GameActionPon, tileField(called), heldField(first, second))
}

func (c *seatClient) chi(at time.Duration, label string, called, first, second tile.TileID) {
	c.act(at, label, messaging.GameActionChi, tileField(called), heldField(first, second))
}

func (c *seatClient) kan(at time.Duration, id tile.TileID, kind string) {
	c.act(at, labelKanChosen, messaging.GameActionKan, tileField(id), wire.Field{Key: wire.KeyActionKanType, Value: wire.Str(kind)})
}

func (c *seatClient) kyuushu(at time.Duration, label string) {
	c.act(at, label, messaging.GameActionKyuushu)
}

func (c *seatClient) pass(at time.Duration) {
	c.act(at, labelPassed, messaging.GameActionPass)
}

func (c *seatClient) confirmRound(at time.Duration, label string) {
	c.act(at, label, messaging.GameActionConfirmRound)
}

func (c *seatClient) resync(at time.Duration, label string, refusedWith messaging.SessionErrorCode) {
	c.game.runAt(at, func() error {
		socket, err := c.currentSocket()
		if err != nil {
			return err
		}
		message, err := asWire(wire.Map{{Key: wire.KeyEventType, Value: wire.Int(messaging.ClientResync)}})
		if err != nil {
			return err
		}
		c.record(kindSent, wire.StrMap{{Key: "message", Value: message}}, label)
		if refusedWith != "" {
			c.expectRefusal(refusedWith)
		}
		c.game.router.Route(socket, message)
		return nil
	})
}

func (c *seatClient) labelEvent(name string, event wire.EventType) {
	c.label(name, func(p wire.Map) bool { return isEvent(p, event) }, "event "+strconv.Itoa(int(event)))
}

func (c *seatClient) labelSession(name, sessionType string) {
	c.label(name, func(p wire.Map) bool { return isSession(p, sessionType) }, sessionType)
}

func (c *seatClient) label(name string, matches func(wire.Map) bool, kind string) {
	if c.game.failure() != nil {
		return
	}
	c.mu.Lock()
	defer c.mu.Unlock()

	for i, e := range slices.Backward(c.events) {
		payload, _ := e.fields.Get("payload")
		m, isMap := payload.(wire.Map)
		if e.kind != kindReceived || !isMap || !matches(m) {
			continue
		}
		if e.label != "" {
			c.game.fail(fmt.Errorf("%s: the last %s is already labelled %s", c.name, kind, e.label))
			return
		}
		c.events[i].label = name
		return
	}
	c.game.fail(fmt.Errorf("%s received no %s to label %s", c.name, kind, name))
}

func isEvent(m wire.Map, event wire.EventType) bool {
	n, ok := m.Int(wire.KeyEventType)
	_, isSessionMessage := m.Get(wire.KeySessionType)
	return ok && n == int(event) && !isSessionMessage
}

func isSession(m wire.Map, sessionType string) bool {
	v, _ := m.Get(wire.KeySessionType)
	return v == wire.Str(sessionType)
}

func isRefusal(m wire.Map) bool {
	n, ok := m.Int(wire.KeyEventType)
	return ok && n == int(wire.EventError) || isSession(m, sessionErrorType)
}
