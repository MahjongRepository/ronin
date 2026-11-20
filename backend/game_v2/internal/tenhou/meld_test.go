package tenhou

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

type capturedMeld struct {
	code   int
	from   int
	called int
	held   [2]int
}

var capturedTenhouMelds = []capturedMeld{
	{46207, 3, 79, [2]int{83, 84}},
	{56519, 3, 94, [2]int{88, 97}},
	{30807, 3, 50, [2]int{54, 56}},
	{25131, 3, 66, [2]int{67, 64}},
	{33079, 3, 58, [2]int{50, 53}},
	{12623, 3, 17, [2]int{22, 26}},
	{34378, 2, 89, [2]int{91, 88}},
	{18986, 2, 50, [2]int{51, 48}},
	{55391, 3, 91, [2]int{94, 96}},
	{12299, 3, 33, [2]int{35, 34}},
	{22121, 1, 57, [2]int{58, 56}},
	{31275, 3, 82, [2]int{83, 80}},
	{13385, 1, 35, [2]int{33, 32}},
	{20671, 3, 33, [2]int{27, 29}},
	{30903, 3, 50, [2]int{53, 57}},
	{35847, 3, 60, [2]int{52, 56}},
	{32778, 2, 86, [2]int{85, 87}},
	{55807, 3, 91, [2]int{95, 99}},
	{47167, 3, 81, [2]int{79, 84}},
	{12297, 1, 33, [2]int{35, 34}},
	{5131, 3, 14, [2]int{13, 15}},
	{15369, 1, 41, [2]int{42, 43}},
	{2057, 1, 6, [2]int{7, 5}},
	{38411, 3, 101, [2]int{103, 102}},
}

func tileIDs(t *testing.T, ns ...int) []tile.TileID {
	t.Helper()
	ids := make([]tile.TileID, 0, len(ns))
	for _, n := range ns {
		id, ok := tile.NewTileID(n)
		if !ok {
			t.Fatalf("NewTileID(%d) refused", n)
		}
		ids = append(ids, id)
	}
	return ids
}

func TestMeldCode_WhenGivenTheMeldsOfACapturedTenhouPlay_ShouldWriteTheirTenhouIntegers(t *testing.T) {
	for _, captured := range capturedTenhouMelds {
		kind := play.MeldChi
		if captured.held[0]/tile.CopiesPerKind == captured.held[1]/tile.CopiesPerKind {
			kind = play.MeldPon
		}
		tiles := tileIDs(t, captured.called, captured.held[0], captured.held[1])
		meld := wire.Meld{
			Caller: seat(t, 0), Kind: kind, Tiles: tiles, Called: play.Some(tiles[0]),
			From: play.Some(seat(t, captured.from)),
		}

		got, err := meldCode(meld)
		if err != nil || got != captured.code {
			t.Errorf("meldCode(%+v) = %d, %v; want %d", captured, got, err, captured.code)
		}
	}
}

func TestMeldCode_WhenTheMeldIsAKan_ShouldWriteItsTileAndOnlyAnOpenKansSource(t *testing.T) {
	quad := tileIDs(t, 104, 105, 106, 107)
	closed := wire.Meld{Caller: seat(t, 2), Kind: play.MeldClosedKan, Tiles: quad}
	open := wire.Meld{
		Caller: seat(t, 2), Kind: play.MeldOpenKan, Tiles: quad, Called: play.Some(quad[2]), From: play.Some(seat(t, 3)),
	}

	if got, err := meldCode(closed); err != nil || got != 104<<8 {
		t.Errorf("closed kan code = %d, %v; want %d", got, err, 104<<8)
	}
	if got, err := meldCode(open); err != nil || got != 106<<8|1 {
		t.Errorf("open kan code = %d, %v; want %d", got, err, 106<<8|1)
	}
}
