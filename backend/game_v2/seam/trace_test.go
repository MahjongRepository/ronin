package seam_test

import (
	"bufio"
	"compress/gzip"
	"encoding/json"
	"fmt"
	"os"
	"slices"
	"strings"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	tracesPath      = "testdata/traces.jsonl.gz"
	traceHeaderHead = `{"game":`
	seededTraceGame = "seeded"
	maxTraceLine    = 1 << 20
)

type traceHeader struct {
	Game    string              `json:"game"`
	Number  uint64              `json:"number"`
	Seed    string              `json:"seed"`
	Walls   [][]int             `json:"walls"`
	Scripts [][]json.RawMessage `json:"scripts"`
}

type tracedGame struct {
	header traceHeader
	name   string
	lines  []string
}

type traceLines struct {
	lines []string
}

func (l *traceLines) record(event play.Emitted) error {
	l.lines = append(l.lines, eventLine(event))
	return nil
}

type tracedAgent struct {
	inner agent
	trace *traceLines
}

func (a tracedAgent) observe(event play.Emitted) error {
	return a.inner.observe(event)
}

func (a tracedAgent) decide(decision play.Decision) (play.Action, error) {
	action, err := a.inner.decide(decision)
	if err != nil {
		return play.Action{}, err
	}
	a.trace.lines = append(a.trace.lines, decisionLine(decision, action))
	return action, nil
}

type scripted struct {
	script []play.Action
}

func (*scripted) observe(play.Emitted) error {
	return nil
}

func (s *scripted) decide(decision play.Decision) (play.Action, error) {
	if len(s.script) > 0 && slices.Contains(decision.Legal, s.script[0]) {
		next := s.script[0]
		s.script = s.script[1:]
		return next, nil
	}
	return decision.Default, nil
}

func readTraces(t *testing.T) []tracedGame {
	t.Helper()
	file, err := os.Open(tracesPath)
	if err != nil {
		t.Fatalf("open %s: %v", tracesPath, err)
	}
	t.Cleanup(func() { _ = file.Close() })
	unzipped, err := gzip.NewReader(file)
	if err != nil {
		t.Fatalf("gunzip %s: %v", tracesPath, err)
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
		if len(games) == 0 {
			t.Fatalf("trace line before any game header: %s", line)
		}
		last := &games[len(games)-1]
		last.lines = append(last.lines, line)
	}
	if err := scanner.Err(); err != nil {
		t.Fatalf("read %s: %v", tracesPath, err)
	}
	return games
}

func readTraceHeader(t *testing.T, line string) tracedGame {
	t.Helper()
	var header traceHeader
	if err := json.Unmarshal([]byte(line), &header); err != nil {
		t.Fatalf("game header %s: %v", line, err)
	}
	name := header.Game
	if name == seededTraceGame {
		name = fmt.Sprintf("%s %d", seededTraceGame, header.Number)
	}
	return tracedGame{header: header, name: name}
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

func traceSetup(t *testing.T, header traceHeader) (engine.Setup, agents) {
	t.Helper()
	if header.Game == seededTraceGame {
		seed, err := engine.ParseSeed(header.Seed)
		if err != nil {
			t.Fatalf("seed %q: %v", header.Seed, err)
		}
		assertEqual(t, "seed of the game number", seed, selfPlaySeed(header.Number))
		return engine.Setup{Walls: play.Seeded{Seed: seed}}, selfPlayAgents(header.Number)
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

	if len(header.Scripts) != tile.SeatCount {
		t.Fatalf("%d scripts, want one per seat", len(header.Scripts))
	}
	var seated agents
	for i, script := range header.Scripts {
		actions := make([]play.Action, len(script))
		for j, raw := range script {
			actions[j] = readAction(t, raw)
			assertEqual(t, "scripted action read back", actionJSON(actions[j]), string(raw))
		}
		seated[i] = &scripted{script: actions}
	}
	return engine.Setup{Walls: play.Fixed{Walls: walls}}, seated
}

func assertSameTrace(t *testing.T, got, want []string) {
	t.Helper()
	for i := range min(len(got), len(want)) {
		if got[i] != want[i] {
			t.Fatalf("trace line %d differs:\n got %s\nwant %s", i+1, got[i], want[i])
		}
	}
	if len(got) != len(want) {
		t.Fatalf("trace has %d lines, want %d", len(got), len(want))
	}
}

func TestPlayGameChecked_WhenReplayingTheReferenceTraces_ShouldOfferTakeAndEmitExactlyTheSame(t *testing.T) {
	games := readTraces(t)
	seeded := 0
	for _, traced := range games {
		if traced.header.Game == seededTraceGame {
			seeded++
		}
	}
	assertEqual(t, "seeded traced games", seeded, tracedSeededGames)

	for _, traced := range games {
		t.Run(traced.name, func(t *testing.T) {
			t.Parallel()
			setup, inner := traceSetup(t, traced.header)
			trace := &traceLines{}
			var seated agents
			for i, a := range inner {
				seated[i] = tracedAgent{inner: a, trace: trace}
			}
			g, initial := newGame(t, setup)

			_, err := playGameChecked(&g, initial, seated, trace, selfPlayMaxSteps)
			if err != nil {
				t.Errorf("play error = %v", err)
			}
			assertSameTrace(t, trace.lines, traced.lines)
		})
	}
}
