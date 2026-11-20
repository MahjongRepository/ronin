package session

import (
	"fmt"
	"slices"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	gameTypeHanchan = "hanchan"
	aiNamePrefix    = "ai-tsumogiri-"
)

type sessionRefusal struct {
	code    messaging.SessionErrorCode
	message string
}

func (g *game) join(conn Connection, ticket string) error {
	if g.lifecycle == lifecyclePlaying {
		sendSessionError(g.log, conn, messaging.SessionJoinGameAlreadyStarted, "Game already started, use RECONNECT")
		return nil
	}

	b := g.bindJoining(conn, ticket)
	switch {
	case !b.registered:
		return nil
	case b.refused.OK:
		sendSessionError(g.log, conn, b.refused.Value.code, b.refused.Value.message)
		return nil
	}
	g.closeReplaced(b.replaced, conn)
	return g.admit(b.participant, conn)
}

type seatBinding struct {
	registered  bool
	participant *participant
	replaced    Connection
	refused     play.Option[sessionRefusal]
}

func (g *game) bindJoining(conn Connection, ticket string) seatBinding {
	g.m.mu.Lock()
	defer g.m.mu.Unlock()

	entry := g.m.registeredLocked(conn)
	if entry == nil {
		return seatBinding{}
	}
	p, refused := g.joiningLocked(entry, ticket)
	if refused.OK {
		return seatBinding{registered: true, refused: refused}
	}
	return seatBinding{registered: true, participant: p, replaced: g.bindLocked(p, entry)}
}

func (g *game) joiningLocked(entry *connEntry, ticket string) (*participant, play.Option[sessionRefusal]) {
	switch l := g.m.tickets[ticket]; {
	case entry.bound != nil:
		return nil, play.Some(sessionRefusal{messaging.SessionAlreadyInGame, "Connection already in a game"})
	case l == nil:
		return nil, play.Some(sessionRefusal{messaging.SessionJoinGameNoSession, "No session for this ticket"})
	case l.game != g:
		return nil, play.Some(sessionRefusal{
			messaging.SessionReconnectGameMismatch, "Session token is not valid for this game",
		})
	}
	return g.byTicket(ticket), play.Option[sessionRefusal]{}
}

func (g *game) byTicket(ticket string) *participant {
	for _, p := range g.participants {
		if p.spec.Ticket == ticket {
			return p
		}
	}
	return nil
}

func (g *game) bindLocked(p *participant, entry *connEntry) Connection {
	replaced := p.conn
	if replaced != nil {
		g.m.evictLocked(replaced)
	}
	p.conn = entry.conn
	entry.bound = p
	entry.authTimer()
	return replaced
}

func (g *game) closeReplaced(replaced, conn Connection) {
	if replaced == nil {
		return
	}
	g.log.Info("replacing a participant's connection",
		"old_connection_id", replaced.ID(), "new_connection_id", conn.ID())
	replaced.Close(CloseReplaced, "replaced_by_new_connection")
	g.m.stats.takeovers.Add(1)
}

func (g *game) admit(p *participant, conn Connection) error {
	err := send(conn, messaging.GameJoined(g.timing.PendingGame.Seconds()))
	if err != nil {
		return err
	}

	connected := len(g.connected())
	g.log.Info("player joined pending game",
		"player_name", p.spec.Name, "connected", connected, "expected", len(g.participants))
	if connected < len(g.participants) {
		return nil
	}
	g.pending.cancel()
	return g.startGame()
}

func (g *game) pendingTimedOut(token uint64) error {
	if !g.pending.claim(token) || g.lifecycle != lifecyclePending {
		return nil
	}
	if len(g.connected()) == 0 {
		g.log.Warn("no players connected before timeout, cancelling game", "expected", len(g.participants))
		g.endGame(endAbandoned, play.Option[store.Result]{})
		return nil
	}
	return g.startGame()
}

