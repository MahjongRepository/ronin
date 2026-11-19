package game_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func paoDealerGame(t *testing.T, dealer, draws, rinshan []tile.TileID) game.Game {
	t.Helper()
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			dealer, copies(t, 1, "123456789p1234s"), copies(t, 2, "123456789p1234s"), copies(t, 3, "123456789p1234s"),
		},
		Draws:   draws,
		Rinshan: rinshan,
	}
	return begun(t, w, noStart())
}

func ponAndDiscard(t *testing.T, g game.Game, discard tile.TileID) game.Game {
	t.Helper()
	g, _ = discardDrawn(t, g, 1)
	g, _ = script(t, g, act(seat(t, 0), firstPon(t, g, seat(t, 0))), act(seat(t, 0), play.DiscardAction(discard)))
	return g
}

func dragonDraws(t *testing.T, seatOneDraws []tile.TileID) []tile.TileID {
	t.Helper()
	return slices.Concat([]tile.TileID{tileOf(t, 0, "3z")}, seatOneDraws, copies(t, 0, "246m"),
		[]tile.TileID{tileOf(t, 1, "9s")})
}

func TestPao_WhenAnOpenKanCompletesTheThirdDragon_ShouldBeAnnouncedToAllRightAfterTheCall(t *testing.T) {
	dealer := slices.Concat(copies(t, 0, "5566777z"), copies(t, 0, "234p9s"), copies(t, 0, "12z"))
	draws := dragonDraws(t, []tile.TileID{tileOf(t, 2, "5z"), tileOf(t, 2, "6z"), tileOf(t, 3, "7z")})
	g, _ := discardDrawn(t, paoDealerGame(t, dealer, draws, []tile.TileID{tileOf(t, 3, "4z")}), 1)
	g = ponAndDiscard(t, g, tileOf(t, 0, "1z"))
	g = ponAndDiscard(t, g, tileOf(t, 0, "2z"))
	g, _ = discardDrawn(t, g, 1)

	_, events := script(t, g, act(seat(t, 0), play.KanAction(play.KanOpen, tileOf(t, 3, "7z"))))

	assertEqual(t, "kinds", testkit.EventKinds(events)[:2], []string{"called", "pao_assigned"})
	assertEqual(t, "pao", events[1], play.Emitted{To: play.ToAll(), Event: play.PaoAssigned{
		Seat: seat(t, 0), Liable: seat(t, 1),
	}})
}
