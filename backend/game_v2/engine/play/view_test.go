package play_test

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
)

func TestPublicSeatDeclaredRiichi_ShouldHoldFromTheRiichiDiscardBeforeItStands(t *testing.T) {
	plain := play.RiverTile{Tile: copyOf(t, 0, "1z")}
	declaring := play.RiverTile{Tile: copyOf(t, 0, "2z"), Riichi: true}
	standing := play.Some(play.Riichi{Ippatsu: true})

	for _, c := range []struct {
		name   string
		public play.PublicSeat
		want   bool
	}{
		{name: "plain river", public: play.PublicSeat{River: []play.RiverTile{plain}}},
		{name: "riichi discard", public: play.PublicSeat{River: []play.RiverTile{plain, declaring}}, want: true},
		{name: "riichi standing", public: play.PublicSeat{River: []play.RiverTile{plain, declaring}, Riichi: standing}, want: true},
		{name: "riichi without a river", public: play.PublicSeat{Riichi: standing}, want: true},
	} {
		t.Run(c.name, func(t *testing.T) {
			if got := c.public.DeclaredRiichi(); got != c.want {
				t.Errorf("DeclaredRiichi = %t, want %t", got, c.want)
			}
		})
	}
}
