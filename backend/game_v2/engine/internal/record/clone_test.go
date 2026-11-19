package record_test

import (
	"reflect"
	"strconv"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/record"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func sliceArrays(v reflect.Value, path string, into map[uintptr]string) {
	switch kind := v.Kind(); {
	case kind == reflect.Slice:
		if v.Len() > 0 {
			into[v.Pointer()] = path
		}
		for i := range v.Len() {
			sliceArrays(v.Index(i), path+"["+strconv.Itoa(i)+"]", into)
		}
	case kind == reflect.Array:
		for i := range v.Len() {
			sliceArrays(v.Index(i), path+"["+strconv.Itoa(i)+"]", into)
		}
	case kind == reflect.Struct:
		for field, value := range v.Fields() {
			sliceArrays(value, path+"."+field.Name, into)
		}
	case kind == reflect.Interface && !v.IsNil():
		sliceArrays(v.Elem(), path, into)
	}
}

func assertNoSharedSlice(t *testing.T, got, kept any) {
	t.Helper()
	keptArrays := map[uintptr]string{}
	sliceArrays(reflect.ValueOf(kept), "kept", keptArrays)
	gotArrays := map[uintptr]string{}
	sliceArrays(reflect.ValueOf(got), "got", gotArrays)
	for data, path := range gotArrays {
		if keptPath, shared := keptArrays[data]; shared {
			t.Errorf("%s shares its backing array with %s", path, keptPath)
		}
	}
}

func everyResultRecord(t *testing.T) play.SeatRecord {
	t.Helper()
	melds := []play.MeldView{{Kind: play.MeldPon, Tiles: copies(t, 0, "777z"), Called: play.Some(tileOf(t, "7z"))}}
	shown := []play.ShownHand{{Seat: seat(t, 1), Hand: copies(t, 0, "123m"), Melds: melds}}
	river := []play.RiverTile{{Tile: tileOf(t, "1z")}}
	win := play.WinResult{
		Hand: copies(t, 0, "123p"), Melds: melds, Yaku: []play.YakuID{play.YakuRiichi},
		UraIndicators: copies(t, 0, "9s"),
	}
	results := []play.RoundResult{
		play.ExhaustiveDraw{Tenpai: shown, Nagashi: []play.NagashiRiver{{River: river}}},
		play.Tsumo{Win: win},
		play.Ron{Wins: []play.WinResult{win, win}, HeadBumped: []tile.Seat{seat(t, 2)}},
		play.Abortive{Kind: play.KyuushuKyuuhai{Hand: copies(t, 0, "19m19p19s1234567z")}},
		play.Abortive{Kind: play.FourRiichi{Hands: shown}},
		play.Abortive{Kind: play.TripleRon{Hands: shown}},
		play.Abortive{Kind: play.FourWinds{}},
		play.Abortive{Kind: play.FourKans{}},
	}
	r := play.SeatRecord{Hand: copies(t, 0, "456s"), DoraIndicators: copies(t, 0, "5z"), Result: results[1]}
	r.Players[0].River = river
	r.Players[0].Melds = melds
	for _, result := range results {
		r.History = append(r.History, play.FinishedRound{Result: result, RiichiSeats: []tile.Seat{seat(t, 0)}})
	}
	return r
}

func TestClone_ShouldShareNoSliceWithTheRecord(t *testing.T) {
	r := everyResultRecord(t)

	cloned := record.Clone(r)

	assertEqual(t, "clone", cloned, r)
	assertNoSharedSlice(t, cloned, r)
}

func TestClone_WhenARoundIsInPlay_ShouldHaveNoResultAndNilForEmptySlices(t *testing.T) {
	r := play.SeatRecord{Hand: []tile.TileID{}, History: []play.FinishedRound{}}

	cloned := record.Clone(r)

	if cloned.Result != nil || cloned.Hand != nil || cloned.History != nil {
		t.Errorf("Clone = %+v, want no result and nil slices", cloned)
	}
}
