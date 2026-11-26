package wire

import (
	"bytes"
	"errors"
	"os"
	"reflect"
	"strconv"
	"strings"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
)

const legacyChankanAddedPath = "testdata/legacy/chankan_added.msgpack"

func record(fields ...Field) Map {
	return Map(fields)
}

func field(k Key, v Value) Field {
	return Field{Key: k, Value: v}
}

func ints(values ...int) Array {
	array := Array{}
	for _, n := range values {
		array = append(array, Int(n))
	}

	return array
}

func with(m Map, k Key, v Value) Map {
	out := Map{}
	replaced := false
	for _, f := range m {
		if f.Key == k {
			f.Value = v
			replaced = true
		}

		out = append(out, f)
	}

	if !replaced {
		out = append(out, field(k, v))
	}

	return out
}

func without(m Map, k Key) Map {
	out := Map{}
	for _, f := range m {
		if f.Key != k {
			out = append(out, f)
		}
	}

	return out
}

func evenScores() StrMap {
	return StrMap{{Key: "0", Value: Int(250)}, {Key: "1", Value: Int(250)}, {Key: "2", Value: Int(250)}, {Key: "3", Value: Int(250)}}
}

func ronScoreChanges() StrMap {
	return StrMap{{Key: "0", Value: Int(0)}, {Key: "1", Value: Int(-120)}, {Key: "2", Value: Int(120)}, {Key: "3", Value: Int(0)}}
}

func gameStartedRecord() Map {
	return record(
		field(KeyEventType, Int(EventGameStarted)),
		field(KeyGameID, Str("game")),
		field(KeyGameType, Int(GameHanchan)),
		field(KeyPlayers, Array{
			record(field(KeySeat, Int(0)), field(KeyName, Str("A")), field(KeyAIPlayer, Int(0))),
			record(field(KeySeat, Int(1)), field(KeyName, Str("B")), field(KeyAIPlayer, Int(1))),
		}),
		field(KeyDealer, Int(0)),
		field(KeyDealerDice, Array{ints(1, 2), ints(3, 4)}),
		field(KeyRiichiStickValue, Int(10)),
		field(KeyHasAkadora, Bool(true)),
		field(KeySeed, Bin(make([]byte, ReplaySeedBytes))),
		field(KeyRNGVersion, Str("shake256-v1")),
		field(KeyGameSettings, ReplaySettings(play.RulesetTenhou)),
	)
}

func handResult() Map {
	return record(
		field(KeyHan, Int(6)),
		field(KeyFu, Int(30)),
		field(KeyYaku, Array{record(field(KeyYakuID, Int(1)), field(KeyHan, Int(1)), field(KeyYakuYakumanCount, Int(0)))}),
		field(KeyPoints, Int(120)),
		field(KeyHandLimit, Str("haneman")),
	)
}

func ronWin(seat int) Map {
	return record(
		field(KeyWinnerSeat, Int(seat)),
		field(KeyHandResult, handResult()),
		field(KeyScoreChanges, ronScoreChanges()),
		field(KeyRiichiCollected, Int(0)),
		field(KeyClosedTiles, ints(0, 4, 8)),
		field(KeyMelds, ints(23181)),
		field(KeyHonbaBonus, Int(0)),
		field(KeyPaoSeat, Int(1)),
		field(KeyUraDora, ints()),
	)
}

func roundEndRecord(result ResultType, fields ...Field) Map {
	return append(record(
		field(KeyEventType, Int(EventRoundEnd)),
		field(KeyResultType, Int(result)),
		field(KeyRiichiSticks, Int(0)),
		field(KeyDealer, Int(0)),
		field(KeyDoraIndicators, ints(112)),
	), fields...)
}

func ronRecord(wins ...Value) Map {
	return roundEndRecord(ResultRon,
		field(KeyLoserSeat, Int(1)),
		field(KeyWinningTile, Int(59)),
		field(KeyWinners, Array(wins)),
		field(KeyScores, evenScores()),
		field(KeyScoreChanges, ronScoreChanges()),
	)
}

func shownHand(seat int) Map {
	return record(field(KeySeat, Int(seat)), field(KeyClosedTiles, ints(0, 4, 8)), field(KeyMelds, ints()))
}

