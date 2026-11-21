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

	b := g.m.bindJoining(g, conn, ticket)
	switch {
	case !b.registered:
		return nil
	case b.refused.OK:
		sendSessionError(g.log, conn, b.refused.Value.code, b.refused.Value.message)
		return nil
	}
	g.closeReplaced(b.participant, b.replaced, conn)
	return g.admit(b.participant, conn)
}

func (g *game) byTicket(ticket string) *participant {
	for _, p := range g.participants {
		if p.spec.Ticket == ticket {
			return p
		}
	}
	return nil
}

func (g *game) closeReplaced(p *participant, replaced, conn Connection) {
	if replaced == nil {
		return
	}
	p.log.Info("replacing a participant's connection",
		"old_connection_id", replaced.ID(), "new_connection_id", conn.ID())
	replaced.Close(CloseReplaced, "replaced_by_new_connection")
	g.m.stats.takeovers.Add(1)
}

func (g *game) admit(p *participant, conn Connection) error {
	err := send(conn, messaging.GameJoined(g.timing.PendingGame.Seconds()))
	if err != nil {
		return err
	}

	connected := g.connectedCount()
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
	if g.connectedCount() == 0 {
		g.log.Warn("no players connected before timeout, cancelling game", "expected", len(g.participants))
		g.endGame(endAbandoned, play.Option[store.Result]{})
		return nil
	}
	return g.startGame()
}

func (g *game) startGame() error {
	g.lifecycle = lifecyclePlaying

	seed := g.m.cfg.Seeds()
	names := make([]string, 0, len(g.participants))
	for _, p := range g.participants {
		names = append(names, p.spec.Name)
	}
	roster, seats := SeatPlayers(g.id, names, seed, g.seating)
	for i, p := range g.participants {
		p.seat, p.seated = seats[i], true
		p.log = g.log.With("seat", p.seat.Index())
	}
	g.roster = roster

	started, events, err := engine.NewGame(g.m.cfg.Setup(seed))
	if err != nil {
		return fmt.Errorf("start the engine game: %w", err)
	}
	err = g.recordStart()
	if err != nil {
		return fmt.Errorf("claim the game id: %w", err)
	}
	g.startRecorded = true
	g.m.markPlaying(g, StartedGame{
		GameID:    g.id,
		StartedAt: g.start.StartedAt,
		GameType:  g.start.GameType,
		Names:     namesFromEast(roster.Names, seed),
	})
	g.engine = started
	g.replay = messaging.NewReplayLog(seed, g.roster)
	g.log.Info("pending game completed")
	return g.openFirstWait(events)
}

func (g *game) recordStart() error {
	seats := make([]store.Player, tile.SeatCount)
	for i, name := range g.roster.Names {
		seats[i].Name = name
	}
	for _, p := range g.participants {
		seats[p.seat.Index()].UserID = p.spec.UserID
	}
	g.start = store.GameStart{GameID: g.id, StartedAt: g.clock.Now(), GameType: gameTypeHanchan, Seats: seats}
	return g.m.cfg.DB.RecordStart(g.m.storeCtx, g.start)
}

func (g *game) openFirstWait(events []play.Emitted) error {
	if g.timing.GameStartConfirm > 0 {
		opened := pause{startsGame: true, resultsShown: 1}
		for p := range g.connected() {
			opened.owing[p.seat.Index()] = true
		}
		g.pause = &opened
	}

	err := g.recordReplay(events)
	if err != nil {
		return err
	}
	err = g.applyUpdate(events, play.Option[tile.Seat]{})
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
		return g.begin(play.Option[tile.Seat]{})
	}
	return nil
}

func (g *game) begin(actor play.Option[tile.Seat]) error {
	next, events, refusal := g.engine.Begin()
	if refusal.OK {
		return errRefusedBegin
	}
	g.engine = next
	return g.followEngine(events, actor)
}

// SeatPlayers seats a game's players, given by name in input order, as the session seats them by
// seating: shuffled, the n-th player at the n-th seat of the seed's seat permutation, or fixed, the
// n-th player n seats after the seed's first dealer. It returns the game's roster, an AI player
// named in each seat no player takes, and each player's seat in input order.
func SeatPlayers(gameID string, names []string, seed engine.Seed, seating Seating) (messaging.Roster, []tile.Seat) {
	seats := playerSeats(len(names), seed, seating)
	roster := messaging.Roster{GameID: gameID}
	for i := range roster.AI {
		roster.AI[i] = true
	}
	for i, seat := range seats {
		roster.Names[seat.Index()], roster.AI[seat.Index()] = names[i], false
	}

	number := 1
	for i := range roster.Names {
		if !roster.AI[i] {
			continue
		}
		for slices.Contains(names, aiNamePrefix+strconv.Itoa(number)) {
			number++
		}
		roster.Names[i] = aiNamePrefix + strconv.Itoa(number)
		number++
	}
	return roster, seats
}

func playerSeats(count int, seed engine.Seed, seating Seating) []tile.Seat {
	if seating == SeatingFixed {
		seat, _, _ := engine.FirstDealer(seed)
		seats := make([]tile.Seat, count)
		for i := range seats {
			seats[i], seat = seat, seat.Next()
		}
		return seats
	}
	permutation := engine.SeatPermutation(seed)
	return permutation[:count]
}

func namesFromEast(names [tile.SeatCount]string, seed engine.Seed) [tile.SeatCount]string {
	var fromEast [tile.SeatCount]string
	seat, _, _ := engine.FirstDealer(seed)
	for i := range fromEast {
		fromEast[i], seat = names[seat.Index()], seat.Next()
	}
	return fromEast
}
