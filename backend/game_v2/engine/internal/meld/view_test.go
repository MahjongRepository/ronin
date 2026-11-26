package meld_test

import (
	"errors"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func ids(t *testing.T, first int, mpsz string) []tile.TileID {
	t.Helper()
	var seen [tile.KindCount]int
	parsed := tiles(t, mpsz)
	out := make([]tile.TileID, 0, len(parsed))
	for _, parsedTile := range parsed {
		kind := parsedTile.Kind()
		id, ok := tile.NewTileID(int(kind)*tile.CopiesPerKind + first + seen[kind])
		if !ok {
			t.Fatalf("%q repeats a kind past its copies", mpsz)
		}

		out = append(out, id)
		seen[kind]++
	}

	return out
}

func view(t *testing.T, kind play.MeldKind, mpsz string) play.MeldView {
	t.Helper()
	tileIDs := ids(t, 0, mpsz)
	if kind == play.MeldClosedKan {
		return play.MeldView{Kind: kind, Tiles: tileIDs}
	}

	from, ok := tile.NewSeat(3)
	if !ok {
		t.Fatal("NewSeat(3) refused")
	}

	return play.MeldView{Kind: kind, Tiles: tileIDs, Called: play.Some(tileIDs[0]), From: play.Some(from)}
}

func TestFromView_WhenTheTilesFitTheKind_ShouldReadRedFivesAndScoreAnAddedKanAsOpen(t *testing.T) {
	for _, c := range []struct {
		name string
		view play.MeldView
		want meld.Meld
	}{
		{"chi", view(t, play.MeldChi, "345m"), chi(t, "340m")},
		{"pon", view(t, play.MeldPon, "555z"), pon(t, "555z")},
		{"open kan", view(t, play.MeldOpenKan, "2222s"), openKan(t, "2222s")},
		{"added kan", view(t, play.MeldAddedKan, "1111p"), openKan(t, "1111p")},
		{"closed kan", view(t, play.MeldClosedKan, "9999s"), closedKan(t, "9999s")},
	} {
		t.Run(c.name, func(t *testing.T) {
			got, ok := meld.FromView(c.view)
			if !ok || got != c.want {
				t.Errorf("FromView(%v) = %v, %t, want %v", c.view, got, ok, c.want)
			}
		})
	}
}

func TestFromView_WhenTheTilesDoNotFitTheKind_ShouldRefuse(t *testing.T) {
	for _, c := range []struct {
		name string
		view play.MeldView
	}{
		{"gapped chi", view(t, play.MeldChi, "357m")},
		{"two-tile pon", view(t, play.MeldPon, "55z")},
		{"empty pon", play.MeldView{Kind: play.MeldPon}},
		{"three-tile kan", view(t, play.MeldOpenKan, "111p")},
		{"mixed closed kan", view(t, play.MeldClosedKan, "1112p")},
		{"five tiles", view(t, play.MeldAddedKan, "11112p")},
		{"unknown kind", play.MeldView{Kind: play.MeldKind(9), Tiles: ids(t, 0, "1111p")}},
	} {
		t.Run(c.name, func(t *testing.T) {
			if got, ok := meld.FromView(c.view); ok {
				t.Errorf("FromView = %v, want refused", got)
			}
		})
	}
}

func TestCheckHandInput_WhenHandAndMeldsAreSound_ShouldPass(t *testing.T) {
	hand := ids(t, 0, "123m456p")
	melds := []play.MeldView{view(t, play.MeldPon, "555z"), view(t, play.MeldClosedKan, "9999s")}

	if err := meld.CheckHandInput(hand, melds); err != nil {
		t.Errorf("CheckHandInput error = %v", err)
	}
}

func TestCheckHandInput_WhenAMeldIsMisfitAndATileDuplicated_ShouldReportTheMisfitFirst(t *testing.T) {
	melds := []play.MeldView{view(t, play.MeldClosedKan, "9999m"), {Kind: play.MeldPon}}
	duplicated := ids(t, 0, "1m")[0]

	err := meld.CheckHandInput([]tile.TileID{duplicated, duplicated}, melds)
	if !errors.Is(err, meld.MisfitMeldError{Index: 1}) {
		t.Errorf("CheckHandInput error = %v, want MisfitMeldError{Index: 1}", err)
	}
}

func TestCheckHandInput_WhenAHandTileIsAlsoMelded_ShouldReportTheDuplicate(t *testing.T) {
	hand := append(ids(t, 0, "1111m"), ids(t, 2, "5p")...)
	melds := []play.MeldView{view(t, play.MeldPon, "555p")}

	err := meld.CheckHandInput(hand, melds)
	if !errors.Is(err, meld.DuplicateTileError{Tile: ids(t, 2, "5p")[0]}) {
		t.Errorf("CheckHandInput error = %v, want the duplicate 5p copy 2", err)
	}
}

func TestCheckHandInput_WhenOneIDIsHeldFiveTimes_ShouldReportTheDuplicate(t *testing.T) {
	first := ids(t, 0, "1m")[0]

	err := meld.CheckHandInput([]tile.TileID{first, first, first, first, first}, nil)
	if !errors.Is(err, meld.DuplicateTileError{Tile: first}) {
		t.Errorf("CheckHandInput error = %v, want the duplicate 1m", err)
	}
}
