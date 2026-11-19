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
		{"plain river", play.PublicSeat{River: []play.RiverTile{plain}}, false},
		{"riichi discard", play.PublicSeat{River: []play.RiverTile{plain, declaring}}, true},
		{"riichi standing", play.PublicSeat{River: []play.RiverTile{plain, declaring}, Riichi: standing}, true},
		{"riichi without a river", play.PublicSeat{Riichi: standing}, true},
	} {
		if got := c.public.DeclaredRiichi(); got != c.want {
			t.Errorf("%s DeclaredRiichi = %t, want %t", c.name, got, c.want)
		}
	}
}
