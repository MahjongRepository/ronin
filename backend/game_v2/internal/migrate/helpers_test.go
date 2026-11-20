package migrate_test

import (
	"flag"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/migrate"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	legacyDir    = "../wire/testdata/legacy"
	rewrittenDir = "../wire/testdata/rewritten"
)

var update = flag.Bool("update", false, "rewrite the expected rewritten replays from the legacy ones")

func legacyNames(t *testing.T) []string {
	t.Helper()
	paths, err := filepath.Glob(filepath.Join(legacyDir, "*.msgpack"))
	if err != nil || len(paths) == 0 {
		t.Fatalf("glob %s: %d files, %v", legacyDir, len(paths), err)
	}
	names := make([]string, 0, len(paths))
	for _, p := range paths {
		names = append(names, strings.TrimSuffix(filepath.Base(p), ".msgpack"))
	}
	return names
}

func readFile(t *testing.T, path string) []byte {
	t.Helper()
	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return content
}

func legacyContent(t *testing.T, name string) []byte {
	t.Helper()
	return readFile(t, filepath.Join(legacyDir, name+".msgpack"))
}

func rewrittenRecords(t *testing.T, name string) []wire.Map {
	t.Helper()
	records, err := wire.DecodeReplay(readFile(t, filepath.Join(rewrittenDir, name+".msgpack")))
	if err != nil {
		t.Fatalf("DecodeReplay(rewritten %s): %v", name, err)
	}
	return records
}

func rewriteRecords(t *testing.T, content []byte) []wire.Map {
	t.Helper()
	rewritten, err := migrate.Rewrite(content)
	if err != nil {
		t.Fatalf("Rewrite: %v", err)
	}
	records, err := wire.DecodeReplay(rewritten.Content)
	if err != nil {
		t.Fatalf("DecodeReplay(rewritten): %v", err)
	}
	return records
}

func legacyEdited(t *testing.T, name string, edit func(events []wire.Map) []wire.Map) []byte {
	t.Helper()
	content := legacyContent(t, name)
	records, err := wire.DecodeRecords(content)
	if err != nil {
		t.Fatalf("DecodeRecords(legacy %s): %v", name, err)
	}

	edited := slices.Clone(legacyHead(t, content))
	for _, record := range edit(slices.Clone(records[2:])) {
		encoded, encodeErr := wire.Encode(record)
		if encodeErr != nil {
			t.Fatalf("encode %v: %v", record, encodeErr)
		}
		edited = append(edited, encoded...)
	}
	return edited
}

func legacyHead(t *testing.T, content []byte) []byte {
	t.Helper()
	for end := range content {
		records, err := wire.DecodeRecords(content[:end])
		if err == nil && len(records) == 2 {
			return content[:end]
		}
	}
	t.Fatal("no version record and game start at the head of the replay")
	return nil
}

func eventOf(t *testing.T, record wire.Map) wire.EventType {
	t.Helper()
	return wire.EventType(intField(t, record, wire.KeyEventType))
}

func intField(t *testing.T, m wire.Map, k wire.Key) int {
	t.Helper()
	v, _ := m.Get(k)
	n, ok := v.(wire.Int)
	if !ok {
		t.Fatalf("field %v of %v is no integer", k, m)
	}
	return int(n)
}

func mapField(t *testing.T, m wire.Map, k wire.Key) wire.Map {
	t.Helper()
	v, _ := m.Get(k)
	nested, ok := v.(wire.Map)
	if !ok {
		t.Fatalf("field %v of %v is no map", k, m)
	}
	return nested
}

func arrayField(t *testing.T, m wire.Map, k wire.Key) wire.Array {
	t.Helper()
	v, _ := m.Get(k)
	array, ok := v.(wire.Array)
	if !ok {
		t.Fatalf("field %v of %v is no array", k, m)
	}
	return array
}

func with(m wire.Map, k wire.Key, v wire.Value) wire.Map {
	out := slices.Clone(m)
	for i, f := range out {
		if f.Key == k {
			out[i].Value = v
			return out
		}
	}
	return append(out, wire.Field{Key: k, Value: v})
}

func without(m wire.Map, k wire.Key) wire.Map {
	return slices.DeleteFunc(slices.Clone(m), func(f wire.Field) bool { return f.Key == k })
}

func lastOf(t *testing.T, records []wire.Map, event wire.EventType) int {
	t.Helper()
	for i, record := range slices.Backward(records) {
		if eventOf(t, record) == event {
			return i
		}
	}
	t.Fatalf("no record of event %d", event)
	return 0
}

func meldOf(t *testing.T, record wire.Map) wire.Meld {
	t.Helper()
	meld, err := wire.UnpackMeld(intField(t, record, wire.KeyPackedMeld))
	if err != nil {
		t.Fatalf("UnpackMeld(%v): %v", record, err)
	}
	return meld
}

func seatOf(t *testing.T, n int) tile.Seat {
	t.Helper()
	seat, ok := tile.NewSeat(n)
	if !ok {
		t.Fatalf("seat %d out of range", n)
	}
	return seat
}

func tileIDs(t *testing.T, ns ...int) []tile.TileID {
	t.Helper()
	ids := make([]tile.TileID, 0, len(ns))
	for _, n := range ns {
		id, ok := tile.NewTileID(n)
		if !ok {
			t.Fatalf("tile id %d out of range", n)
		}
		ids = append(ids, id)
	}
	return ids
}

func calledMeld(t *testing.T, kind play.MeldKind, caller, from, called int, tiles ...int) wire.Meld {
	t.Helper()
	return wire.Meld{
		Caller: seatOf(t, caller),
		Kind:   kind,
		Tiles:  tileIDs(t, tiles...),
		Called: play.Some(tileIDs(t, called)[0]),
		From:   play.Some(seatOf(t, from)),
	}
}
