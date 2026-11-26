package tile_test

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestTilePredicates_ShouldFollowTheKind(t *testing.T) {
	names := kindNames()
	for _, mpsz := range append(names[:], "0m", "0p", "0s") {
		got := mustTile(t, mpsz)
		rank, suit := mpsz[0], mpsz[1]
		honor := suit == 'z'
		terminal := !honor && (rank == '1' || rank == '9')
		gotFlags := [6]bool{got.IsMan(), got.IsPin(), got.IsSou(), got.IsHonor(), got.IsTerminal(), got.IsTerminalOrHonor()}
		wantFlags := [6]bool{suit == 'm', suit == 'p', suit == 's', honor, terminal, terminal || honor}
		if gotFlags != wantFlags {
			t.Errorf("%s predicates = %v, want %v", mpsz, gotFlags, wantFlags)
		}
	}
}

func TestNewTile_ShouldTakeEveryKindAsAPlainTile(t *testing.T) {
	for kind := range tile.Kind(tile.KindCount) {
		got, ok := tile.NewTile(kind)
		if !ok || got.Kind() != kind || got.IsRed() {
			t.Errorf("NewTile(%d) = %v, %v; want plain kind %d", kind, got, ok, kind)
		}
	}
}

func TestNewTile_WhenKindIsPastTheLast_ShouldRefuse(t *testing.T) {
	for _, kind := range []tile.Kind{34, 35, 36, 37, 135, 255} {
		if _, ok := tile.NewTile(kind); ok {
			t.Errorf("NewTile(%d) accepted", kind)
		}
	}
}

func TestRedFive_ShouldTakeOnlyTheFivesOfASuit(t *testing.T) {
	for n := range 256 {
		kind := tile.Kind(n)
		got, ok := tile.RedFive(kind)
		isFive := kind == 4 || kind == 13 || kind == 22
		if ok != isFive {
			t.Errorf("RedFive(%d) ok = %v, want %v", kind, ok, isFive)
			continue
		}

		plain, _ := tile.NewTile(kind)
		if ok && (got.Kind() != kind || !got.IsRed() || got == plain) {
			t.Errorf("RedFive(%d) = %v, want the red five of kind %d", kind, got, kind)
		}
	}
}

func TestTileIDTile_WhenAkaDoraIsEnabled_ShouldReadIDs16And52And88AsTheRedFives(t *testing.T) {
	for _, id := range tile.AllTileIDs() {
		got := id.Tile(tile.AkaDoraEnabled)
		wantRed := id.Index() == 16 || id.Index() == 52 || id.Index() == 88
		if got.Kind() != tile.Kind(id.Index()/4) || got.IsRed() != wantRed {
			t.Errorf("TileID %d Tile = %v, want kind %d red %v", id.Index(), got, id.Index()/4, wantRed)
		}
	}

	if got := mustID(t, 52).Tile(tile.AkaDoraEnabled); got != redFive(t, 13) {
		t.Errorf("TileID 52 Tile = %v, want 0p", got)
	}
}

func TestTileIDTile_WhenAkaDoraIsDisabled_ShouldReadEveryFiveAsPlain(t *testing.T) {
	for _, id := range tile.AllTileIDs() {
		want, _ := tile.NewTile(id.Kind())
		if got := id.Tile(tile.AkaDoraDisabled); got != want {
			t.Errorf("TileID %d Tile = %v, want %v", id.Index(), got, want)
		}
	}
}

func TestTileString_ShouldBeMpsz(t *testing.T) {
	for kind, want := range kindNames() {
		if got := plainTiles(t, tile.Kind(kind))[0].String(); got != want {
			t.Errorf("kind %d String = %q, want %q", kind, got, want)
		}
	}

	for kind, want := range map[tile.Kind]string{4: "0m", 13: "0p", 22: "0s"} {
		if got := redFive(t, kind).String(); got != want {
			t.Errorf("red five %d String = %q, want %q", kind, got, want)
		}
	}
}

func TestTileCompare_ShouldOrderByKindWithTheRedFiveFirst(t *testing.T) {
	for _, c := range []struct {
		a, b string
		want int
	}{
		{"4p", "0p", -1},
		{"0p", "5p", -1},
		{"5p", "0p", 1},
		{"0p", "0p", 0},
		{"5p", "5p", 0},
		{"6p", "5p", 1},
		{"9m", "1p", -1},
		{"1z", "0s", 1},
	} {
		t.Run(c.a+" vs "+c.b, func(t *testing.T) {
			if got := mustTile(t, c.a).Compare(mustTile(t, c.b)); got != c.want {
				t.Errorf("%s.Compare(%s) = %d, want %d", c.a, c.b, got, c.want)
			}
		})
	}
}
