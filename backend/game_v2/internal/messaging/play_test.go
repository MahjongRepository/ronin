package messaging_test

import (
	"fmt"
	"slices"
	"strconv"
	"strings"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const selfPlayGames = 12

type replayLog struct {
	records   []wire.Map
	dealt     []play.RoundStarted
	liveTiles int
}

func (l *replayLog) flushDeal() {
	if len(l.dealt) > 0 {
		l.records = append(l.records, messaging.ReplayRoundStartedPayload(l.dealt))
		l.liveTiles = l.dealt[0].LiveTiles
		l.dealt = nil
	}
}

type shapedGame struct {
	t        *testing.T
	seed     engine.Seed
	game     engine.Game
	replay   replayLog
	results  map[string]int
	openings map[wire.EventType]int
	batches  int
}

func (s *shapedGame) record(event play.Emitted) {
	s.t.Helper()
	switch e := event.Event.(type) {
	case play.RoundStarted:
		s.replay.dealt = append(s.replay.dealt, e)
		return
	case play.GameStarted:
		s.replay.records = append(s.replay.records, messaging.ReplayGameStartedPayload(e, testRoster(), s.seed))
		return
	case play.Drew:
		s.replay.flushDeal()
		s.replay.liveTiles--
		s.replay.records = append(s.replay.records, messaging.ReplayDrawPayload(e, s.replay.liveTiles))
		return
	case play.DrewNotice, play.FuritenChanged:
		return
	case play.Discarded, play.RiichiDeposited, play.Called, play.PaoAssigned, play.DoraRevealed, play.RoundEnded,
		play.GameEnded:
	}

	s.replay.flushDeal()
	m := s.payload(event.Event)
	s.replay.records = append(s.replay.records, m)
}

func (s *shapedGame) payload(e play.Event) wire.Map {
	s.t.Helper()
	m, err := messaging.EventPayload(e, func() messaging.Table {
		return messaging.Table{Roster: testRoster(), Record: s.game.View(tile.Seats()[0]).Record}
	})
	if err != nil {
		s.t.Fatalf("EventPayload(%T) error = %v", e, err)
	}
	_, err = wire.Encode(m)
	if err != nil {
		s.t.Fatalf("Encode(%T) = %v: %v", e, err, m)
	}
	return m
}

func (s *shapedGame) apply(next engine.Game, events []play.Emitted) {
	s.t.Helper()
	s.game = next
	for _, e := range events {
		m := s.payload(e.Event)
		if ended, ok := e.Event.(play.RoundEnded); ok {
			s.checkRoundEnd(ended, m)
		}
		s.record(e)
	}
	s.replay.flushDeal()

	s.batches++
	for _, seat := range tile.Seats() {
		view := next.View(seat)
		if view.Decision.OK {
			opening := messaging.BuildOpening(view.Decision.Value)
			s.openings[wire.EventType(field(s.t, opening.Payload, wire.KeyEventType).(wire.Int))]++
			stamped := messaging.StampOpening(opening.Payload, 1, messaging.WholeSeconds(20), play.Some(0.5))
			if _, err := wire.Encode(stamped); err != nil {
				s.t.Fatalf("Encode(opening) error = %v: %v", err, stamped)
			}
		}
		if seat.Index() != s.batches%tile.SeatCount {
			continue
		}
		snapshot, err := messaging.ReconnectionPayload(view.Record, testRoster(), [tile.SeatCount]play.Option[wire.SeatControlReason]{})
		if err != nil {
			s.t.Fatalf("ReconnectionPayload error = %v", err)
		}
		reconnected := messaging.GameReconnected(snapshot, 1, play.Option[messaging.Pause]{}, timerSettings())
		if _, err := wire.Encode(reconnected); err != nil {
			s.t.Fatalf("Encode(snapshot) error = %v: %v", err, reconnected)
		}
	}
}

func (s *shapedGame) checkRoundEnd(ended play.RoundEnded, m wire.Map) {
	s.t.Helper()
	var wins []play.WinResult
	var shaped []wire.Map
	switch r := ended.Result.(type) {
	case play.Tsumo:
		s.results["tsumo"]++
		wins, shaped = []play.WinResult{r.Win}, []wire.Map{m}
	case play.Ron:
		s.results[fmt.Sprintf("ron of %d", len(r.Wins))]++
		wins = r.Wins
		for _, win := range field(s.t, m, wire.KeyWinners).(wire.Array) {
			shaped = append(shaped, win.(wire.Map))
		}
	case play.ExhaustiveDraw:
		s.results["exhaustive draw"]++
	case play.Abortive:
		s.results[fmt.Sprintf("abortive %T", r.Kind)]++
	}

	before := field(s.t, m, wire.KeyScores).(wire.StrMap)
	changes := field(s.t, m, wire.KeyScoreChanges).(wire.StrMap)
	for i, after := range ended.Scores {
		paid := int(before[i].Value.(wire.Int)+changes[i].Value.(wire.Int)) * wire.ScoreDivisor
		if paid != after {
			s.t.Errorf("round end %v: scores %v and changes %v do not make the scores after it %v", m, before, changes, ended.Scores)
		}
	}

	for i, win := range wins {
		hand := field(s.t, shaped[i], wire.KeyHandResult).(wire.Map)
		han, isHan := win.Value.(play.Han)
		total := 0
		for _, yaku := range field(s.t, hand, wire.KeyYaku).(wire.Array) {
			total += int(field(s.t, yaku.(wire.Map), wire.KeyHan).(wire.Int))
		}
		if isHan && total != han.Han {
			s.t.Errorf("win %+v: yaku han sum to %d, want %d: %v", win, total, han.Han, hand)
		}
		points := int(field(s.t, hand, wire.KeyPoints).(wire.Int))
		sticks := int(field(s.t, shaped[i], wire.KeyRiichiCollected).(wire.Int))
		bonus := int(field(s.t, shaped[i], wire.KeyHonbaBonus).(wire.Int))
		if points <= 0 || (points+bonus)*wire.ScoreDivisor+sticks*engine.RiichiStickValue != win.ScoreChanges[win.Winner.Index()] {
			s.t.Errorf("win %+v: points %d, honba %d, sticks %d do not make the winner's change", win, points, bonus, sticks)
		}
	}
}

func chooseAction(d play.Decision, hand []tile.TileID, step int) play.Action {
	for _, kind := range []play.ActionKind{play.ActionTsumo, play.ActionRon, play.ActionKyuushu, play.ActionRiichi} {
		if i := slices.IndexFunc(d.Legal, func(a play.Action) bool { return a.Kind() == kind }); i >= 0 {
			return d.Legal[i]
		}
	}
	if step%3 == 0 {
		for _, a := range d.Legal {
			if a.Kind() == play.ActionPon || a.Kind() == play.ActionChi || a.Kind() == play.ActionKan {
				return a
			}
		}
	}
	if _, isCall := d.Context.(play.Call); isCall {
		return d.Default
	}

	best, bestScore := d.Default, 1<<30
	for _, a := range d.Legal {
		id, ok := a.Tile()
		if a.Kind() != play.ActionDiscard || !ok {
			continue
		}
		if score := connectedness(hand, id.Kind()); score < bestScore {
			best, bestScore = a, score
		}
	}
	return best
}

func connectedness(hand []tile.TileID, kind tile.Kind) int {
	score := 0
	for _, other := range hand {
		k := other.Kind()
		switch {
		case k == kind:
			score += 3
		case kind.IsHonor() || k.IsHonor() || int(k)/9 != int(kind)/9:
		case k == kind+1 || k+1 == kind:
			score += 2
		case k == kind+2 || k+2 == kind:
			score++
		}
	}
	return score
}

func playShapedGame(t *testing.T, n int, results map[string]int, openings map[wire.EventType]int) {
	t.Helper()
	seed, err := engine.ParseSeed(strings.Repeat(fmt.Sprintf("%02x", byte(n*37+11)), engine.SeedBytes))
	if err != nil {
		t.Fatalf("ParseSeed error = %v", err)
	}
	g, events, err := engine.NewGame(engine.Setup{Walls: play.Seeded{Seed: seed}})
	if err != nil {
		t.Fatalf("NewGame error = %v", err)
	}
	s := &shapedGame{t: t, seed: seed, results: results, openings: openings}
	s.replay.records = []wire.Map{wire.VersionRecord()}
	s.apply(g, events)

	for step := 0; ; step++ {
		var refusal play.Option[play.Refusal]
		switch awaiting := s.game.Awaiting().(type) {
		case play.AwaitingTurn:
			d, _ := s.game.Decision(awaiting.Seat)
			hand := s.game.View(awaiting.Seat).Record.Hand
			g, events, refusal = s.game.Act(awaiting.Seat, chooseAction(d, hand, step))
		case play.AwaitingCall:
			d, _ := s.game.Decision(awaiting.Seats[0])
			g, events, refusal = s.game.Act(awaiting.Seats[0], chooseAction(d, nil, step))
		case play.AwaitingRoundOver:
			g, events, refusal = s.game.DealNextRound()
		case play.AwaitingGameOver:
			if _, err := wire.EncodeReplay(s.replay.records); err != nil {
				t.Fatalf("game %d: EncodeReplay error = %v", n, err)
			}
			return
		}
		if refusal.OK {
			t.Fatalf("game %d step %d refused: %+v", n, step, refusal.Value)
		}
		s.apply(g, events)
	}
}

func TestSelfPlay_WhenEveryEventOpeningAndSnapshotIsShaped_ShouldEncodeLiveAndAsAValidReplay(t *testing.T) {
	var results [selfPlayGames]map[string]int
	var openings [selfPlayGames]map[wire.EventType]int
	t.Run("games", func(t *testing.T) {
		for n := range selfPlayGames {
			results[n], openings[n] = map[string]int{}, map[wire.EventType]int{}
			t.Run(strconv.Itoa(n), func(t *testing.T) {
				t.Parallel()
				playShapedGame(t, n, results[n], openings[n])
			})
		}
	})

	for _, kind := range []string{"tsumo", "ron of 1", "exhaustive draw", "abortive play.KyuushuKyuuhai"} {
		if !slices.ContainsFunc(results[:], func(seen map[string]int) bool { return seen[kind] > 0 }) {
			t.Errorf("no %s among the results %v", kind, results)
		}
	}
	for _, opening := range []wire.EventType{wire.EventDraw, wire.EventTurn, wire.EventCallPrompt} {
		if !slices.ContainsFunc(openings[:], func(seen map[wire.EventType]int) bool { return seen[opening] > 0 }) {
			t.Errorf("no opening of type %d among %v", opening, openings)
		}
	}
}