func everyShapeRecords() []Map {
	return []Map{
		VersionRecord(),
		gameStartedRecord(),
		record(field(KeyEventType, Int(EventMeld)), field(KeyPackedMeld, Int(18285))),
		record(field(KeyEventType, Int(EventPaoAssigned)), field(KeySeat, Int(2)), field(KeyPaoSeat, Int(1))),
		ronRecord(ronWin(2), ronWin(3)),
		ronRecord(ronWin(2), ronWin(3), ronWin(0)),
		roundEndRecord(ResultTsumo,
			field(KeyWinnerSeat, Int(2)),
			field(KeyHandResult, with(handResult(), KeyYakumanCount, Int(1))),
			field(KeyScores, evenScores()),
			field(KeyScoreChanges, ronScoreChanges()),
			field(KeyRiichiCollected, Int(0)),
			field(KeyClosedTiles, ints(0, 4, 8)),
			field(KeyMelds, ints()),
			field(KeyWinningTile, Int(59)),
			field(KeyHonbaBonus, Int(0)),
			field(KeyPaoLiability, record(field(KeyYaku, ints(34)), field(KeyPaoShare, Str("all")), field(KeyPaysHonba, Bool(true)))),
		),
		roundEndRecord(ResultExhaustiveDraw,
			field(KeyTenpaiSeats, ints(0)),
			field(KeyNotenSeats, ints(1, 2, 3)),
			field(KeyTenpaiHands, Array{shownHand(0)}),
			field(KeyQualifyingSeats, ints(1)),
			field(KeyQualifyingRivers, Array{record(field(KeySeat, Int(1)), field(KeyDiscards, Array{
				record(field(KeyTileID, Int(0)), field(KeyTsumogiri, Bool(true)), field(KeyRiichiDiscard, Bool(false))),
			}))}),
			field(KeyScores, evenScores()),
			field(KeyScoreChanges, evenScores()),
		),
		roundEndRecord(ResultAbortiveDraw,
			field(KeyAbortiveReason, Str("triple_ron")),
			field(KeyScores, evenScores()),
			field(KeyScoreChanges, StrMap{}),
			field(KeyShownHands, Array{shownHand(1), shownHand(2), shownHand(3)}),
			field(KeyRobbedKan, record(field(KeySeat, Int(0)), field(KeyTileID, Int(59)), field(KeyKanType, Str("added")))),
		),
		record(field(KeyEventType, Int(EventGameEnd)), field(KeyWinnerSeat, Int(2)),
			field(KeyStandings, Array{record(field(KeySeat, Int(2)), field(KeyScore, Int(370)), field(KeyFinalScore, Int(574)))}),
			field(KeyLeftoverBonus, Int(0)), field(KeyLeftoverRiichi, Int(0)), field(KeyRoundCount, Int(8)),
			field(KeyEndCause, Str("length")), field(KeyPlayers, Array{record(field(KeyName, Str("A")))})),
		record(field(KeyEventType, Int(EventSeatControl)), field(KeySeat, Int(1)), field(KeyAIPlayer, Int(1)),
			field(KeySeatControlReason, Int(SeatControlLeft))),
	}
}

func TestEncodeReplay_WhenEveryRecordShapeIsRecorded_ShouldDecodeTheSameRecords(t *testing.T) {
	records := everyShapeRecords()

	content, err := EncodeReplay(records)
	if err != nil {
		t.Fatalf("EncodeReplay: %v", err)
	}

	decoded, err := DecodeReplay(content)
	if err != nil || !reflect.DeepEqual(decoded, records) {
		t.Errorf("DecodeReplay(EncodeReplay(r)) = %v, %v; want %v", decoded, err, records)
	}
}

