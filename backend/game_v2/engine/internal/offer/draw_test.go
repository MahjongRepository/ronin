package offer_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/offer"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestNagashiSeats_ShouldListTheSeatsWhoseDiscardsAreAllTerminalsOrHonorsAndUncalled(t *testing.T) {
	var rivers [tile.SeatCount][]play.RiverTile
	rivers[0] = river(copies(t, 0, "19m1z"))
	rivers[1] = river(copies(t, 0, "19p2z"))
	rivers[2] = river(copies(t, 0, "9s5m"))
	var melds [tile.SeatCount][]play.MeldView
	melds[3] = []play.MeldView{calledMeld(t, play.MeldPon, 1, "222z", seat(t, 1))}

	got := offer.NagashiSeats(rivers, melds)
	if want := []tile.Seat{seat(t, 0)}; !slices.Equal(got, want) {
		t.Errorf("NagashiSeats = %v, want %v", got, want)
	}
}