func (g *game) startGame() error {
	g.lifecycle = lifecyclePlaying
	g.markPlaying()

	seed := g.m.cfg.Seeds()
	names := make([]string, 0, len(g.participants))
	for _, p := range g.participants {
		names = append(names, p.spec.Name)
	}
	seating := seatPlayers(names, seed)
	for i, p := range g.participants {
		p.seat, p.seated = seating.playerSeats[i], true
	}
	g.roster = messaging.Roster{GameID: g.id, Names: seating.names, AI: seating.ai}

	started, events, err := engine.NewGame(g.m.cfg.Setup(seed))
	if err != nil {
		return fmt.Errorf("start the engine game: %w", err)
	}
	g.engine = started
	g.replay = &replayLog{seed: seed, roster: g.roster}
	g.recordStart()
	g.log.Info("pending game completed")
	return g.openFirstWait(events)
}

func (g *game) markPlaying() {
	g.m.mu.Lock()
	defer g.m.mu.Unlock()

	if l := g.m.games[g.id]; l != nil && l.game == g {
		l.playing = true
	}
}

func (g *game) recordStart() {
	seats := make([]store.Player, tile.SeatCount)
	for i, name := range g.roster.Names {
		seats[i].Name = name
	}
	for _, p := range g.participants {
		seats[p.seat.Index()].UserID = p.spec.UserID
	}
	g.start = store.GameStart{GameID: g.id, StartedAt: g.clock.Now(), GameType: gameTypeHanchan, Seats: seats}

	written := make(chan struct{})
	g.startWritten = written
	start, db, ctx, log := g.start, g.m.cfg.DB, g.m.storeCtx, g.log
	g.m.wg.Go(func() {
		defer close(written)
		err := protect(func() error { return db.RecordStart(ctx, start) })
		if err != nil {
			log.Error("record the start of a game", "error", err)
		}
	})
}

func (g *game) openFirstWait(events []play.Emitted) error {
	head, held := splitFirstDraw(events)
	g.holdingDraw, g.held = true, held
	for _, e := range head {
		if dealt, ok := e.Event.(play.RoundStarted); ok {
			g.dealt[dealt.Seat.Index()] = dealt
		}
	}
	if g.timing.GameStartConfirm > 0 {
		opened := pause{startsGame: true, resultsShown: 1}
		for _, p := range g.connected() {
			opened.owing[p.seat.Index()] = true
		}
		g.pause = &opened
	}

	err := g.applyUpdate(head, play.Option[tile.Seat]{})
	if err != nil {
		return err
	}
	for _, p := range g.participants {
		if p.conn == nil {
			err = g.handOver(p, play.Some(wire.SeatControlAbsent))
			if err != nil {
				return err
			}
		}
	}

	if g.pause == nil {
		return g.beginRound(play.Option[tile.Seat]{})
	}
	return nil
}

func splitFirstDraw(events []play.Emitted) (head, held []play.Emitted) {
	at := slices.IndexFunc(events, func(e play.Emitted) bool {
		switch e.Event.(type) {
		case play.Drew, play.DrewNotice:
			return true
		case play.GameStarted, play.RoundStarted, play.Discarded, play.RiichiDeposited, play.FuritenChanged,
			play.Called, play.PaoAssigned, play.DoraRevealed, play.RoundEnded, play.GameEnded:
		}
		return false
	})
	if at < 0 {
		return events, nil
	}
	return events[:at], events[at:]
}

func (g *game) beginRound(actor play.Option[tile.Seat]) error {
	held := g.held
	g.holdingDraw, g.held = false, nil
	return g.followEngine(held, actor)
}

type seating struct {
	names       [tile.SeatCount]string
	ai          [tile.SeatCount]bool
	playerSeats []tile.Seat
}

func seatPlayers(names []string, seed engine.Seed) seating {
	permutation := engine.SeatPermutation(seed)
	s := seating{playerSeats: permutation[:len(names)]}
	for i := range s.ai {
		s.ai[i] = true
	}
	for i, seat := range s.playerSeats {
		s.names[seat.Index()], s.ai[seat.Index()] = names[i], false
	}

	number := 1
	for i := range s.names {
		if !s.ai[i] {
			continue
		}
		for slices.Contains(names, aiNamePrefix+strconv.Itoa(number)) {
			number++
		}
		s.names[i] = aiNamePrefix + strconv.Itoa(number)
		number++
	}
	return s
}