func TestEncodeReplay_WhenARecordBreaksTheFormat_ShouldRefuseItAtItsPosition(t *testing.T) {
	gameStarted := gameStartedRecord()
	players, _ := gameStarted.Get(KeyPlayers)
	ron := ronRecord(ronWin(2))
	tests := []struct {
		name   string
		record Map
	}{
		{"no event type", record(field(KeyPackedMove, Int(1)))},
		{"event type no integer", record(field(KeyEventType, Str("draw")))},
		{"event type past a byte", record(field(KeyEventType, Int(258)))},
		{"negative event type", record(field(KeyEventType, Int(-1)))},
		{"live-only event type", record(field(KeyEventType, Int(EventCallPrompt)))},
		{"missing field", record(field(KeyEventType, Int(EventDraw)), field(KeyPackedMove, Int(1)))},
		{"live-only key", record(field(KeyEventType, Int(EventDiscard)), field(KeyPackedMove, Int(1)), field(KeyAction, Int(0)))},
		{"float", record(field(KeyEventType, Int(EventDiscard)), field(KeyPackedMove, Float(1.5)))},
		{"integer field of a string", record(field(KeyEventType, Int(EventDiscard)), field(KeyPackedMove, Str("1")))},
		{"string field of an integer", with(gameStarted, KeyGameID, Int(1))},
		{"boolean field of an integer", with(gameStarted, KeyHasAkadora, Int(1))},
		{"binary data outside the seed", with(gameStarted, KeyGameID, Bin{1})},
		{"short seed", with(gameStarted, KeySeed, Bin(make([]byte, ReplaySeedBytes-1)))},
		{"hexadecimal seed", with(gameStarted, KeySeed, Str(strings.Repeat("00", ReplaySeedBytes)))},
		{"rules envelope of an integer", with(gameStarted, KeyGameSettings, Int(1))},
		{"rules envelope without overrides", with(gameStarted, KeyGameSettings, StrMap{{Key: "id", Value: Int(TenhouRulesProfileID)}})},
		{"unknown rules profile", with(gameStarted, KeyGameSettings, StrMap{{Key: "id", Value: Int(4)}, {Key: "overrides", Value: StrMap{}}})},
		{"rules profile of a boolean", with(gameStarted, KeyGameSettings, StrMap{{Key: "id", Value: Bool(true)}, {Key: "overrides", Value: StrMap{}}})},
		{"rules overrides", with(gameStarted, KeyGameSettings, StrMap{{Key: "id", Value: Int(TenhouRulesProfileID)}, {Key: "overrides", Value: StrMap{{Key: "has_akadora", Value: Bool(false)}}}})},
		{"rules overrides of an integer", with(gameStarted, KeyGameSettings, StrMap{{Key: "id", Value: Int(TenhouRulesProfileID)}, {Key: "overrides", Value: Int(0)}})},
		{"dealer dice of an integer", with(gameStarted, KeyDealerDice, Int(2))},
		{"one roll of dealer dice", with(gameStarted, KeyDealerDice, Array{ints(1, 2)})},
		{"dealer roll of an integer", with(gameStarted, KeyDealerDice, Array{Int(1), ints(1, 2)})},
		{"dealer roll of three dice", with(gameStarted, KeyDealerDice, Array{ints(1, 2, 3), ints(1, 2)})},
		{"dealer die of a string", with(gameStarted, KeyDealerDice, Array{Array{Int(1), Str("2")}, ints(1, 2)})},
		{"players of an integer", with(gameStarted, KeyPlayers, Int(4))},
		{"player of an integer", with(gameStarted, KeyPlayers, Array{Int(0)})},
		{"player without a name", with(gameStarted, KeyPlayers, append(players.(Array), record(field(KeySeat, Int(2)), field(KeyAIPlayer, Int(0)))))},
		{"player name of an integer", with(gameStarted, KeyPlayers, Array{record(field(KeySeat, Int(0)), field(KeyName, Int(0)), field(KeyAIPlayer, Int(0)))})},
		{"tile array of an integer", with(ron, KeyDoraIndicators, Int(112))},
		{"tile array holding a boolean", with(ron, KeyDoraIndicators, Array{Bool(false)})},
		{"unknown result type", with(ron, KeyResultType, Int(999))},
		{"negative result type", with(ron, KeyResultType, Int(-1))},
		{"retired double ron", with(ron, KeyResultType, Int(2))},
		{"retired nagashi mangan", with(ron, KeyResultType, Int(5))},
		{"ron without its wins", without(ron, KeyWinners)},
		{"ron of no win", ronRecord()},
		{"ron of four wins", ronRecord(ronWin(2), ronWin(3), ronWin(0), ronWin(1))},
		{"win without its hand result", ronRecord(without(ronWin(2), KeyHandResult))},
		{"hand result of an integer", ronRecord(with(ronWin(2), KeyHandResult, Int(6)))},
		{"hand result without its limit", ronRecord(with(ronWin(2), KeyHandResult, without(handResult(), KeyHandLimit)))},
		{"han of a string", ronRecord(with(ronWin(2), KeyHandResult, with(handResult(), KeyHan, Str("6"))))},
		{"yaku of an integer", ronRecord(with(ronWin(2), KeyHandResult, with(handResult(), KeyYaku, ints(1))))},
		{"honba bonus of a string", ronRecord(with(ronWin(2), KeyHonbaBonus, Str("0")))},
		{"pao yaku of objects", ronRecord(with(ronWin(2), KeyPaoLiability, record(
			field(KeyYaku, Array{handResult()}), field(KeyPaoShare, Str("all")), field(KeyPaysHonba, Bool(true)))))},
		{"seat control of an AI player without its reason", record(field(KeyEventType, Int(EventSeatControl)), field(KeySeat, Int(1)), field(KeyAIPlayer, Int(1)))},
	}
	versionBytes := len(appendValue(nil, VersionRecord()))
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Run(tc.name, func(t *testing.T) {
				content, err := EncodeReplay([]Map{VersionRecord(), tc.record})
				replayErr, isType := errors.AsType[ReplayError](err)
				if !isType || replayErr.Record != 2 || replayErr.Offset != versionBytes || replayErr.Incomplete {
					t.Errorf("EncodeReplay(%s) = %x, %v; want a ReplayError at record 2, byte %d", tc.name, content, err, versionBytes)
				}
			})
		})
	}
}

