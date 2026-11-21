package session_test

import (
	"slices"
	"testing"
	"testing/synctest"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func threeDragonCopiesWall(t *testing.T) [tile.TileIDCount]tile.TileID {
	t.Helper()
	return fixedWall(t, [tile.SeatCount][]tile.TileID{
		junkHand(t, 2),
		junkHand(t, 0),
		copies(t, 1, "1357m2468p9s555z6z"),
		junkHand(t, 3),
	}, copies(t, 0, "5z"))
}

func TestPick_WhenASeatPonsAndThenTimesOut_ShouldPlayPickedCopiesAndAPickedDiscard(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		middle := func(c *session.Config) { c.Pick = func(n int) int { return n / 2 } }
		h := newHarness(t, withSeed(seedSeating(t, 0, 1, 2)), withWalls(threeDragonCopiesWall(t)), middle,
			withTiming(func(timing *session.Timing) {
				noWaits(timing)
				timing.BaseTurn = time.Second
			}))
		conns := h.start("Alice", "Bob", "Carol")
		alice, carol := conns[0], conns[2]
		draw := lastDraw(t, alice)
		h.act(alice, discard(intOf(t, draw, wire.KeyWaitID), drawnTile(t, draw)))
		held := copies(t, 1, "555z6z")

		h.act(carol, messaging.GameActionMessage{
			Action: messaging.GameActionPon,
			WaitID: intOf(t, callPrompt(t, carol), wire.KeyWaitID),
			Play:   play.Some(play.PonAction([2]tile.TileID{held[0], held[1]})),
		})
		sleep(time.Minute)

		melds := ofEvent(alice.messages(), wire.EventMeld)
		if len(melds) != 1 {
			t.Fatalf("melds alice saw = %d, want carol's pon", len(melds))
		}
		meld, err := wire.UnpackMeld(intOf(t, melds[0], wire.KeyPackedMeld))
		if err != nil || slices.Contains(meld.Tiles, held[0]) || !slices.Contains(meld.Tiles, held[2]) {
			t.Errorf("pon tiles = %v (%v), want the picked copies %d and %d, not the named %d",
				meld.Tiles, err, held[1].Index(), held[2].Index(), held[0].Index())
		}
		discards := ofEvent(alice.messages(), wire.EventDiscard)
		if len(discards) < 2 {
			t.Fatalf("discards alice saw = %d, want carol's timed out one after her own", len(discards))
		}
		move, err := wire.UnpackDiscard(intOf(t, discards[1], wire.KeyPackedMove))
		if want := copies(t, 1, "4p")[0]; err != nil || move.Tile != want {
			t.Errorf("timeout discard after the pon = %+v (%v), want the picked tile %d, not the last in hand order %d",
				move, err, want.Index(), held[3].Index())
		}
	})
}
