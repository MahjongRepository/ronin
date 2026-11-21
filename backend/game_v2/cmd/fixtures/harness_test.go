package main

import (
	"bytes"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/google/go-cmp/cmp"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func testEnv(t *testing.T) env {
	t.Helper()
	return env{logger: slog.New(slog.DiscardHandler)}
}

func kyuushuIntoNextRound(t *testing.T, s *staging, rounds ...stagedWall) error {
	t.Helper()
	_, err := testEnv(t).play(t.Context(), s, alone("harness-check", rounds...), func(g *seatedGame) ([]transcript, error) {
		alice := g.client(player)
		alice.join()
		alice.confirmRound(secs(3), "")
		alice.kyuushu(secs(5), "")
		alice.confirmRound(secs(6), "")
		g.waitUntil(secs(7))
		return g.transcripts("harness_check", player)
	})
	return err
}

func assertFailureNames(t *testing.T, err error, want string) {
	t.Helper()
	if err == nil || !strings.Contains(err.Error(), want) {
		t.Errorf("scenario error = %v, want one naming %q", err, want)
	}
}

func TestSeatedGame_WhenAStagedDrawNamesAnotherSeat_ShouldFailNamingTheDraw(t *testing.T) {
	var s staging
	misseated := kyuushuWall(&s)
	misseated.draws[1] = s.draw(3, misseated.draws[1].id)

	err := kyuushuIntoNextRound(t, &s, misseated)

	assertFailureNames(t, err, "seat 1 drew staged draw 1 (staged for seat 3)")
}

func TestSeatedGame_WhenALaterRoundNamesAnotherDealer_ShouldFailNamingTheDealer(t *testing.T) {
	var s staging
	misdealt := kyuushuWall(&s)
	misdealt.draws, misdealt.dealer = nil, s.seat(1)

	err := kyuushuIntoNextRound(t, &s, kyuushuWall(&s), misdealt)

	assertFailureNames(t, err, "later round 0 was staged for dealer 1, not 0")
}

func TestSeatedGame_WhenAnExpectedRefusalNeverComes_ShouldFailNamingIt(t *testing.T) {
	var s staging
	staged := kyuushuWall(&s)

	_, err := testEnv(t).play(t.Context(), &s, alone("harness-check", staged), func(g *seatedGame) ([]transcript, error) {
		alice := g.client(player)
		alice.join()
		alice.confirmRound(secs(3), "")
		alice.resync(secs(4), "", messaging.SessionGameNotStarted)
		return g.transcripts("harness_check", player)
	})

	assertFailureNames(t, err, "never refused with game_not_started")
}

func TestSeatedGame_WhenAStepFallsOnAServerTimer_ShouldFailNamingTheMoment(t *testing.T) {
	var s staging
	staged := kyuushuWall(&s)

	_, err := testEnv(t).play(t.Context(), &s, alone("harness-check", staged), func(g *seatedGame) ([]transcript, error) {
		alice := g.client(player)
		alice.join()
		alice.confirmRound(startConfirmTimeout, "")
		return g.transcripts("harness_check", player)
	})

	assertFailureNames(t, err, "a step at 10s, the moment a server timer fires")
}

func TestSeatedGame_WhenAScriptNamesNoTile_ShouldFailWithTheNotationError(t *testing.T) {
	var s staging
	staged := kyuushuWall(&s)

	_, err := testEnv(t).play(t.Context(), &s, alone("harness-check", staged), func(g *seatedGame) ([]transcript, error) {
		alice := g.client(player)
		alice.join()
		s.id(0, "8z")
		return g.transcripts("harness_check", player)
	})

	if err == nil {
		t.Error("scenario error = nil, want the notation error of the script's tile")
	}
}

func TestSeededWall_ShouldDealTheRoundTheSeedDealsForThatDealer(t *testing.T) {
	start := play.Some(play.StartPosition{
		Scores: [tile.SeatCount]int{25000, 25000, 25000, 25000}, Dealer: tile.Seats()[2], RoundNumber: 3,
	})
	seededGame, seeded, seededErr := engine.NewGame(engine.Setup{Walls: play.Seeded{Seed: stagedSeed()}, Start: start})
	fixedGame, fixed, fixedErr := engine.NewGame(engine.Setup{
		Walls: play.Fixed{Walls: [][tile.TileIDCount]tile.TileID{seededWall(stagedSeed(), 3, tile.Seats()[2])}},
		Start: start,
	})
	if seededErr != nil || fixedErr != nil {
		t.Fatalf("NewGame errors = %v, %v", seededErr, fixedErr)
	}
	_, seededDraw, _ := seededGame.Begin()
	_, fixedDraw, _ := fixedGame.Begin()

	if diff := cmp.Diff(dealtTiles(append(seeded, seededDraw...)), dealtTiles(append(fixed, fixedDraw...))); diff != "" {
		t.Errorf("seeded wall deals unlike the seed (-seed +wall):\n%s", diff)
	}
}

