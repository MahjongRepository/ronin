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
	{code: 46207, from: 3, called: 79, held: [2]int{83, 84}},
	{code: 56519, from: 3, called: 94, held: [2]int{88, 97}},
	{code: 30807, from: 3, called: 50, held: [2]int{54, 56}},
	{code: 25131, from: 3, called: 66, held: [2]int{67, 64}},
	{code: 33079, from: 3, called: 58, held: [2]int{50, 53}},
	{code: 12623, from: 3, called: 17, held: [2]int{22, 26}},
	{code: 34378, from: 2, called: 89, held: [2]int{91, 88}},
	{code: 18986, from: 2, called: 50, held: [2]int{51, 48}},
	{code: 55391, from: 3, called: 91, held: [2]int{94, 96}},
	{code: 12299, from: 3, called: 33, held: [2]int{35, 34}},
	{code: 22121, from: 1, called: 57, held: [2]int{58, 56}},
	{code: 31275, from: 3, called: 82, held: [2]int{83, 80}},
	{code: 13385, from: 1, called: 35, held: [2]int{33, 32}},
	{code: 20671, from: 3, called: 33, held: [2]int{27, 29}},
	{code: 30903, from: 3, called: 50, held: [2]int{53, 57}},
	{code: 35847, from: 3, called: 60, held: [2]int{52, 56}},
	{code: 32778, from: 2, called: 86, held: [2]int{85, 87}},
	{code: 55807, from: 3, called: 91, held: [2]int{95, 99}},
	{code: 47167, from: 3, called: 81, held: [2]int{79, 84}},
	{code: 12297, from: 1, called: 33, held: [2]int{35, 34}},
	{code: 5131, from: 3, called: 14, held: [2]int{13, 15}},
	{code: 15369, from: 1, called: 41, held: [2]int{42, 43}},
	{code: 2057, from: 1, called: 6, held: [2]int{7, 5}},
	{code: 38411, from: 3, called: 101, held: [2]int{103, 102}},
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

	if got, err := meldCode(closed); err != nil || got != 26624 {
		t.Errorf("closed kan code = %d, %v; want 26624", got, err)
	}

	if got, err := meldCode(open); err != nil || got != 27137 {
		t.Errorf("open kan code = %d, %v; want 27137", got, err)
	}
}
