package server_test

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"slices"
	"sync"
	"testing"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/auth"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replay"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replayfile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/server"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	fullGameReplayPath = "../../../../frontend/game_v2/src/fixtures/replays/full_game.msgpack"
	fullGameFixtureID  = "fixture-fg"
)

type stoppedClock struct{}

func (stoppedClock) Now() time.Time {
	return time.Date(2026, time.January, 1, 0, 0, 0, 0, time.UTC)
}

func (stoppedClock) AfterFunc(time.Duration, func()) func() bool {
	return func() bool { return true }
}

type scriptedAction struct {
	player int
	action messaging.GameAction
	fields []wire.Field
}

type fullGameScript struct {
	fixture []byte
	loaded  replay.Replay
	names   []string
	actions []scriptedAction
	steps   int
}

func readFullGameScript(tb testing.TB) fullGameScript {
	tb.Helper()
	content, err := os.ReadFile(fullGameReplayPath)
	if err != nil {
		tb.Fatalf("read the full game replay: %v", err)
	}
	loaded, err := replay.Load(content)
	if err != nil {
		tb.Fatalf("Load error = %v", err)
	}
	if slices.Contains(loaded.AI[:], true) {
		tb.Fatalf("the full game replay seats an AI player: %v", loaded.AI)
	}

	permutation := engine.SeatPermutation(loaded.Seed)
	names := make([]string, tile.SeatCount)
	players := map[tile.Seat]int{}
	for i, seat := range permutation {
		names[i] = loaded.Names[seat.Index()]
		players[seat] = i
	}
	actions, steps, err := scriptFullGame(loaded, players)
	if err != nil {
		tb.Fatalf("script the full game: %v", err)
	}
	return fullGameScript{fixture: content, loaded: loaded, names: names, actions: actions, steps: steps}
}

type scriptWriter struct {
	game    engine.Game
	players map[tile.Seat]int
	actions []scriptedAction
	steps   int
}

func scriptFullGame(loaded replay.Replay, players map[tile.Seat]int) ([]scriptedAction, int, error) {
	g, _, err := engine.NewGame(engine.Setup{Walls: play.Seeded{Seed: loaded.Seed}})
	if err != nil {
		return nil, 0, err
	}
	w := &scriptWriter{game: g, players: players}
	w.confirmAll()
	err = w.begin()
	if err != nil {
		return nil, 0, err
	}

	next := 0
	for {
		switch awaiting := w.game.Awaiting().(type) {
		case play.AwaitingGameOver:
			if next != len(loaded.Actions) {
				return nil, 0, fmt.Errorf("the game ended with %d of %d actions played", next, len(loaded.Actions))
			}
			return w.actions, w.steps, nil
		case play.AwaitingRoundOver:
			err = w.dealNext()
		case play.AwaitingCall:
			next, err = w.answerCall(awaiting, loaded.Actions, next)
		case play.AwaitingDealt:
			err = errors.New("a dealt round awaits its first draw")
		case play.AwaitingTurn:
			if next == len(loaded.Actions) {
				return nil, 0, errors.New("the replay ran out of actions before the game ended")
			}
			err = w.play(loaded.Actions[next])
			next++
		}
		if err != nil {
			return nil, 0, err
		}
	}
}

func (w *scriptWriter) confirmAll() {
	for _, seat := range tile.Seats() {
		w.actions = append(w.actions, scriptedAction{player: w.players[seat], action: messaging.GameActionConfirmRound})
	}
}

func (w *scriptWriter) begin() error {
	next, _, refusal := w.game.Begin()
	if refusal.OK {
		return fmt.Errorf("the engine refused the first draw: %v", refusal.Value)
	}
	w.game = next
	w.steps++
	return nil
}