func TestEncodeReplay_WhenThereIsNoRecord_ShouldRefuseWithErrNoVersionRecord(t *testing.T) {
	content, err := EncodeReplay(nil)

	if !errors.Is(err, ErrNoVersionRecord) {
		t.Errorf("EncodeReplay(nil) = %x, %v; want ErrNoVersionRecord", content, err)
	}
}

func TestEncodeReplay_WhenTheFirstRecordIsNotThisVersion_ShouldRefuseWithAnUnsupportedVersionError(t *testing.T) {
	tests := []struct {
		name    string
		first   Map
		version Value
		message string
	}{
		{"old version", record(field(KeyReplayVersion, Str("0.4-dev"))), Str("0.4-dev"), `unsupported replay version "0.4-dev"`},
		{"no version record", gameStartedRecord(), nil, "the first record is no version record"},
		{"version record with an event type", with(VersionRecord(), KeyEventType, Int(EventGameStarted)), Str(ReplayVersion), "unsupported replay version"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			_, err := EncodeReplay([]Map{tc.first})
			versionErr, isType := errors.AsType[UnsupportedVersionError](err)
			if !isType || versionErr.Version != tc.version || !strings.Contains(err.Error(), tc.message) {
				t.Errorf("EncodeReplay(%v) = %v; want an UnsupportedVersionError of %v saying %q", tc.first, err, tc.version, tc.message)
			}
		})
	}
}

func TestDecodeReplay_WhenTheReplayIsOfVersion04Dev_ShouldRefuseItsFirstRecord(t *testing.T) {
	content, err := os.ReadFile(legacyChankanAddedPath)
	if err != nil {
		t.Fatalf("read %s: %v", legacyChankanAddedPath, err)
	}

	_, err = DecodeReplay(content)

	replayErr, isReplayErr := errors.AsType[ReplayError](err)
	versionErr, isVersionErr := errors.AsType[UnsupportedVersionError](err)
	if !isReplayErr || replayErr.Record != 1 || replayErr.Offset != 0 || !isVersionErr ||
		versionErr.Version != Str("0.4-dev") {
		t.Errorf("DecodeReplay(legacy) = %v; want record 1 refused for version 0.4-dev", err)
	}
}

func TestDecodeReplay_WhenTheContentEndsInsideARecord_ShouldReportItIncompleteWhereItStarts(t *testing.T) {
	complete, err := EncodeReplay(everyShapeRecords())
	if err != nil {
		t.Fatalf("EncodeReplay: %v", err)
	}

	for _, tail := range [][]byte{{0x81}, {0x81, 0x01}, {0x81, 0x01, 0xdb, 0, 0, 0, 5, 'a'}} {
		_, err = DecodeReplay(append(bytes.Clone(complete), tail...))

		want := len(everyShapeRecords()) + 1
		replayErr, isType := errors.AsType[ReplayError](err)
		if !isType || !replayErr.Incomplete || replayErr.Record != want || replayErr.Offset != len(complete) ||
			err.Error() != "incomplete replay record "+strconv.Itoa(want)+" at byte "+strconv.Itoa(len(complete)) {
			t.Errorf("DecodeReplay(complete + %x) = %v; want record %d incomplete at byte %d", tail, err, want, len(complete))
		}
	}
}

func TestDecodeRecords_WhenTheReplayIsOfVersion04Dev_ShouldReadEveryRecord(t *testing.T) {
	content, err := os.ReadFile(legacyChankanAddedPath)
	if err != nil {
		t.Fatalf("read %s: %v", legacyChankanAddedPath, err)
	}

	records, err := DecodeRecords(content)

	if err != nil || len(records) != 15 || !reflect.DeepEqual(records[0], Map{{Key: KeyReplayVersion, Value: Str("0.4-dev")}}) {
		t.Fatalf("DecodeRecords(legacy) = %d records, first %v, error %v; want 15 from the 0.4-dev version record", len(records), records[:1], err)
	}

	if got := appendRecords(records); !bytes.Equal(got, content) {
		t.Errorf("records re-encode to %x, want the file's bytes %x", got, content)
	}
}

