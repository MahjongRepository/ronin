package migrate_test

import (
	"bytes"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/migrate"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/tenhou"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func TestRewrite_WhenEveryLegacyReplayIsRewritten_ShouldWriteItsCommittedRewriteByteForByte(t *testing.T) {
	for _, name := range legacyNames(t) {
		rewritten, err := migrate.Rewrite(legacyContent(t, name))
		if err != nil {
			t.Errorf("Rewrite(%s): %v", name, err)
			continue
		}

		path := filepath.Join(rewrittenDir, name+".msgpack")
		if *update {
			err = os.WriteFile(path, rewritten.Content, 0o600)
			if err != nil {
				t.Fatalf("write %s: %v", path, err)
			}
		}
		if want := readFile(t, path); !bytes.Equal(rewritten.Content, want) {
			t.Errorf("Rewrite(%s) = %x, want the committed %x", name, rewritten.Content, want)
		}
	}
}

func TestRewrittenReplays_ShouldDecodeAndConvertToATenhouLogExactlyWhenTheGameEnded(t *testing.T) {
	for _, name := range legacyNames(t) {
		records := rewrittenRecords(t, name)
		ended := eventOf(t, records[len(records)-1]) == wire.EventGameEnd

		_, err := tenhou.Convert(readFile(t, filepath.Join(rewrittenDir, name+".msgpack")))

		if ended && err != nil || !ended && !errors.Is(err, tenhou.ErrNoGameEnd) {
			t.Errorf("tenhou.Convert(rewritten %s) error = %v; game ended %v", name, err, ended)
		}
	}
}

func TestRewrittenChankanAdded_ShouldDeclareTheRobbedAddedKanAheadOfTheRonThatRobsIt(t *testing.T) {
	records := rewrittenRecords(t, "chankan_added")
	kanRecord, ron := records[len(records)-2], records[len(records)-1]

	wantKan := calledMeld(t, play.MeldAddedKan, 1, 0, 58, 56, 57, 58, 59)
	wantKan.Added = play.Some(tileIDs(t, 59)[0])
	if eventOf(t, kanRecord) != wire.EventMeld || !reflect.DeepEqual(meldOf(t, kanRecord), wantKan) {
		t.Errorf("record before the ron = %v, want the added kan %v", kanRecord, wantKan)
	}

	wins := arrayField(t, ron, wire.KeyWinners)
	wantScoreChanges := wire.StrMap{{Key: "0", Value: wire.Int(0)}, {Key: "1", Value: wire.Int(-120)}, {Key: "2", Value: wire.Int(120)}, {Key: "3", Value: wire.Int(0)}}
	scoreChanges, _ := ron.Get(wire.KeyScoreChanges)
	_, robbed := ron.Get(wire.KeyRobbedKan)
	if wire.ResultType(intField(t, ron, wire.KeyResultType)) != wire.ResultRon || intField(t, ron, wire.KeyLoserSeat) != 1 ||
		intField(t, ron, wire.KeyWinningTile) != 59 || len(wins) != 1 || robbed ||
		!reflect.DeepEqual(scoreChanges, wantScoreChanges) {
		t.Fatalf("round end = %v, want seat 1's 59 robbed for -120, +120 with no robbed kan field", ron)
	}

	win, _ := wins[0].(wire.Map)
	hand := mapField(t, win, wire.KeyHandResult)
	limit, _ := hand.Get(wire.KeyHandLimit)
	if intField(t, win, wire.KeyWinnerSeat) != 2 || intField(t, hand, wire.KeyHan) != 6 || intField(t, hand, wire.KeyFu) != 30 ||
		intField(t, hand, wire.KeyPoints) != 120 || limit != wire.Str("haneman") {
		t.Errorf("win = %v, want seat 2's 6 han 30 fu haneman of 120", win)
	}
}

func TestRewrittenChankanClosedKokushi_ShouldDeclareTheFourCopiesOfTheWonTileAsAClosedKanOfTheLoser(t *testing.T) {
	records := rewrittenRecords(t, "chankan_closed_kokushi")
	ron := records[lastOf(t, records, wire.EventRoundEnd)]
	kanRecord := records[lastOf(t, records, wire.EventRoundEnd)-1]

	want := wire.Meld{Caller: seatOf(t, 1), Kind: play.MeldClosedKan, Tiles: tileIDs(t, 32, 33, 34, 35)}
	if intField(t, ron, wire.KeyWinningTile) != 35 || !reflect.DeepEqual(meldOf(t, kanRecord), want) {
		t.Errorf("records before and at the ron = %v, %v; want seat 1's closed kan of 32-35 robbed by 35", kanRecord, ron)
	}
}

func TestRewrittenChankanAIReplacement_ShouldDeclareTheRobbedKanBeforeTheSeatLeftDuringItsPrompt(t *testing.T) {
	records := rewrittenRecords(t, "chankan_ai_replacement")
	end := lastOf(t, records, wire.EventRoundEnd)

	got := []wire.EventType{eventOf(t, records[end-3]), eventOf(t, records[end-2]), eventOf(t, records[end-1])}
	if want := []wire.EventType{wire.EventDraw, wire.EventMeld, wire.EventSeatControl}; !slices.Equal(got, want) {
		t.Errorf("records before the ron = %v, want the declarer's draw, its kan, then the leave", got)
	}
}

func TestRewrittenPao_ShouldAssignPaoRightAfterTheThirdDragonPonFromTheLiableSeat(t *testing.T) {
	records := rewrittenRecords(t, "pao")
	at := lastOf(t, records, wire.EventPaoAssigned)

	wantPon := calledMeld(t, play.MeldPon, 1, 0, 134, 132, 133, 134)
	if !reflect.DeepEqual(meldOf(t, records[at-1]), wantPon) || intField(t, records[at], wire.KeySeat) != 1 ||
		intField(t, records[at], wire.KeyPaoSeat) != 0 {
		t.Errorf("pao record %v after %v, want seat 1 made liable by seat 0 after the pon of 132-134", records[at], records[at-1])
	}
	if tsumo := records[lastOf(t, records, wire.EventRoundEnd)]; intField(t, tsumo, wire.KeyPaoSeat) != 0 {
		t.Errorf("tsumo = %v, want it still naming seat 0 liable", tsumo)
	}
}

func TestRewrittenDoubleYakuman_ShouldKeepTheDoubleAsScoredAndHoldTheFinalScoresInTenths(t *testing.T) {
	records := rewrittenRecords(t, "double_yakuman")
	tsumo := records[lastOf(t, records, wire.EventRoundEnd)]
	gameEnd := records[len(records)-1]

	hand := mapField(t, tsumo, wire.KeyHandResult)
	wantYaku := wire.Array{wire.Map{
		{Key: wire.KeyYakuID, Value: wire.Int(112)}, {Key: wire.KeyHan, Value: wire.Int(26)}, {Key: wire.KeyYakuYakumanCount, Value: wire.Int(2)},
	}}
	if intField(t, hand, wire.KeyHan) != 26 || intField(t, hand, wire.KeyYakumanCount) != 2 ||
		!reflect.DeepEqual(arrayField(t, hand, wire.KeyYaku), wantYaku) {
		t.Errorf("hand result = %v, want the 13-sided kokushi as the double it scored", hand)
	}

	var finals []int
	for _, standing := range arrayField(t, gameEnd, wire.KeyStandings) {
		finals = append(finals, intField(t, standing.(wire.Map), wire.KeyFinalScore))
	}
	if want := []int{1310, -270, -470, -570}; !slices.Equal(finals, want) {
		t.Errorf("final scores = %v, want %v, the old whole points in tenths", finals, want)
	}
}

func TestRewrittenCallsRedFives_ShouldKeepTheChiAndPonWithTheRedFivesTheyTook(t *testing.T) {
	legacy, err := wire.DecodeRecords(legacyContent(t, "calls_red_fives"))
	if err != nil {
		t.Fatalf("DecodeRecords: %v", err)
	}
	records := rewrittenRecords(t, "calls_red_fives")

	var melds []wire.Meld
	for _, record := range records[1:] {
		if eventOf(t, record) == wire.EventMeld {
			melds = append(melds, meldOf(t, record))
		}
	}
	want := []wire.Meld{
		calledMeld(t, play.MeldChi, 1, 0, 52, 48, 52, 56),
		calledMeld(t, play.MeldPon, 3, 2, 17, 16, 17, 18),
	}
	if !reflect.DeepEqual(melds, want) {
		t.Errorf("melds = %v, want %v", melds, want)
	}
	if end := len(records) - 1; !reflect.DeepEqual(records[1:end], legacy[1:end]) {
		t.Errorf("records before the ron differ from the legacy ones")
	}
}

func TestRewrittenDoubleRon_ShouldBeARonOfTheTwoWins(t *testing.T) {
	records := rewrittenRecords(t, "double_ron")
	ron := records[lastOf(t, records, wire.EventRoundEnd)]

	if wire.ResultType(intField(t, ron, wire.KeyResultType)) != wire.ResultRon || len(arrayField(t, ron, wire.KeyWinners)) != 2 {
		t.Errorf("round end = %v, want a ron of two wins", ron)
	}
}

func TestRewrite_WhenTheOldReplayIsCutInsideARecord_ShouldRewriteTheRecordsBeforeIt(t *testing.T) {
	content := legacyContent(t, "kans")
	whole := rewriteRecords(t, content)

	rewritten, err := migrate.Rewrite(content[:len(content)-3])
	if err != nil {
		t.Fatalf("Rewrite(cut kans): %v", err)
	}

	records, err := wire.DecodeReplay(rewritten.Content)
	if err != nil || !rewritten.Cut || rewritten.GameEnded || !reflect.DeepEqual(records, whole[:len(whole)-1]) {
		t.Errorf("Rewrite(cut kans) = %d records, cut %v, ended %v, %v; want the whole rewrite but its last record",
			len(records), rewritten.Cut, rewritten.GameEnded, err)
	}
}

func TestRewrite_WhenTheOldReplayCannotBeCarriedOverWhole_ShouldRefuseItWithTheKind(t *testing.T) {
	roundEndEdit := func(edit func(wire.Map) wire.Map) func([]wire.Map) []wire.Map {
		return func(events []wire.Map) []wire.Map {
			for i, e := range events {
				if v, _ := e.Get(wire.KeyEventType); v == wire.Int(wire.EventRoundEnd) {
					events[i] = edit(e)
				}
			}
			return events
		}
	}
	tests := []struct {
		name    string
		content []byte
		kind    migrate.FailureKind
	}{
		{"not MessagePack", []byte{0xc1}, migrate.FailureUnreadable},
		{"current version", readFile(t, filepath.Join(rewrittenDir, "kans.msgpack")), migrate.FailureVersion},
		{"a pao event", legacyEdited(t, "kans", func(events []wire.Map) []wire.Map {
			return append(events, wire.Map{{Key: wire.KeyEventType, Value: wire.Int(wire.EventPaoAssigned)}})
		}), migrate.FailureShape},
		{"an abort showing hands", legacyEdited(t, "kyuushu", roundEndEdit(func(m wire.Map) wire.Map {
			return with(m, wire.KeyShownHands, wire.Array{})
		})), migrate.FailureShape},
		{"a record after the game end", legacyEdited(t, "pao", func(events []wire.Map) []wire.Map {
			return append(events, events[0])
		}), migrate.FailureShape},
		{"a win without the pao its calls set", legacyEdited(t, "pao", roundEndEdit(func(m wire.Map) wire.Map {
			return without(without(m, wire.KeyPaoSeat), wire.KeyPaoLiability)
		})), migrate.FailureInconsistent},
		{"a robbed added kan of no pon", legacyEdited(t, "chankan_added", func(events []wire.Map) []wire.Map {
			return slices.DeleteFunc(events, func(e wire.Map) bool { v, _ := e.Get(wire.KeyEventType); return v == wire.Int(wire.EventMeld) })
		}), migrate.FailureInconsistent},
		{"a draw with no tiles remaining", legacyEdited(t, "kans", func(events []wire.Map) []wire.Map {
			return append(events[:1], without(events[1], wire.KeyTilesRemaining))
		}), migrate.FailureEncode},
		{"a yaku no Tenhou log names", legacyEdited(t, "pao", roundEndEdit(func(m wire.Map) wire.Map {
			hand := with(mapField(t, m, wire.KeyHandResult), wire.KeyYaku, wire.Array{wire.Map{
				{Key: wire.KeyYakuID, Value: wire.Int(99)}, {Key: wire.KeyHan, Value: wire.Int(13)}, {Key: wire.KeyYakuYakumanCount, Value: wire.Int(1)},
			}})
			return with(m, wire.KeyHandResult, hand)
		})), migrate.FailureExport},
	}
	for _, tc := range tests {
		_, err := migrate.Rewrite(tc.content)

		rewriteErr, ok := errors.AsType[migrate.RewriteError](err)
		if !ok || rewriteErr.Kind != tc.kind {
			t.Errorf("Rewrite(%s) error = %v, want a %s", tc.name, err, tc.kind)
		}
	}
}
