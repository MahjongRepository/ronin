package main

import (
	"fmt"
	"slices"
	"strconv"
	"sync"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	unseenDropCode      = 1006
	ticketPlaceholder   = "<game ticket>"
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
