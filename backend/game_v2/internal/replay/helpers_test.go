package replay_test

import (
	"bufio"
	"compress/gzip"
	"encoding/json"
	"os"
	"reflect"
	"slices"
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
		if decodeErr := json.Unmarshal([]byte(line), &decision); decodeErr != nil {
			t.Fatalf("trace line %s: %v", line, decodeErr)
		}

		if decision.Decide == nil {
			continue
		}

		last := &games[len(games)-1]
		last.answers = append(last.answers, replay.SeatAction{
			Seat: seat(t, *decision.Decide), Action: readAction(t, decision.Action),
		})
	}

	if scanErr := scanner.Err(); scanErr != nil {
		t.Fatalf("read %s: %v", referenceTracesPath, scanErr)
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

func nextTraceAnswers(t *testing.T, awaiting play.Awaiting, answers []replay.SeatAction) []replay.SeatAction {
	t.Helper()
	call, open := awaiting.(play.AwaitingCall)
	if !open {
		return answers[:1]
	}

	if len(call.Seats) > len(answers) {
		t.Fatalf("trace ends with %d answers for %d callers", len(answers), len(call.Seats))
	}

	order := []play.ActionKind{play.ActionPass, play.ActionChi, play.ActionPon, play.ActionKan, play.ActionRon}
	return slices.SortedStableFunc(slices.Values(answers[:len(call.Seats)]), func(a, b replay.SeatAction) int {
		return slices.Index(order, a.Action.Kind()) - slices.Index(order, b.Action.Kind())
	})
}

func playTracedGame(t *testing.T, traced tracedGame) []replay.Step {
	t.Helper()
	g, events, err := engine.NewGame(traced.setup)
	if err != nil {
		t.Fatalf("NewGame error = %v", err)
	}

	begin := func(dealt []play.Emitted) []play.Emitted {
		if _, awaitsDraw := g.Awaiting().(play.AwaitingDealt); !awaitsDraw {
			return dealt
		}

		next, drew, refusal := g.Begin()
		if refusal.OK {
			t.Fatalf("Begin refused: %+v", refusal.Value)
		}

		g = next
		return append(dealt, drew...)
	}

	events = begin(events)
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
		dealt = begin(dealt)
		steps = append(steps, replay.Step{Events: dealt, Game: g})
	}

	for answers := traced.answers; len(answers) > 0; {
		deal()
		batch := nextTraceAnswers(t, g.Awaiting(), answers)
		for _, answer := range batch {
			next, emitted, refusal := g.Act(answer.Seat, answer.Action)
			if refusal.OK {
				t.Fatalf("Act(%+v) refused: %+v", answer, refusal.Value)
			}

			g = next
			steps = append(steps, replay.Step{Events: emitted, Game: g})
		}

		answers = answers[len(batch):]
	}

	deal()
	if _, over := g.Awaiting().(play.AwaitingGameOver); !over {
		t.Fatalf("the traced game is not over: %+v", g.Awaiting())
	}

	return steps
}

func recordSteps(t *testing.T, seed engine.Seed, steps []replay.Step) []wire.Map {
	t.Helper()
	log := messaging.NewReplayLog(seed, testRoster)
	for _, step := range steps {
		table := func() messaging.Table {
			return messaging.Table{Roster: testRoster, Record: step.Game.View(tile.Seats()[0]).Record}
		}

		if err := log.Collect(step.Events, table); err != nil {
			t.Fatalf("Collect error = %v", err)
		}
	}

	return log.Records()
}

func loadRecords(t *testing.T, records []wire.Map) replay.Replay {
	t.Helper()
	content, err := messaging.EncodeReplayRecords(records)
	if err != nil {
		t.Fatalf("EncodeReplayRecords error = %v", err)
	}

	loaded, err := replay.Load(content)
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
