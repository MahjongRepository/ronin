package wire

import (
	"errors"
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func tileIDs(t *testing.T, ids ...int) []tile.TileID {
	t.Helper()
	tiles := make([]tile.TileID, 0, len(ids))
	for _, n := range ids {
		tiles = append(tiles, tileIDOf(t, n))
	}
	return tiles
}

func calledMeld(t *testing.T, kind play.MeldKind, caller, from int, called int, ids ...int) Meld {
	t.Helper()
	return Meld{
		Caller: seatOf(t, caller),
		Kind:   kind,
		Tiles:  tileIDs(t, ids...),
		Called: play.Some(tileIDOf(t, called)),
		From:   play.Some(seatOf(t, from)),
	}
}

func TestPackMeld_ShouldPackEachKindToTheIntegerTheWireCarries(t *testing.T) {
	addedKan := calledMeld(t, play.MeldAddedKan, 0, 3, 133, 135, 133, 132, 134)
	addedKan.Added = play.Some(tileIDOf(t, 134))
	tests := []struct {
		name string
		meld Meld
		want int
	}{
		{"chi", calledMeld(t, play.MeldChi, 2, 1, 10, 10, 0, 5), 82},
		{"pon", calledMeld(t, play.MeldPon, 0, 2, 111, 108, 109, 111), 20116},
		{"open kan", calledMeld(t, play.MeldOpenKan, 3, 1, 125, 124, 125, 126, 127), 27427},
		{"closed kan", Meld{Caller: seatOf(t, 1), Kind: play.MeldClosedKan, Tiles: tileIDs(t, 52, 53, 54, 55)}, 27605},
		{"added kan", addedKan, 25868},
	}
	for _, tc := range tests {
		packed, err := PackMeld(tc.meld)
		if packed != tc.want || err != nil {
			t.Errorf("PackMeld(%s) = %d, %v; want %d", tc.name, packed, err, tc.want)
		}
	}
}

func TestUnpackMeld_ShouldReadBackEveryPackableMeldWithItsTilesInOrder(t *testing.T) {
	for packed := range meldIndexCount * tile.SeatCount {
		meld, err := UnpackMeld(packed)
		if err != nil {
			t.Fatalf("UnpackMeld(%d): %v", packed, err)
		}
		repacked, err := PackMeld(meld)
		sorted := slices.IsSortedFunc(meld.Tiles, tile.TileID.Compare)
		if repacked != packed || err != nil || !sorted {
			t.Fatalf("PackMeld(UnpackMeld(%d) = %v) = %d, %v", packed, meld, repacked, err)
		}
	}
}

func TestUnpackMeld_WhenThePackedValueIsOutOfRange_ShouldRefuseWithAnInvalidMeldError(t *testing.T) {
	for _, packed := range []int{-1, meldIndexCount * tile.SeatCount} {
		_, err := UnpackMeld(packed)
		if _, isType := errors.AsType[InvalidMeldError](err); !isType {
			t.Errorf("UnpackMeld(%d) = %v, want an InvalidMeldError", packed, err)
		}
	}
}

func TestPackMeld_WhenTheMeldIsNoMeldOfItsKind_ShouldRefuseWithAnInvalidMeldError(t *testing.T) {
	ponWithAdded := calledMeld(t, play.MeldPon, 0, 2, 108, 108, 109, 110)
	ponWithAdded.Added = play.Some(tileIDOf(t, 111))
	chiFromNobody := calledMeld(t, play.MeldChi, 2, 1, 0, 0, 4, 8)
	chiFromNobody.From = play.Option[tile.Seat]{}
	chiCallingNothing := calledMeld(t, play.MeldChi, 2, 1, 0, 0, 4, 8)
	chiCallingNothing.Called = play.Option[tile.TileID]{}
	ponFromNobody := calledMeld(t, play.MeldPon, 0, 2, 108, 108, 109, 110)
	ponFromNobody.From = play.Option[tile.Seat]{}
	addedKan := func(added int) Meld {
		m := calledMeld(t, play.MeldAddedKan, 0, 3, 133, 132, 133, 134, 135)
		m.Added = play.Some(tileIDOf(t, added))
		return m
	}
	addedKanOfThree := addedKan(134)
	addedKanOfThree.Tiles = tileIDs(t, 132, 133, 134)
	addedKanWithoutAdded := addedKan(134)
	addedKanWithoutAdded.Added = play.Option[tile.TileID]{}
	openKanCallingNothing := calledMeld(t, play.MeldOpenKan, 3, 1, 124, 124, 125, 126, 127)
	openKanCallingNothing.Called = play.Option[tile.TileID]{}
	openKanFromNobody := calledMeld(t, play.MeldOpenKan, 3, 1, 124, 124, 125, 126, 127)
	openKanFromNobody.From = play.Option[tile.Seat]{}
	closedKan := func() Meld {
		return Meld{Caller: seatOf(t, 1), Kind: play.MeldClosedKan, Tiles: tileIDs(t, 52, 53, 54, 55)}
	}
	closedKanOfThree := closedKan()
	closedKanOfThree.Tiles = tileIDs(t, 52, 53, 54)
	closedKanCalling := closedKan()
	closedKanCalling.Called = play.Some(tileIDOf(t, 52))
	closedKanFromSeat := closedKan()
	closedKanFromSeat.From = play.Some(seatOf(t, 0))
	unknownKind := closedKan()
	unknownKind.Kind = play.MeldKind(9)

	tests := []struct {
		name string
		meld Meld
	}{
		{"pon with an added tile", ponWithAdded},
		{"chi of two tiles", calledMeld(t, play.MeldChi, 2, 1, 0, 0, 4)},
		{"chi of honors", calledMeld(t, play.MeldChi, 2, 1, 108, 108, 112, 116)},
		{"chi across suits", calledMeld(t, play.MeldChi, 2, 1, 28, 28, 32, 36)},
		{"chi out of row", calledMeld(t, play.MeldChi, 2, 1, 0, 0, 4, 12)},
		{"chi from the toimen", calledMeld(t, play.MeldChi, 2, 0, 0, 0, 4, 8)},
		{"chi from nobody", chiFromNobody},
		{"chi calling nothing", chiCallingNothing},
		{"chi calling a tile it lacks", calledMeld(t, play.MeldChi, 2, 1, 1, 0, 4, 8)},
		{"pon of two kinds", calledMeld(t, play.MeldPon, 0, 2, 108, 108, 109, 112)},
		{"pon of one tile twice", calledMeld(t, play.MeldPon, 0, 2, 108, 108, 108, 109)},
		{"pon calling a tile it lacks", calledMeld(t, play.MeldPon, 0, 2, 111, 108, 109, 110)},
		{"pon of its own discard", calledMeld(t, play.MeldPon, 0, 0, 108, 108, 109, 110)},
		{"pon from nobody", ponFromNobody},
		{"added kan of three tiles", addedKanOfThree},
		{"added kan without its added tile", addedKanWithoutAdded},
		{"added kan adding a tile it lacks", addedKan(0)},
		{"added kan adding its called tile", addedKan(133)},
		{"open kan of three tiles", calledMeld(t, play.MeldOpenKan, 3, 1, 124, 124, 125, 126)},
		{"open kan calling nothing", openKanCallingNothing},
		{"open kan from nobody", openKanFromNobody},
		{"closed kan of three tiles", closedKanOfThree},
		{"closed kan calling a tile", closedKanCalling},
		{"closed kan from a seat", closedKanFromSeat},
		{"unknown kind", unknownKind},
	}
	for _, tc := range tests {
		packed, err := PackMeld(tc.meld)
		meldErr, isType := errors.AsType[InvalidMeldError](err)
		if !isType || meldErr.Error() == "" {
			t.Errorf("PackMeld(%s) = %d, %v; want an InvalidMeldError", tc.name, packed, err)
		}
	}
}