func dealtTiles(events []play.Emitted) [][]int {
	var dealt [][]int
	for _, e := range events {
		if dealtRound, ok := e.Event.(play.RoundStarted); ok {
			dealt = append(dealt, indices(dealtRound.Hand), indices(dealtRound.DoraIndicators))
		}
		if drew, ok := e.Event.(play.Drew); ok {
			dealt = append(dealt, indices([]tile.TileID{drew.Tile}))
		}
	}
	return dealt
}

func indices(ids []tile.TileID) []int {
	out := make([]int, 0, len(ids))
	for _, id := range ids {
		out = append(out, id.Index())
	}
	return out
}

func TestTranscriptText_ShouldWriteOneEventPerLineWithSortedKeysAsPythonJSON(t *testing.T) {
	got, err := transcript{
		scenario: "probe", gameID: "seat-probe", seat: 2,
		events: []transcriptEvent{
			{at: 1500 * time.Millisecond, kind: kindReceived, label: "named", fields: wire.StrMap{{
				Key: "payload", Value: wire.Map{
					{Key: wire.KeyWaitID, Value: wire.Int(3)},
					{Key: wire.KeyEventType, Value: wire.Int(9)},
					{Key: wire.KeyBankSeconds, Value: wire.Float(20)},
					{Key: wire.KeyScores, Value: wire.StrMap{{Key: "1", Value: wire.Int(-5)}, {Key: "0", Value: wire.Int(5)}}},
					{Key: wire.KeyName, Value: wire.Str("Zo\u00eb\u007f\n")},
				},
			}}},
			{at: 2 * time.Second, kind: kindClosed, fields: wire.StrMap{
				{Key: "reason", Value: wire.Str("")}, {Key: "code", Value: wire.Int(unseenDropCode)},
			}},
		},
	}.text()
	if err != nil {
		t.Fatalf("text error = %v", err)
	}

	want := `{
  "game_id": "seat-probe",
  "scenario": "probe",
  "seat": 2,
  "events": [
    {"at": 1500, "kind": "received", "label": "named", "payload": {"1": 9, "31": "Zo\u00eb\u007f\n", "53": {"0": 5, "1": -5}, "76": 20.0, "109": 3}},
    {"at": 2000, "code": 1006, "kind": "closed", "reason": ""}
  ]
}
`
	if got != want {
		t.Errorf("text =\n%s\nwant\n%s", got, want)
	}
}

func TestFixtureDir_WhenCommittedFilesDiffer_ShouldNameEachOrphanedMissingAndStaleOne(t *testing.T) {
	dir := t.TempDir()
	for name, content := range map[string]string{"kept.json": "same", "changed.json": "old", "orphan.json": "x", "a.txt": "y"} {
		err := os.WriteFile(filepath.Join(dir, name), []byte(content), 0o600)
		if err != nil {
			t.Fatalf("write %s: %v", name, err)
		}
	}

	problems, err := fixtureDir{path: dir, suffix: ".json"}.drift(map[string][]byte{
		"kept.json": []byte("same"), "changed.json": []byte("new"), "new.json": []byte("z"),
	})
	if err != nil {
		t.Fatalf("drift error = %v", err)
	}

	want := []string{"orphaned: orphan.json (no scenario produces it)", "stale: changed.json", "missing: new.json"}
	if diff := cmp.Diff(want, problems); diff != "" {
		t.Errorf("drift problems (-want +got):\n%s", diff)
	}
}

func TestRun_WhenTheFixturesWereJustWritten_ShouldFindNoDrift(t *testing.T) {
	dirs := []string{"-seat-scenarios", t.TempDir(), "-replays", t.TempDir()}
	var stdout, stderr bytes.Buffer
	if code := run(t.Context(), dirs, io.Discard, &stderr); code != 0 {
		t.Fatalf("writing run exit = %d, stderr:\n%s", code, stderr.String())
	}

	code := run(t.Context(), append([]string{"-check"}, dirs...), &stdout, &stderr)

	want := "25 seat transcript(s) up to date\n25 replay fixture(s) up to date\n"
	if code != 0 || stdout.String() != want {
		t.Errorf("check run exit = %d, stdout %q, stderr:\n%s", code, stdout.String(), stderr.String())
	}
}
