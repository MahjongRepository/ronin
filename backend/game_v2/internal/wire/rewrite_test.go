package wire

import (
	"bytes"
	"os"
	"reflect"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	legacyChankanAddedPath    = "testdata/legacy/chankan_added.msgpack"
	rewrittenChankanAddedPath = "testdata/rewritten/chankan_added.msgpack"
)

var legacyRonWinFields = []Key{
	KeyWinnerSeat, KeyHandResult, KeyScoreChanges, KeyRiichiCollected, KeyClosedTiles, KeyMelds,
	KeyHonbaBonus, KeyPaoSeat, KeyUraDora,
}

func decodeLegacyRecords(t *testing.T, path string) []Map {
	t.Helper()
	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	d := decoder{data: content, limits: replayProfile.limits}
	var records []Map
	for d.pos < len(content) {
		record, recordErr := d.record()
		if recordErr != nil {
			t.Fatalf("record %d of %s: %v", len(records)+1, path, recordErr)
		}
		records = append(records, record)
	}
	return records
}

func intField(t *testing.T, m Map, k Key) int {
	t.Helper()
	v, _ := m.Get(k)
	n, ok := v.(Int)
	if !ok {
		t.Fatalf("field %v of %v is no integer", k, m)
	}
	return int(n)
}

func seatOf(t *testing.T, n int) tile.Seat {
	t.Helper()
	seat, ok := tile.NewSeat(n)
	if !ok {
		t.Fatalf("seat %d out of range", n)
	}
	return seat
}

func tileIDOf(t *testing.T, n int) tile.TileID {
	t.Helper()
	id, ok := tile.NewTileID(n)
	if !ok {
		t.Fatalf("tile id %d out of range", n)
	}
	return id
}

func rewriteLegacyReplay(t *testing.T, legacy []Map) []Map {
	t.Helper()
	pons := map[[2]int]Meld{}
	rewritten := []Map{VersionRecord()}
	for _, record := range legacy[1:] {
		event := EventType(intField(t, record, KeyEventType))
		if event == EventMeld {
			meld, err := UnpackMeld(intField(t, record, KeyPackedMeld))
			if err != nil {
				t.Fatalf("legacy meld %v: %v", record, err)
			}
			if meld.Kind == play.MeldPon {
				pons[[2]int{meld.Caller.Index(), int(meld.Tiles[0].Kind())}] = meld
			}
		}
		if event == EventRoundEnd {
			if robbed, ok := record.Get(KeyRobbedKan); ok {
				rewritten = append(rewritten, robbedAddedKanRecord(t, robbed.(Map), pons))
			}
			if ResultType(intField(t, record, KeyResultType)) == ResultRon {
				record = rewriteSingleRon(record)
			}
		}
		rewritten = append(rewritten, record)
	}
	return rewritten
}

func robbedAddedKanRecord(t *testing.T, robbed Map, pons map[[2]int]Meld) Map {
	t.Helper()
	added := tileIDOf(t, intField(t, robbed, KeyTileID))
	pon, ok := pons[[2]int{intField(t, robbed, KeySeat), int(added.Kind())}]
	if !ok {
		t.Fatalf("robbed kan %v has no recorded pon", robbed)
	}

	kan := pon
	kan.Kind = play.MeldAddedKan
	kan.Tiles = append(append([]tile.TileID(nil), pon.Tiles...), added)
	kan.Added = play.Some(added)
	packed, err := PackMeld(kan)
	if err != nil {
		t.Fatalf("pack robbed kan %v: %v", kan, err)
	}
	return Map{{Key: KeyEventType, Value: Int(EventMeld)}, {Key: KeyPackedMeld, Value: Int(packed)}}
}