func TestDecodeRecords_WhenTheContentEndsInsideARecord_ShouldReturnTheRecordsBeforeIt(t *testing.T) {
	complete, err := EncodeReplay(everyShapeRecords())
	if err != nil {
		t.Fatalf("EncodeReplay: %v", err)
	}

	records, err := DecodeRecords(append(bytes.Clone(complete), 0x81, 0x01))

	replayErr, isType := errors.AsType[ReplayError](err)
	if !isType || !replayErr.Incomplete || replayErr.Offset != len(complete) ||
		!reflect.DeepEqual(records, everyShapeRecords()) {
		t.Errorf("DecodeRecords(complete + cut) = %d records, %v; want every complete record and the cut one incomplete", len(records), err)
	}
}

func appendRecords(records []Map) []byte {
	var content []byte
	for _, record := range records {
		content = appendValue(content, record)
	}

	return content
}

func TestDecodeReplay_WhenARecordIsMalformed_ShouldReportItsPosition(t *testing.T) {
	version := appendValue(nil, VersionRecord())
	discard := record(field(KeyEventType, Int(EventDiscard)), field(KeyPackedMove, Int(1)))
	tests := []struct {
		name      string
		malformed []byte
		message   string
	}{
		{"reserved type", []byte{0xc1}, ""},
		{"not a map", []byte{0x91, 0x01}, ""},
		{"duplicate key", []byte{0x82, 0x01, 0x02, 0x01, 0x03}, ""},
		{"float", appendValue(nil, with(discard, KeyPackedMove, Float(1.5))), ""},
		{"unknown key", []byte{0x81, 0xcc, 0xc8, 0x01}, ""},
		{"long seed", appendValue(nil, with(gameStartedRecord(), KeySeed, Bin(make([]byte, ReplaySeedBytes+1)))), "binary of 97 exceeds 96"},
		{"long array", appendValue(nil, with(discard, KeyDoraIndicators, ints(make([]int, 4097)...))), ""},
		{"long string", appendValue(nil, with(discard, KeyName, Str(strings.Repeat("a", 4097)))), ""},
		{"wide map", append([]byte{0x81, byte(KeyHandResult), 0xde, 0, 129}, make([]byte, 258)...), "map of 129 exceeds 128"},
		{"seed of 96 hexa", appendValue(nil, with(gameStartedRecord(), KeySeed, Str(strings.Repeat("0", 2*ReplaySeedBytes)))), ""},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Run(tc.name, func(t *testing.T) {
				_, err := DecodeReplay(append(bytes.Clone(version), tc.malformed...))

				replayErr, isType := errors.AsType[ReplayError](err)
				if !isType || replayErr.Incomplete || replayErr.Record != 2 || replayErr.Offset != len(version) ||
					!strings.HasPrefix(err.Error(), "replay record 2 at byte "+strconv.Itoa(len(version))+": ") ||
					!strings.Contains(err.Error(), tc.message) {
					t.Errorf("DecodeReplay(version + %s) = %v; want record 2 refused at byte %d", tc.name, err, len(version))
				}
			})
		})
	}
}

func TestDecodeReplay_WhenTheContentIsEmptyOrTooLarge_ShouldRefuseIt(t *testing.T) {
	tests := []struct {
		name    string
		content []byte
		want    error
	}{
		{"empty", nil, ErrNoVersionRecord},
		{"too large", make([]byte, MaxReplayBytes+1), ErrReplayTooLarge},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			_, err := DecodeReplay(tc.content)
			if !errors.Is(err, tc.want) {
				t.Errorf("DecodeReplay(%d bytes) = %v, want %v", len(tc.content), err, tc.want)
			}
		})
	}
}

func TestReplaySettings_ShouldNameEachRulesetsProfileWithoutOverridesAndLoadItBack(t *testing.T) {
	tests := []struct {
		name    string
		ruleset play.Ruleset
		want    string
	}{
		{name: "tenhou", ruleset: play.RulesetTenhou, want: "82a2696402a96f7665727269646573" + "80"},
		{name: "rrc", ruleset: play.RulesetRRC, want: "82a2696403a96f7665727269646573" + "80"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := appendValue(nil, ReplaySettings(tc.ruleset))
			if want := hexBytes(t, tc.want); !bytes.Equal(got, want) {
				t.Errorf("ReplaySettings(%d) = %x, want %x", tc.ruleset, got, want)
			}

			if loaded, ok := RulesetOfProfile(RulesProfileOf(tc.ruleset)); !ok || loaded != tc.ruleset {
				t.Errorf("RulesetOfProfile(RulesProfileOf(%d)) = %d, %t, want %d, true", tc.ruleset, loaded, ok, tc.ruleset)
			}
		})
	}
}
