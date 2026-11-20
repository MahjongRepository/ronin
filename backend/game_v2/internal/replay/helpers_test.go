package replay_test

import (
	"bufio"
	"compress/gzip"
	"encoding/json"
	"os"
	"reflect"
	"strconv"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replay"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	referenceTracesPath = "../../seam/testdata/traces.jsonl.gz"
	traceHeaderHead     = `{"game":`
	seededTraceGame     = "seeded"
	maxTraceLine        = 1 << 20
)

var testRoster = messaging.Roster{GameID: "game-0001", Names: [tile.SeatCount]string{"Alice", "Bob", "Charlie", "Diana"}}

type traceHeader struct {
	Game   string  `json:"game"`
	Number uint64  `json:"number"`
	Seed   string  `json:"seed"`
	Walls  [][]int `json:"walls"`
}

type traceDecision struct {
	Decide *int            `json:"decide"`
	Action json.RawMessage `json:"action"`
}

type tracedGame struct {
	name    string
	setup   engine.Setup
	seed    engine.Seed
	answers []replay.SeatAction
}

func seat(t *testing.T, n int) tile.Seat {
	t.Helper()
	got, ok := tile.NewSeat(n)
	if !ok {
		t.Fatalf("NewSeat(%d) refused", n)
	}
	return got
}

func id(t *testing.T, n int) tile.TileID {
	t.Helper()
	got, ok := tile.NewTileID(n)
	if !ok {
		t.Fatalf("NewTileID(%d) refused", n)
	}
	return got
}

func readReferenceTraces(t *testing.T) []tracedGame {
	t.Helper()
	file, err := os.Open(referenceTracesPath)
	if err != nil {
		t.Fatalf("open %s: %v", referenceTracesPath, err)
	}
	t.Cleanup(func() { _ = file.Close() })
	unzipped, err := gzip.NewReader(file)
	if err != nil {
		t.Fatalf("gunzip %s: %v", referenceTracesPath, err)
	}

	var games []tracedGame
	scanner := bufio.NewScanner(unzipped)
	scanner.Buffer(nil, maxTraceLine)
	for scanner.Scan() {
		line := scanner.Text()
		if strings.HasPrefix(line, traceHeaderHead) {
			games = append(games, readTraceHeader(t, line))
			continue
		}
		var decision traceDecision
		if err := json.Unmarshal([]byte(line), &decision); err != nil {
			t.Fatalf("trace line %s: %v", line, err)
		}
		if decision.Decide == nil {
			continue
		}
		last := &games[len(games)-1]
		last.answers = append(last.answers, replay.SeatAction{
			Seat: seat(t, *decision.Decide), Action: readAction(t, decision.Action),
		})
	}
	if err := scanner.Err(); err != nil {
		t.Fatalf("read %s: %v", referenceTracesPath, err)
	}
	return games
}

func readTraceHeader(t *testing.T, line string) tracedGame {
	t.Helper()
	var header traceHeader
	if err := json.Unmarshal([]byte(line), &header); err != nil {
		t.Fatalf("game header %s: %v", line, err)
	}
	if header.Game == seededTraceGame {
		seed, err := engine.ParseSeed(header.Seed)
		if err != nil {
			t.Fatalf("seed %q: %v", header.Seed, err)
		}
		return tracedGame{
			name:  seededTraceGame + " " + strconv.FormatUint(header.Number, 10),
			setup: engine.Setup{Walls: play.Seeded{Seed: seed}},
			seed:  seed,
		}
	}

	walls := make([][tile.TileIDCount]tile.TileID, len(header.Walls))
	for i, wall := range header.Walls {
		if len(wall) != tile.TileIDCount {
			t.Fatalf("wall %d holds %d tiles", i, len(wall))
		}
		for slot, n := range wall {
			walls[i][slot] = id(t, n)
		}
	}
	return tracedGame{name: header.Game, setup: engine.Setup{Walls: play.Fixed{Walls: walls}}}
}

type rawAction struct {
	Discard *int    `json:"discard"`
	Riichi  *int    `json:"riichi"`
	Pon     *[2]int `json:"pon"`
	Chi     *[2]int `json:"chi"`
	Kan     *string `json:"kan"`
	Tile    *int    `json:"tile"`
}

