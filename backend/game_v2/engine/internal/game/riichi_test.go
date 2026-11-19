package game_test

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func dealerAfterDraw(t *testing.T, dealer, draws []tile.TileID) game.Game {
	t.Helper()
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{dealer, souWithWinds(t, 1), souWithWinds(t, 2), souWithWinds(t, 3)},
		Draws: draws,
	}
	return begun(t, w, noStart())
}

func tenpaiDealerAfterDraw(t *testing.T) game.Game {
	t.Helper()
	return dealerAfterDraw(t, copies(t, 0, "1123456788899m"), []tile.TileID{tileOf(t, 0, "7z")})
}

func TestRiichiDiscard_WhenTheDiscardBreaksTenpai_ShouldBeRefusedByRuleAndChangeNothing(t *testing.T) {
	assertRefused(t, tenpaiDealerAfterDraw(t), seat(t, 0), play.RiichiAction(tileOf(t, 0, "3m")),
		refusal(play.RefusalRule, play.CodeRiichiBreaksTenpai))
}

func TestRiichi_WhenRiichiIsNotOffered_ShouldBeNotOffered(t *testing.T) {
	g := dealerAfterDraw(t, copies(t, 0, "13579m2468p1357s"), []tile.TileID{tileOf(t, 0, "7z")})

	assertRefused(t, g, seat(t, 0), play.RiichiAction(tileOf(t, 0, "7z")), notOfferedRefusal())
}

func TestRiichi_WhenTheHandIsTenpaiAndTheTileIsNotHeld_ShouldBeNotOffered(t *testing.T) {
	g := tenpaiDealerAfterDraw(t)

	assertRefused(t, g, seat(t, 0), play.RiichiAction(g.Hand(seat(t, 1))[0]),
		refusal(play.RefusalNotOffered, play.CodeTileNotHeld))
}

func TestDiscard_WhenRiichiForbidsTheTile_ShouldBeRefusedByRuleAndChangeNothing(t *testing.T) {
	draws := []tile.TileID{tileOf(t, 0, "7z"), tileOf(t, 0, "5z"), tileOf(t, 0, "6z"), tileOf(t, 1, "7z"), tileOf(t, 1, "5z")}
	g, _ := script(t, dealerAfterDraw(t, copies(t, 0, "1123456788899m"), draws), act(seat(t, 0), play.RiichiAction(tileOf(t, 0, "7z"))))
	g, _ = discardDrawn(t, g, 3)

	assertRefused(t, g, seat(t, 0), play.DiscardAction(g.Hand(seat(t, 0))[0]),
		refusal(play.RefusalRule, play.CodeRiichiDrawnTileOnly))
}