func rewriteSingleRon(record Map) Map {
	win := Map{}
	for _, k := range legacyRonWinFields {
		if v, ok := record.Get(k); ok {
			win = append(win, Field{Key: k, Value: v})
		}
	}

	ron := Map{}
	for _, k := range []Key{KeyEventType, KeyResultType, KeyRiichiSticks, KeyDealer, KeyDoraIndicators, KeyLoserSeat, KeyWinningTile} {
		v, _ := record.Get(k)
		ron = append(ron, Field{Key: k, Value: v})
	}
	ron = append(ron, Field{Key: KeyWinners, Value: Array{win}})
	for _, k := range []Key{KeyScores, KeyScoreChanges, KeyHeadBumpedSeats} {
		if v, ok := record.Get(k); ok {
			ron = append(ron, Field{Key: k, Value: v})
		}
	}
	return ron
}

func TestReplayRewrite_WhenChankanAddedIsRewritten_ShouldEncodeTheCommittedReplayByteForByte(t *testing.T) {
	content, err := EncodeReplay(rewriteLegacyReplay(t, decodeLegacyRecords(t, legacyChankanAddedPath)))
	if err != nil {
		t.Fatalf("EncodeReplay(rewritten chankan_added): %v", err)
	}

	if *update {
		err = os.WriteFile(rewrittenChankanAddedPath, content, 0o600)
		if err != nil {
			t.Fatalf("write %s: %v", rewrittenChankanAddedPath, err)
		}
	}
	want, err := os.ReadFile(rewrittenChankanAddedPath)
	if err != nil {
		t.Fatalf("read %s: %v", rewrittenChankanAddedPath, err)
	}
	if !bytes.Equal(content, want) {
		t.Errorf("rewritten chankan_added = %x, want %x", content, want)
	}
}

func TestRewrittenChankanAdded_ShouldDeclareTheRobbedAddedKanAheadOfTheRonThatRobsIt(t *testing.T) {
	content, err := os.ReadFile(rewrittenChankanAddedPath)
	if err != nil {
		t.Fatalf("read %s: %v", rewrittenChankanAddedPath, err)
	}
	records, err := DecodeReplay(content)
	if err != nil {
		t.Fatalf("DecodeReplay(%s): %v", rewrittenChankanAddedPath, err)
	}
	kanRecord, ronRecord := records[len(records)-2], records[len(records)-1]

	kan, err := UnpackMeld(intField(t, kanRecord, KeyPackedMeld))
	wantKan := Meld{
		Caller: seatOf(t, 1),
		Kind:   play.MeldAddedKan,
		Tiles:  []tile.TileID{tileIDOf(t, 56), tileIDOf(t, 57), tileIDOf(t, 58), tileIDOf(t, 59)},
		Called: play.Some(tileIDOf(t, 58)),
		From:   play.Some(seatOf(t, 0)),
		Added:  play.Some(tileIDOf(t, 59)),
	}
	if err != nil || EventType(intField(t, kanRecord, KeyEventType)) != EventMeld || !reflect.DeepEqual(kan, wantKan) {
		t.Errorf("record before the ron = %v (%v, %v), want the added kan %v", kanRecord, kan, err, wantKan)
	}

	winners, _ := ronRecord.Get(KeyWinners)
	wins, _ := winners.(Array)
	scoreChanges, _ := ronRecord.Get(KeyScoreChanges)
	wantScoreChanges := StrMap{{"0", Int(0)}, {"1", Int(-120)}, {"2", Int(120)}, {"3", Int(0)}}
	if ResultType(intField(t, ronRecord, KeyResultType)) != ResultRon || intField(t, ronRecord, KeyLoserSeat) != 1 ||
		intField(t, ronRecord, KeyWinningTile) != 59 || len(wins) != 1 ||
		!reflect.DeepEqual(scoreChanges, wantScoreChanges) {
		t.Fatalf("round end = %v, want seat 1's 59 robbed for -120, +120", ronRecord)
	}

	win, _ := wins[0].(Map)
	handResult, _ := win.Get(KeyHandResult)
	hand, _ := handResult.(Map)
	limit, _ := hand.Get(KeyHandLimit)
	if intField(t, win, KeyWinnerSeat) != 2 || intField(t, hand, KeyHan) != 6 || intField(t, hand, KeyFu) != 30 ||
		intField(t, hand, KeyPoints) != 120 || limit != Str("haneman") {
		t.Errorf("win = %v, want seat 2's 6 han 30 fu haneman of 120", win)
	}
}