func readAction(t *testing.T, raw json.RawMessage) play.Action {
	t.Helper()
	var unit string
	if err := json.Unmarshal(raw, &unit); err == nil {
		units := map[string]play.Action{
			"tsumo": play.TsumoAction(), "ron": play.RonAction(), "kyuushu": play.KyuushuAction(), "pass": play.PassAction(),
		}
		action, ok := units[unit]
		if !ok {
			t.Fatalf("unknown action %s", raw)
		}
		return action
	}

	var fields rawAction
	if err := json.Unmarshal(raw, &fields); err != nil {
		t.Fatalf("action %s: %v", raw, err)
	}
	held := func(pair [2]int) [2]tile.TileID { return [2]tile.TileID{id(t, pair[0]), id(t, pair[1])} }
	switch {
	case fields.Discard != nil:
		return play.DiscardAction(id(t, *fields.Discard))
	case fields.Riichi != nil:
		return play.RiichiAction(id(t, *fields.Riichi))
	case fields.Pon != nil:
		return play.PonAction(held(*fields.Pon))
	case fields.Chi != nil:
		return play.ChiAction(held(*fields.Chi))
	case fields.Kan != nil && fields.Tile != nil:
		kinds := map[string]play.KanKind{"closed": play.KanClosed, "added": play.KanAdded, "open": play.KanOpen}
		kind, ok := kinds[*fields.Kan]
		if !ok {
			t.Fatalf("unknown kan %s", raw)
		}
		return play.KanAction(kind, id(t, *fields.Tile))
	}
	t.Fatalf("unknown action %s", raw)
	return play.Action{}
}

func playTracedGame(t *testing.T, traced tracedGame) []replay.Step {
	t.Helper()
	g, events, err := engine.NewGame(traced.setup)
	if err != nil {
		t.Fatalf("NewGame error = %v", err)
	}
	steps := []replay.Step{{Events: events, Game: g}}
	deal := func() {
		if _, over := g.Awaiting().(play.AwaitingRoundOver); !over {
			return
		}
		next, dealt, refusal := g.DealNextRound()
		if refusal.OK {
			t.Fatalf("DealNextRound refused: %+v", refusal.Value)
		}
		g = next
		steps = append(steps, replay.Step{Events: dealt, Game: g})
	}

	for _, answer := range traced.answers {
		deal()
		next, emitted, refusal := g.Act(answer.Seat, answer.Action)
		if refusal.OK {
			t.Fatalf("Act(%+v) refused: %+v", answer, refusal.Value)
		}
		g = next
		steps = append(steps, replay.Step{Played: play.Some(answer), Events: emitted, Game: g})
	}
	deal()

	if _, over := g.Awaiting().(play.AwaitingGameOver); !over {
		t.Fatalf("the traced game is not over: %+v", g.Awaiting())
	}
	return steps
}

func recordSteps(t *testing.T, seed engine.Seed, steps []replay.Step) []wire.Map {
	t.Helper()
	records := []wire.Map{wire.VersionRecord()}
	liveTiles := 0
	for _, step := range steps {
		table := messaging.Table{Roster: testRoster, Record: step.Game.View(tile.Seats()[0]).Record}
		var dealt []play.RoundStarted
		flush := func() {
			if len(dealt) > 0 {
				records = append(records, messaging.ReplayRoundStartedPayload(dealt))
				liveTiles = dealt[0].LiveTiles
				dealt = nil
			}
		}

		for _, emitted := range step.Events {
			if e, isDeal := emitted.Event.(play.RoundStarted); isDeal {
				dealt = append(dealt, e)
				continue
			}
			flush()
			record, kept := recordOf(t, emitted.Event, table, seed, &liveTiles)
			if kept {
				records = append(records, record)
			}
		}
		flush()
	}
	return records
}

func recordOf(t *testing.T, event play.Event, table messaging.Table, seed engine.Seed, liveTiles *int) (wire.Map, bool) {
	t.Helper()
	switch e := event.(type) {
	case play.GameStarted:
		return messaging.ReplayGameStartedPayload(e, testRoster, seed), true
	case play.Drew:
		*liveTiles = max(0, *liveTiles-1)
		return messaging.ReplayDrawPayload(e, *liveTiles), true
	case play.DrewNotice, play.FuritenChanged, play.RoundStarted:
		return nil, false
	case play.Discarded, play.RiichiDeposited, play.Called, play.PaoAssigned, play.DoraRevealed, play.RoundEnded,
		play.GameEnded:
	}
	record, err := messaging.EventPayload(event, table)
	if err != nil {
		t.Fatalf("EventPayload(%+v) error = %v", event, err)
	}
	return record, true
}

func encodeRecords(t *testing.T, records []wire.Map) []byte {
	t.Helper()
	content, err := wire.EncodeReplay(records)
	if err != nil {
		t.Fatalf("EncodeReplay error = %v", err)
	}
	return content
}

func loadRecords(t *testing.T, records []wire.Map) replay.Replay {
	t.Helper()
	loaded, err := replay.Load(encodeRecords(t, records))
	if err != nil {
		t.Fatalf("Load error = %v", err)
	}
	return loaded
}

func assertSameGame(t *testing.T, what string, got, want engine.Game) {
	t.Helper()
	if !reflect.DeepEqual(got, want) {
		t.Errorf("%s: the games differ (-got +want):\n%s", what, cmp.Diff(got, want, cmp.Exporter(func(reflect.Type) bool { return true })))
	}
}
