package game_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/wall"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestHaitei_WhenTheTsumoIsOnTheLastTile_ShouldAwardHaiteiNotHoutei(t *testing.T) {
	lastEast := tileOf(t, 1, "1z")
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			copies(t, 1, "123456789s2345z"),
			copies(t, 0, "123456789m444p1z"),
			copies(t, 2, "123456789s2345z"),
			copies(t, 3, "123456789s2345z"),
		},
		Rinshan: copies(t, 2, "11z"),
		Dora:    play.Some(tileOf(t, 3, "9p")),
		Ura:     []tile.TileID{tileOf(t, 3, "7z")},
	}
	var fillers []tile.TileID
	for _, free := range w.UnplacedTiles() {
		if free != lastEast && len(fillers) < wall.LiveTilesAtDeal-1 {
			fillers = append(fillers, free)
		}
	}
	w.Draws = slices.Concat(fillers, []tile.TileID{lastEast})
	g := playDefaultsWhileLiveTilesExceed(t, begun(t, w, noStart()), 0)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 1)))
	if hand := g.Hand(seat(t, 1)); hand[len(hand)-1] != lastEast {
		t.Fatalf("last drawn tile = %v, want the last East", hand[len(hand)-1])
	}

	_, events := script(t, g, act(seat(t, 1), play.TsumoAction()))

	win := firstWin(t, events)
	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuTsumo, play.YakuHaitei, play.YakuIttsu})
	assertEqual(t, "aka dora", win.Dora.AkaDora, 1)
}
