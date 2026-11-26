package replay_test

import (
	"errors"
	"os"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replay"
)

func TestRun_WhenReplayingTheRecordsOfEachReferenceGame_ShouldRecordTheSameReplayAndEndInTheSameGame(t *testing.T) {
	for _, traced := range readReferenceTraces(t) {
		t.Run(traced.name, func(t *testing.T) {
			t.Parallel()
			played := playTracedGame(t, traced)
			records := recordSteps(t, traced.seed, played)

			loaded := loadRecords(t, records)
			if loaded.Seed != traced.seed || loaded.Names != testRoster.Names {
				t.Fatalf("Load read seed %x and names %v, want the recorded ones", loaded.Seed, loaded.Names)
			}

			setup := traced.setup
			if _, seeded := setup.Walls.(play.Seeded); seeded {
				setup = engine.Setup{Walls: play.Seeded{Seed: loaded.Seed}}
			}

			replayed, err := replay.Run(setup, loaded.Actions)
			if err != nil {
				t.Fatalf("Run error = %v", err)
			}

			if diff := cmp.Diff(records, recordSteps(t, loaded.Seed, replayed)); diff != "" {
				t.Errorf("the run records another replay (-recorded +replayed):\n%s", diff)
			}

			assertSameGame(t, "final game", replayed[len(replayed)-1].Game, played[len(played)-1].Game)
		})
	}
}

func TestRun_WhenAnActionIsFromASeatTheGameDoesNotAwait_ShouldReturnItsRefusal(t *testing.T) {
	seed := engine.Seed{1}
	dealer, _, _ := engine.FirstDealer(seed)
	notDealer := seat(t, (dealer.Index()+1)%tile.SeatCount)
	actions := []replay.SeatAction{{Seat: notDealer, Action: play.DiscardAction(id(t, 0))}}

	_, err := replay.Run(engine.Setup{Walls: play.Seeded{Seed: seed}}, actions)

	want := replay.RefusedError{
		Index: 0, Played: actions[0], Refusal: play.Refusal{Kind: play.RefusalNotAwaited, Code: play.CodeSeatNotAwaited},
	}
	if got, ok := errors.AsType[replay.RefusedError](err); !ok || got != want {
		t.Errorf("Run error = %v, want %v", err, want)
	}
}

func TestRun_WhenActionsRemainAfterTheGameEnds_ShouldReturnActionAfterGameEndError(t *testing.T) {
	traced := readReferenceTraces(t)[0]
	loaded := loadRecords(t, recordSteps(t, traced.seed, playTracedGame(t, traced)))
	extra := replay.SeatAction{Seat: seat(t, 0), Action: play.DiscardAction(id(t, 0))}

	_, err := replay.Run(traced.setup, append(loaded.Actions, extra))

	want := replay.ActionAfterGameEndError{Index: len(loaded.Actions)}
	if got, ok := errors.AsType[replay.ActionAfterGameEndError](err); !ok || got != want {
		t.Errorf("Run error = %v, want %v", err, want)
	}
}

const fullGameReplayPath = "../../../../frontend/game_v2/src/fixtures/replays/full_game.msgpack"

func BenchmarkRun_FullGame(b *testing.B) {
	content, err := os.ReadFile(fullGameReplayPath)
	if err != nil {
		b.Fatalf("read the full game replay: %v", err)
	}

	loaded, err := replay.Load(content)
	if err != nil {
		b.Fatalf("Load error = %v", err)
	}

	setup := engine.Setup{Walls: play.Seeded{Seed: loaded.Seed}}

	steps := 0
	for b.Loop() {
		run, runErr := replay.Run(setup, loaded.Actions)
		if runErr != nil {
			b.Fatalf("Run error = %v", runErr)
		}

		steps = len(run)
	}

	b.ReportMetric(float64(steps), "steps/op")
}
