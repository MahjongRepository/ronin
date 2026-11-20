package play_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestVisibility_WhenToAll_ShouldIncludeEverySeat(t *testing.T) {
	everyone := play.ToAll()

	if !everyone.All() {
		t.Error("All = false")
	}
	if _, single := everyone.Seat(); single {
		t.Error("Seat reports a single seat")
	}
	for _, s := range tile.Seats() {
		if !everyone.Includes(s) {
			t.Errorf("Includes(%d) = false", s.Index())
		}
	}
}

func TestVisibility_WhenZero_ShouldIncludeNoSeat(t *testing.T) {
	var unset play.Visibility

	if unset.All() {
		t.Error("All = true")
	}
	if _, single := unset.Seat(); single {
		t.Error("Seat reports a single seat")
	}
	for _, s := range tile.Seats() {
		if unset.Includes(s) {
			t.Errorf("Includes(%d) = true", s.Index())
		}
	}
}

func TestVisibility_WhenToSeat_ShouldIncludeOnlyThatSeat(t *testing.T) {
	only := play.ToSeat(seat(t, 2))

	if got, single := only.Seat(); !single || got != seat(t, 2) {
		t.Errorf("Seat = %d, %t, want 2, true", got.Index(), single)
	}
	if only.All() {
		t.Error("All = true")
	}
	var included []int
	for _, s := range tile.Seats() {
		if only.Includes(s) {
			included = append(included, s.Index())
		}
	}
	if !slices.Equal(included, []int{2}) {
		t.Errorf("included seats = %v, want [2]", included)
	}
}

func meldView(t *testing.T, kind play.MeldKind, tiles []tile.TileID, called play.Option[tile.TileID]) play.MeldView {
	t.Helper()
	sorted := slices.Clone(tiles)
	slices.SortFunc(sorted, tile.TileID.Compare)
	from := play.Option[tile.Seat]{}
	if called.OK {
		from = play.Some(seat(t, 3))
	}
	return play.MeldView{Kind: kind, Tiles: sorted, Called: called, From: from}
}

func TestMeldViewCall_ShouldHoldTheMeldTilesButTheCalledOne(t *testing.T) {
	chi := meldView(t, play.MeldChi, copies(t, 0, "345m"), play.Some(copyOf(t, 0, "4m")))
	if got, ok := chi.Call(); !ok || got != (play.ChiCall{Held: [2]tile.TileID{copyOf(t, 0, "3m"), copyOf(t, 0, "5m")}}) {
		t.Errorf("chi Call = %v, %t", got, ok)
	}

	pon := meldView(t, play.MeldPon, []tile.TileID{copyOf(t, 0, "7z"), copyOf(t, 1, "7z"), copyOf(t, 2, "7z")},
		play.Some(copyOf(t, 1, "7z")))
	if got, ok := pon.Call(); !ok || got != (play.PonCall{Held: [2]tile.TileID{copyOf(t, 0, "7z"), copyOf(t, 2, "7z")}}) {
		t.Errorf("pon Call = %v, %t", got, ok)
	}

	openKan := meldView(t, play.MeldOpenKan, copies(t, 0, "1111p"), play.Some(copyOf(t, 3, "1p")))
	if got, ok := openKan.Call(); !ok || got != (play.OpenKanCall{}) {
		t.Errorf("open kan Call = %v, %t", got, ok)
	}

	for _, kind := range []play.MeldKind{play.MeldAddedKan, play.MeldClosedKan} {
		kan := openKan
		kan.Kind = kind
		if got, ok := kan.Call(); ok {
			t.Errorf("kind %d Call = %v, want none", kind, got)
		}
	}

	uncalled := meldView(t, play.MeldChi, copies(t, 0, "345m"), play.Option[tile.TileID]{})
	if got, ok := uncalled.Call(); ok {
		t.Errorf("uncalled Call = %v, want none", got)
	}
	calledElsewhere := meldView(t, play.MeldChi, copies(t, 0, "345m"), play.Some(copyOf(t, 1, "4m")))
	if got, ok := calledElsewhere.Call(); ok {
		t.Errorf("called elsewhere Call = %v, want none", got)
	}
	calledWithOneMore := meldView(t, play.MeldPon, copies(t, 0, "77z"), play.Some(copyOf(t, 0, "7z")))
	if got, ok := calledWithOneMore.Call(); ok {
		t.Errorf("two-tile pon Call = %v, want none", got)
	}
}
