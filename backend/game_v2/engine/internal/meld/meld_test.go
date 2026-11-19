package meld_test

import (
	"errors"
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func tiles(t *testing.T, mpsz string) []tile.Tile {
	t.Helper()
	parsed, err := tile.ParseTiles(mpsz)
	if err != nil {
		t.Fatalf("ParseTiles(%q) error = %v", mpsz, err)
	}
	return parsed
}

func three(t *testing.T, mpsz string) [3]tile.Tile {
	t.Helper()
	parsed := tiles(t, mpsz)
	if len(parsed) != 3 {
		t.Fatalf("%q holds %d tiles, want 3", mpsz, len(parsed))
	}
	return [3]tile.Tile(parsed)
}

func four(t *testing.T, mpsz string) [4]tile.Tile {
	t.Helper()
	parsed := tiles(t, mpsz)
	if len(parsed) != 4 {
		t.Fatalf("%q holds %d tiles, want 4", mpsz, len(parsed))
	}
	return [4]tile.Tile(parsed)
}

func fitted(t *testing.T, m meld.Meld, err error) meld.Meld {
	t.Helper()
	if err != nil {
		t.Fatalf("meld error = %v", err)
	}
	return m
}

func chi(t *testing.T, mpsz string) meld.Meld {
	t.Helper()
	m, err := meld.NewChi(three(t, mpsz))
	return fitted(t, m, err)
}

func pon(t *testing.T, mpsz string) meld.Meld {
	t.Helper()
	m, err := meld.NewPon(three(t, mpsz))
	return fitted(t, m, err)
}

func openKan(t *testing.T, mpsz string) meld.Meld {
	t.Helper()
	m, err := meld.NewOpenKan(four(t, mpsz))
	return fitted(t, m, err)
}

func closedKan(t *testing.T, mpsz string) meld.Meld {
	t.Helper()
	m, err := meld.NewClosedKan(four(t, mpsz))
	return fitted(t, m, err)
}

func TestNewChi_ShouldSortItsTiles(t *testing.T) {
	for _, mpsz := range []string{"123m", "321m", "213m", "132m", "312m", "231m"} {
		sorted := chi(t, mpsz)
		if got := sorted.Tiles(); !slices.Equal(got, tiles(t, "123m")) || sorted.FirstKind() != 0 {
			t.Errorf("chi of %s = %v from kind %d, want 123m from kind 0", mpsz, got, sorted.FirstKind())
		}
	}
}

func TestNewChi_ShouldTakeEverySequenceOfEachSuit(t *testing.T) {
	for _, mpsz := range []string{"123m", "789m", "456p", "123s", "789s"} {
		if got := chi(t, mpsz).Tiles(); !slices.Equal(got, tiles(t, mpsz)) {
			t.Errorf("chi of %s = %v", mpsz, got)
		}
	}
}

func TestNewChi_WhenTilesAreNotASequenceOfOneSuit_ShouldRefuse(t *testing.T) {
	for _, mpsz := range []string{"89m1p", "9m12p", "9s12z", "123z", "567z", "891m", "112m", "135m", "111m", "12m3p"} {
		if _, err := meld.NewChi(three(t, mpsz)); !errors.Is(err, meld.NotASequenceError{}) {
			t.Errorf("NewChi(%s) error = %v, want not a sequence", mpsz, err)
		}
	}
}

func TestNewPonAndKans_WhenTilesAreOfMixedKinds_ShouldRefuse(t *testing.T) {
	for _, mpsz := range []string{"112m", "123m", "1m1p1s", "556z"} {
		if _, err := meld.NewPon(three(t, mpsz)); !errors.Is(err, meld.NotOneKindError{}) {
			t.Errorf("NewPon(%s) error = %v, want not one kind", mpsz, err)
		}
	}
	for _, mpsz := range []string{"1112m", "1222m", "111z1m"} {
		if _, err := meld.NewOpenKan(four(t, mpsz)); !errors.Is(err, meld.NotOneKindError{}) {
			t.Errorf("NewOpenKan(%s) error = %v, want not one kind", mpsz, err)
		}
		if _, err := meld.NewClosedKan(four(t, mpsz)); !errors.Is(err, meld.NotOneKindError{}) {
			t.Errorf("NewClosedKan(%s) error = %v, want not one kind", mpsz, err)
		}
	}
}

func TestNewPonAndKans_ShouldKeepTheTilesInTheOrderGiven(t *testing.T) {
	for _, c := range []struct {
		meld meld.Meld
		want string
	}{
		{pon(t, "505p"), "505p"},
		{openKan(t, "5505s"), "5505s"},
		{closedKan(t, "0555m"), "0555m"},
	} {
		if got := c.meld.Tiles(); !slices.Equal(got, tiles(t, c.want)) {
			t.Errorf("%v tiles = %v, want %s in that order", c.meld, got, c.want)
		}
	}
}

func TestMelds_WhenTilesHoldRedFives_ShouldFitTheirKind(t *testing.T) {
	if got := chi(t, "640m").Tiles(); !slices.Equal(got, tiles(t, "406m")) || !got[1].IsRed() {
		t.Errorf("chi of 640m = %v, want 406m with the red five in the middle", got)
	}
	for _, c := range []struct {
		meld meld.Meld
		want string
	}{
		{pon(t, "055p"), "055p"},
		{openKan(t, "0555s"), "0555s"},
		{closedKan(t, "5550s"), "5550s"},
	} {
		if got := c.meld.Tiles(); !slices.Equal(got, tiles(t, c.want)) {
			t.Errorf("%v tiles = %v, want %s", c.meld, got, c.want)
		}
	}
}

func TestMeld_ShouldReportItsKindTileCountAndOpenness(t *testing.T) {
	for _, c := range []struct {
		meld      meld.Meld
		kind      meld.Kind
		tileCount int
		isOpen    bool
		isKan     bool
	}{
		{chi(t, "123m"), meld.Chi, 3, true, false},
		{pon(t, "555z"), meld.Pon, 3, true, false},
		{openKan(t, "1111m"), meld.OpenKan, 4, true, true},
		{closedKan(t, "1111m"), meld.ClosedKan, 4, false, true},
	} {
		m := c.meld
		if m.Kind() != c.kind || len(m.Tiles()) != c.tileCount || m.IsOpen() != c.isOpen || m.IsKan() != c.isKan {
			t.Errorf("%v: kind %v, %d tiles, open %v, kan %v; want %v, %d, %v, %v",
				m, m.Kind(), len(m.Tiles()), m.IsOpen(), m.IsKan(), c.kind, c.tileCount, c.isOpen, c.isKan)
		}
	}
}

func TestMeldTiles_WhenTheCallerWritesToThem_ShouldLeaveTheMeldUnchanged(t *testing.T) {
	kan := closedKan(t, "1111z")
	kan.Tiles()[0] = tiles(t, "9m")[0]
	if got := kan.String(); got != "closed kan 1111z" {
		t.Errorf("meld after writing its tiles = %q, want closed kan 1111z", got)
	}
}

func TestMeldString_ShouldNameTheKindAndTheTiles(t *testing.T) {
	for _, c := range []struct {
		meld meld.Meld
		want string
	}{
		{chi(t, "640m"), "chi 406m"},
		{chi(t, "987s"), "chi 789s"},
		{pon(t, "505p"), "pon 055p"},
		{openKan(t, "2222m"), "open kan 2222m"},
		{closedKan(t, "1111z"), "closed kan 1111z"},
	} {
		if got := c.meld.String(); got != c.want {
			t.Errorf("String = %q, want %q", got, c.want)
		}
	}
}

func TestKindString_WhenKindIsUnknown_ShouldNameItsNumber(t *testing.T) {
	if got, want := meld.Kind(9).String(), "meld.Kind(9)"; got != want {
		t.Errorf("String = %q, want %q", got, want)
	}
}

func TestMeldErrors_ShouldDescribeTheMisfit(t *testing.T) {
	for _, c := range []struct {
		err  error
		want string
	}{
		{meld.NotASequenceError{}, "a chi needs three consecutive tiles of one suit"},
		{meld.NotOneKindError{}, "a pon or kan needs tiles of one kind"},
	} {
		if got := c.err.Error(); got != c.want {
			t.Errorf("%#v message = %q, want %q", c.err, got, c.want)
		}
	}
}