func (w *scriptWriter) dealNext() error {
	w.confirmAll()
	next, _, refusal := w.game.DealNextRound()
	if refusal.OK {
		return fmt.Errorf("the engine refused the next deal: %v", refusal.Value)
	}
	w.game = next
	w.steps++
	if _, dealt := next.Awaiting().(play.AwaitingDealt); !dealt {
		return nil
	}
	next, _, refusal = next.Begin()
	if refusal.OK {
		return fmt.Errorf("the engine refused the dealer's first draw: %v", refusal.Value)
	}
	w.game = next
	return nil
}

func (w *scriptWriter) answerCall(awaiting play.AwaitingCall, actions []replay.SeatAction, next int) (int, error) {
	answering := callAnswers(awaiting, actions[next:])
	for _, seat := range awaiting.Seats {
		if slices.Contains(answering, seat) {
			continue
		}
		if _, still := w.game.Awaiting().(play.AwaitingCall); !still {
			return next, nil
		}
		err := w.play(replay.SeatAction{Seat: seat, Action: play.PassAction()})
		if err != nil {
			return next, err
		}
	}
	for range answering {
		if _, still := w.game.Awaiting().(play.AwaitingCall); !still {
			return next, nil
		}
		err := w.play(actions[next])
		if err != nil {
			return next, err
		}
		next++
	}
	return next, nil
}

func callAnswers(awaiting play.AwaitingCall, actions []replay.SeatAction) []tile.Seat {
	if len(actions) == 0 || !slices.Contains(awaiting.Seats, actions[0].Seat) || !actions[0].Action.AnswersCall() ||
		actions[0].Action.Kind() == play.ActionPass {
		return nil
	}
	seats := []tile.Seat{actions[0].Seat}
	if actions[0].Action.Kind() != play.ActionRon {
		return seats
	}
	for _, later := range actions[1:] {
		if later.Action.Kind() != play.ActionRon {
			break
		}
		seats = append(seats, later.Seat)
	}
	return seats
}

func (w *scriptWriter) play(sa replay.SeatAction) error {
	scripted, err := w.message(sa)
	if err != nil {
		return err
	}
	next, _, refusal := w.game.Act(sa.Seat, sa.Action)
	if refusal.OK {
		return fmt.Errorf("the engine refused seat %d's %v: %v", sa.Seat.Index(), sa.Action.Kind(), refusal.Value)
	}
	w.game = next
	w.steps++
	w.actions = append(w.actions, scripted)
	return nil
}

func (w *scriptWriter) message(sa replay.SeatAction) (scriptedAction, error) {
	scripted := scriptedAction{player: w.players[sa.Seat]}
	held, _ := sa.Action.Held()
	switch sa.Action.Kind() {
	case play.ActionDiscard:
		scripted.action = messaging.GameActionDiscard
	case play.ActionRiichi:
		scripted.action = messaging.GameActionRiichi
	case play.ActionTsumo:
		scripted.action = messaging.GameActionTsumo
	case play.ActionRon:
		scripted.action = messaging.GameActionRon
	case play.ActionKyuushu:
		scripted.action = messaging.GameActionKyuushu
	case play.ActionPass:
		scripted.action = messaging.GameActionPass
	case play.ActionPon, play.ActionChi:
		scripted.action = messaging.GameActionPon
		if sa.Action.Kind() == play.ActionChi {
			scripted.action = messaging.GameActionChi
		}
		called, err := w.calledTile(sa.Seat)
		if err != nil {
			return scripted, err
		}
		scripted.fields = []wire.Field{tileIDField(called), {
			Key: wire.KeySequenceTiles, Value: wire.Array{wire.Int(held[0].Index()), wire.Int(held[1].Index())},
		}}
		return scripted, nil
	case play.ActionKan:
		scripted.action = messaging.GameActionKan
		kind, _ := sa.Action.Kan()
		scripted.fields = []wire.Field{{Key: wire.KeyActionKanType, Value: wire.Str(kanTypeName(kind))}}
	}
	if id, ok := sa.Action.Tile(); ok {
		scripted.fields = append(scripted.fields, tileIDField(id))
	}
	return scripted, nil
}

