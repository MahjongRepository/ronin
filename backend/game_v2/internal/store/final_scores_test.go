package store_test

import (
	"bytes"
	"database/sql"
	"encoding/json"
	"errors"
	"os"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
)

const pythonCompletedInTenths = `{"game_id":"game-completed","started_at":"2026-11-19T10:00:00.123456Z",` +
	`"ended_at":"2026-11-19T10:42:07.000005Z","end_reason":"completed","game_type":"hanchan","num_rounds_played":9,` +
	`"standings":[{"name":"Алиса <&>","seat":2,"user_id":"0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d","score":42300,"final_score":5230},` +
	`{"name":"alice","seat":0,"user_id":"5f0c2d1e-8b7a-4c3d-9e2f-1a0b3c4d5e6f","score":28100,"final_score":810},` +
	`{"name":"Tsumogiri 2","seat":3,"user_id":"","score":18600,"final_score":-2140},` +
	`{"name":"Tsumogiri 1","seat":1,"user_id":"","score":11000,"final_score":-3900}],"final_score_unit":"tenths"}`

func pythonRows(t *testing.T) []playedGameRow {
	t.Helper()
	content, err := os.ReadFile(pythonRowsPath)
	if err != nil {
		t.Fatalf("read %s: %v", pythonRowsPath, err)
	}

	var fixtures []struct {
		Row playedGameRow `json:"row"`
	}
	err = json.Unmarshal(content, &fixtures)
	if err != nil {
		t.Fatalf("decode %s: %v", pythonRowsPath, err)
	}

	rows := make([]playedGameRow, 0, len(fixtures))
	for _, f := range fixtures {
		rows = append(rows, f.Row)
	}

	return rows
}

func insertRows(t *testing.T, path string, rows ...playedGameRow) {
	t.Helper()
	conn, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatalf("open %s: %v", path, err)
	}
	defer closeChecked(t, conn)

	for _, r := range rows {
		_, err = conn.ExecContext(t.Context(),
			"INSERT INTO played_games (id, started_at, ended_at, end_reason, data) VALUES (?, ?, ?, ?, ?)",
			r.ID, r.StartedAt, r.EndedAt, r.EndReason, r.Data)
		if err != nil {
			t.Fatalf("insert %s: %v", r.ID, err)
		}
	}
}

func rowsByID(rows []playedGameRow) map[string]playedGameRow {
	byID := map[string]playedGameRow{}
	for _, r := range rows {
		byID[r.ID] = r
	}

	return byID
}

func TestMigrateFinalScores_WhenPythonWroteTheRows_ShouldConvertTheScoredOneToMarkedTenths(t *testing.T) {
	db, path := openDB(t, &bytes.Buffer{})
	python := pythonRows(t)
	insertRows(t, path, python...)

	migration, err := db.MigrateFinalScores(t.Context(), true)
	if err != nil {
		t.Fatalf("MigrateFinalScores: %v", err)
	}

	want := rowsByID(python)
	completed := want["game-completed"]
	completed.Data = pythonCompletedInTenths
	want["game-completed"] = completed
	if diff := cmp.Diff(want, readRows(t, path)); diff != "" {
		t.Errorf("rows after the migration (-want +got):\n%s", diff)
	}
	if diff := cmp.Diff(store.ScoreMigration{Converted: 1, Unscored: 3}, migration); diff != "" {
		t.Errorf("migration (-want +got):\n%s", diff)
	}
}

func TestMigrateFinalScores_WhenItRunsAgainBesideARowThisServerWrote_ShouldChangeNothing(t *testing.T) {
	db, path := openDB(t, &bytes.Buffer{})
	insertRows(t, path, pythonRows(t)...)
	start := fixtureStart("game-go", fixtureStartedAt)
	err := db.RecordCompleted(t.Context(), start, fixtureEndedAt, fixtureResult)
	if err != nil {
		t.Fatalf("RecordCompleted: %v", err)
	}

	_, err = db.MigrateFinalScores(t.Context(), true)
	if err != nil {
		t.Fatalf("first MigrateFinalScores: %v", err)
	}

	before := readRows(t, path)

	migration, err := db.MigrateFinalScores(t.Context(), true)
	if err != nil {
		t.Fatalf("second MigrateFinalScores: %v", err)
	}

	if diff := cmp.Diff(before, readRows(t, path)); diff != "" {
		t.Errorf("rows after the second run (-first +second):\n%s", diff)
	}
	if diff := cmp.Diff(store.ScoreMigration{AlreadyTenths: 2, Unscored: 3}, migration); diff != "" {
		t.Errorf("second migration (-want +got):\n%s", diff)
	}
}

func TestMigrateFinalScores_WhenNotApplied_ShouldCountTheConversionAndWriteNothing(t *testing.T) {
	db, path := openDB(t, &bytes.Buffer{})
	python := pythonRows(t)
	insertRows(t, path, python...)

	migration, err := db.MigrateFinalScores(t.Context(), false)
	if err != nil {
		t.Fatalf("MigrateFinalScores: %v", err)
	}

	if diff := cmp.Diff(rowsByID(python), readRows(t, path)); diff != "" {
		t.Errorf("rows after a dry run (-python +got):\n%s", diff)
	}
	if migration.Converted != 1 {
		t.Errorf("dry run converted = %d, want 1", migration.Converted)
	}
}

func TestMigrateFinalScores_WhenARowIsNotTheJSONThisServerWrites_ShouldLeaveItAndReportIt(t *testing.T) {
	db, path := openDB(t, &bytes.Buffer{})
	completed := rowsByID(pythonRows(t))["game-completed"]
	unknownKey, reordered, unknownUnit, trailing := completed, completed, completed, completed
	unknownKey.ID, unknownKey.Data = "game-unknown-key", strings.Replace(completed.Data, `"game_type"`, `"rules":1,"game_type"`, 1)
	reordered.ID, reordered.Data = "game-reordered", strings.Replace(completed.Data, `"name":"Алиса <&>","seat":2,`, `"seat":2,"name":"Алиса <&>",`, 1)
	unknownUnit.ID, unknownUnit.Data = "game-unknown-unit", strings.TrimSuffix(completed.Data, "}")+`,"final_score_unit":"points"}`
	trailing.ID, trailing.Data = "game-trailing", completed.Data+"{}"
	insertRows(t, path, unknownKey, reordered, unknownUnit, trailing)

	migration, err := db.MigrateFinalScores(t.Context(), true)
	if err != nil {
		t.Fatalf("MigrateFinalScores: %v", err)
	}

	if diff := cmp.Diff(rowsByID([]playedGameRow{unknownKey, reordered, unknownUnit, trailing}), readRows(t, path)); diff != "" {
		t.Errorf("rows after the migration (-before +after):\n%s", diff)
	}

	wantErrs := map[string]error{
		"game-reordered":    store.ErrRowData,
		"game-trailing":     store.ErrRowData,
		"game-unknown-key":  store.ErrRowData,
		"game-unknown-unit": store.ErrUnknownMarker,
	}
	if len(migration.Failed) != len(wantErrs) || migration.Converted != 0 {
		t.Fatalf("migration = %+v, want the four rows failed", migration)
	}

	for _, failure := range migration.Failed {
		if !errors.Is(failure.Err, wantErrs[failure.GameID]) {
			t.Errorf("failure %v, want %v", failure, wantErrs[failure.GameID])
		}
	}
}
