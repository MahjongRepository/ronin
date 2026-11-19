package tile_test

import (
	"errors"
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestNotationErrors_ShouldDescribeTheInput(t *testing.T) {
	for _, c := range []struct {
		err  error
		want string
	}{
		{tile.InvalidCharacterError{Character: 'x'}, "'x' is not a tile rank"},
		{tile.TileOutOfRangeError{Character: '8'}, "rank '8' gives a tile past the last tile"},
		{tile.MissingSuitError{}, "the last ranks have no suit letter"},
		{tile.NotOneTileError{Count: 2}, "the string holds 2 tiles, not exactly one"},
	} {
		if got := c.err.Error(); got != c.want {
			t.Errorf("%#v message = %q, want %q", c.err, got, c.want)
		}
	}
}

func TestParseTiles_ShouldKeepTheOrderWritten(t *testing.T) {
	for _, c := range []struct {
		mpsz string
		want []tile.Kind
	}{
		{"31m9p1s72z", []tile.Kind{2, 0, 17, 18, 33, 28}},
		{"1m2m3m", []tile.Kind{0, 1, 2}},
		{"", nil},
	} {
		if got, want := mustTiles(t, c.mpsz), plainTiles(t, c.want...); !slices.Equal(got, want) {
			t.Errorf("ParseTiles(%q) = %v, want %v", c.mpsz, got, want)
		}
	}
}

func TestParseTiles_ShouldReadEveryKind(t *testing.T) {
	var kinds []tile.Kind
	for kind := range tile.Kind(tile.KindCount) {
		kinds = append(kinds, kind)
	}
	got := mustTiles(t, "123456789m123456789p123456789s1234567z")
	if want := plainTiles(t, kinds...); !slices.Equal(got, want) {
		t.Errorf("ParseTiles = %v, want %v", got, want)
	}
}

func TestParseTiles_WhenRankIsZeroOrR_ShouldReadTheRedFive(t *testing.T) {
	redFives := []tile.Tile{redFive(t, 4), redFive(t, 13), redFive(t, 22)}
	for _, mpsz := range []string{"0m0p0s", "rmrprs"} {
		if got := mustTiles(t, mpsz); !slices.Equal(got, redFives) {
			t.Errorf("ParseTiles(%q) = %v, want %v", mpsz, got, redFives)
		}
	}
	five := plainTiles(t, 4)[0]
	want := []tile.Tile{five, redFive(t, 4), redFive(t, 4), five}
	if got := mustTiles(t, "50r5m"); !slices.Equal(got, want) {
		t.Errorf("ParseTiles(50r5m) = %v, want %v", got, want)
	}
}

func TestParseTiles_WhenSuitIsH_ShouldReadHonors(t *testing.T) {
	if got, want := mustTiles(t, "1234567h"), mustTiles(t, "1234567z"); !slices.Equal(got, want) {
		t.Errorf("ParseTiles(1234567h) = %v, want %v", got, want)
	}
}

func TestParseTiles_ShouldTakeAnyNumberOfCopies(t *testing.T) {
	if got, want := mustTiles(t, "11111m"), plainTiles(t, 0, 0, 0, 0, 0); !slices.Equal(got, want) {
		t.Errorf("ParseTiles(11111m) = %v, want %v", got, want)
	}
}

func TestParseTiles_WhenInputIsMalformed_ShouldNameTheError(t *testing.T) {
	for _, c := range []struct {
		mpsz string
		want error
	}{
		{"0z", tile.InvalidCharacterError{Character: '0'}},
		{"r7z", tile.InvalidCharacterError{Character: 'r'}},
		{"0h", tile.InvalidCharacterError{Character: '0'}},
		{"1x2m", tile.InvalidCharacterError{Character: 'x'}},
		{"1 2m", tile.InvalidCharacterError{Character: ' '}},
		{"x", tile.InvalidCharacterError{Character: 'x'}},
		{"123mx", tile.InvalidCharacterError{Character: 'x'}},
		{"12x", tile.InvalidCharacterError{Character: 'x'}},
		{"1é2m", tile.InvalidCharacterError{Character: 'é'}},
		{"8z", tile.TileOutOfRangeError{Character: '8'}},
		{"19z", tile.TileOutOfRangeError{Character: '9'}},
		{"8h", tile.TileOutOfRangeError{Character: '8'}},
		{"12", tile.MissingSuitError{}},
		{"123m4", tile.MissingSuitError{}},
		{"1m0", tile.MissingSuitError{}},
	} {
		if _, err := tile.ParseTiles(c.mpsz); !errors.Is(err, c.want) {
			t.Errorf("ParseTiles(%q) error = %v, want %v", c.mpsz, err, c.want)
		}
	}
}

func TestTilesString_ShouldSortAndGroupBySuit(t *testing.T) {
	for _, c := range []struct{ mpsz, want string }{
		{"1z9s5p1m", "1m5p9s1z"},
		{"321m", "123m"},
		{"7z1z", "17z"},
		{"5m0m5m", "055m"},
		{"55p0p", "055p"},
		{"406s", "406s"},
		{"123456789m123456789p123456789s1234567z", "123456789m123456789p123456789s1234567z"},
		{"", ""},
	} {
		if got := tile.TilesString(mustTiles(t, c.mpsz)); got != c.want {
			t.Errorf("TilesString(%q) = %q, want %q", c.mpsz, got, c.want)
		}
	}
}

func TestTilesString_WhenTilesAreRedFives_ShouldRoundTrip(t *testing.T) {
	tiles := mustTiles(t, "0m0p0s")
	written := tile.TilesString(tiles)
	if written != "0m0p0s" || !slices.Equal(mustTiles(t, written), tiles) {
		t.Errorf("TilesString = %q, want 0m0p0s parsing back to %v", written, tiles)
	}
}

func TestParseTile_ShouldTakeExactlyOneTile(t *testing.T) {
	if got, err := tile.ParseTile("0p"); err != nil || got != redFive(t, 13) {
		t.Errorf("ParseTile(0p) = %v, %v; want the red five of pin", got, err)
	}
	for _, c := range []struct {
		mpsz string
		want error
	}{
		{"", tile.NotOneTileError{Count: 0}},
		{"12m", tile.NotOneTileError{Count: 2}},
		{"x", tile.InvalidCharacterError{Character: 'x'}},
	} {
		if _, err := tile.ParseTile(c.mpsz); !errors.Is(err, c.want) {
			t.Errorf("ParseTile(%q) error = %v, want %v", c.mpsz, err, c.want)
		}
	}
}