func (w *scriptWriter) calledTile(seat tile.Seat) (tile.TileID, error) {
	decision, ok := w.game.Decision(seat)
	if !ok {
		return tile.TileID{}, fmt.Errorf("seat %d calls with no decision open", seat.Index())
	}
	call, isCall := decision.Context.(play.Call)
	if !isCall {
		return tile.TileID{}, fmt.Errorf("seat %d calls outside a call prompt", seat.Index())
	}
	return call.Tile, nil
}

func tileIDField(id tile.TileID) wire.Field {
	return wire.Field{Key: wire.KeyTileID, Value: wire.Int(id.Index())}
}

func kanTypeName(kind play.KanKind) string {
	switch kind {
	case play.KanOpen:
		return "open"
	case play.KanClosed:
		return "closed"
	case play.KanAdded:
		return "added"
	}
	return ""
}

type benchConn struct {
	id     string
	gameID string

	mu        sync.Mutex
	frames    [][]byte
	sent      int
	waitID    int
	closeCode session.CloseCode
	closed    bool
}

func (c *benchConn) ID() string {
	return c.id
}

func (c *benchConn) GameID() string {
	return c.gameID
}

func (c *benchConn) Send(data []byte) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.closed {
		return
	}
	c.frames = append(c.frames, data)
	c.sent++
}

func (c *benchConn) Close(code session.CloseCode, _ string) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if !c.closed {
		c.closed, c.closeCode = true, code
	}
}

func (c *benchConn) latestWaitID() (int, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	for _, frame := range slices.Backward(c.frames) {
		m, err := wire.Decode(frame)
		if err != nil {
			return 0, err
		}
		if id, ok := m.Int(wire.KeyWaitID); ok {
			c.waitID = id
			break
		}
	}
	c.frames = c.frames[:0]
	return c.waitID, nil
}

type fullGameTable struct {
	manager  *session.Manager
	router   *server.Router
	db       *store.DB
	replays  replayfile.Dir
	schedule []clientStep
}

type clientStep struct {
	player  int
	join    bool
	message []byte
	after   []int
}

func openFullGameTable(tb testing.TB, script fullGameScript) *fullGameTable {
	tb.Helper()
	dir := tb.TempDir()
	logger := slog.New(slog.NewTextHandler(io.Discard, &slog.HandlerOptions{Level: slog.LevelInfo}))
	db, err := store.Open(context.Background(), filepath.Join(dir, "game.db"), logger)
	if err != nil {
		tb.Fatalf("store.Open error = %v", err)
	}
	replays := replayfile.New(filepath.Join(dir, "replays"))
	manager, err := session.New(context.Background(), session.Config{
		Timing:   session.DefaultTiming(),
		Capacity: 1,
		DB:       db,
		Replays:  replays,
		Logger:   logger,
		Clock:    stoppedClock{},
		Seeds:    func() engine.Seed { return script.loaded.Seed },
	})
	if err != nil {
		tb.Fatalf("session.New error = %v", err)
	}
	table := &fullGameTable{
		manager: manager, router: server.NewRouter(manager, ticketSecret, logger, stoppedClock{}.Now),
		db: db, replays: replays,
	}
	tb.Cleanup(func() {
		err := errors.Join(manager.Shutdown(context.Background()), db.Close())
		if err != nil {
			tb.Errorf("close the table: %v", err)
		}
	})
	return table
}

func (t *fullGameTable) play(script fullGameScript, gameID string) ([]*benchConn, error) {
	specs := make([]session.PlayerSpec, 0, len(script.names))
	conns := make([]*benchConn, 0, len(script.names))
	for i, name := range script.names {
		ticket := auth.SignTicket(auth.Ticket{
			UserID: "user-" + name, Username: name, RoomID: gameID,
			ExpiresAt: float64(stoppedClock{}.Now().Add(time.Hour).Unix()),
		}, ticketSecret)
		specs = append(specs, session.PlayerSpec{Name: name, UserID: "user-" + name, Ticket: ticket})
		conns = append(conns, &benchConn{id: fmt.Sprintf("%s-%d", gameID, i), gameID: gameID})
	}
	err := t.manager.CreatePendingGame(gameID, specs)
	if err != nil {
		return nil, err
	}

	for i, conn := range conns {
		t.manager.Connect(conn)
		err = t.route(conns, i, true, wire.Map{
			{Key: wire.KeyEventType, Value: wire.Int(messaging.ClientJoinGame)},
			{Key: wire.KeyGameTicket, Value: wire.Str(specs[i].Ticket)},
		})
		if err != nil {
			return nil, err
		}
	}

	for _, scripted := range script.actions {
		conn := conns[scripted.player]
		waitID, waitErr := conn.latestWaitID()
		if waitErr != nil {
			return nil, waitErr
		}
		m := wire.Map{
			{Key: wire.KeyEventType, Value: wire.Int(messaging.ClientGameAction)},
			{Key: wire.KeyAction, Value: wire.Int(scripted.action)},
		}
		m = append(m, scripted.fields...)
		err = t.route(conns, scripted.player, false, append(m, wire.Field{Key: wire.KeyWaitID, Value: wire.Int(waitID)}))
		if err != nil {
			return nil, err
		}
	}
	return conns, endedGame(conns)
}

func (t *fullGameTable) route(conns []*benchConn, player int, join bool, m wire.Map) error {
	data, err := wire.Encode(m)
	if err != nil {
		return err
	}
	decoded, err := wire.Decode(data)
	if err != nil {
		return err
	}
	if t.schedule != nil {
		t.schedule = append(t.schedule, clientStep{player: player, join: join, message: data, after: sentCounts(conns)})
	}
	t.router.Route(conns[player], decoded)
	t.manager.Settle()
	return nil
}

func sentCounts(conns []*benchConn) []int {
	counts := make([]int, 0, len(conns))
	for _, conn := range conns {
		conn.mu.Lock()
		counts = append(counts, conn.sent)
		conn.mu.Unlock()
	}
	return counts
}

func endedGame(conns []*benchConn) error {
	for _, conn := range conns {
		conn.mu.Lock()
		closed, code := conn.closed, conn.closeCode
		conn.mu.Unlock()
		if !closed || code != session.CloseGameEnded {
			return fmt.Errorf("%s: closed %v with code %d once the script ran, want closed with %d",
				conn.id, closed, code, session.CloseGameEnded)
		}
	}
	return nil
}

func savedReplay(t *fullGameTable, gameID string) ([]byte, error) {
	compressed, err := t.replays.Read(gameID)
	if err != nil {
		return nil, err
	}
	return replayfile.Decompress(compressed, replayfile.MaxFileSize)
}

func TestRouter_WhenFourClientsPlayTheFullGameFixture_ShouldSaveTheFixtureReplay(t *testing.T) {
	script := readFullGameScript(t)
	table := openFullGameTable(t, script)

	_, err := table.play(script, fullGameFixtureID)
	if err != nil {
		t.Fatalf("play the full game: %v", err)
	}

	saved, err := savedReplay(table, fullGameFixtureID)
	if err != nil {
		t.Fatalf("read the saved replay: %v", err)
	}
	if !bytes.Equal(saved, script.fixture) {
		t.Errorf("the session saved %d replay bytes unlike the %d of the fixture", len(saved), len(script.fixture))
	}
}

func BenchmarkRouter_FullGame(b *testing.B) {
	script := readFullGameScript(b)
	table := openFullGameTable(b, script)

	games, messages := 0, 0
	for b.Loop() {
		games++
		conns, err := table.play(script, fmt.Sprintf("bench-%d", games))
		if err != nil {
			b.Fatalf("play game %d: %v", games, err)
		}
		for _, conn := range conns {
			messages += conn.sent
		}
	}
	b.ReportMetric(float64(script.steps), "steps/op")
	b.ReportMetric(float64(messages)/float64(games), "messages/op")
}
