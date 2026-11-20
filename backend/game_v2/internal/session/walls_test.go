package session_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	handSize       = 13
	dealBlocks     = 3
	dealBlockSize  = 4
	dealRoundSize  = tile.SeatCount * dealBlockSize
	finalDealStart = dealBlocks * dealRoundSize
	firstDrawSlot  = tile.SeatCount * handSize
)

func copies(t *testing.T, first int, mpsz string) []tile.TileID {
	t.Helper()
	parsed, err := tile.ParseTiles(mpsz)
	if err != nil {
		t.Fatalf("ParseTiles(%q) error = %v", mpsz, err)
	}
	var seen [tile.KindCount]int
	got := make([]tile.TileID, 0, len(parsed))
	for _, p := range parsed {
		kind := p.Kind()
		id, ok := tile.NewTileID(int(kind)*tile.CopiesPerKind + first + seen[kind])
		if !ok {
			t.Fatalf("no copy %d of %v", first+seen[kind], kind)
		}
		got = append(got, id)
		seen[kind]++
	}
	return got
}

func dealSlot(offset, i int) int {
	if block := i / dealBlockSize; block < dealBlocks {
		return block*dealRoundSize + offset*dealBlockSize + i%dealBlockSize
	}
	return finalDealStart + offset
}

func fixedWall(t *testing.T, hands [tile.SeatCount][]tile.TileID, draws []tile.TileID) [tile.TileIDCount]tile.TileID {
	t.Helper()
	var slots [tile.TileIDCount]tile.TileID
	var filled [tile.TileIDCount]bool
	var placed []tile.TileID
	place := func(slot int, at tile.TileID) {
		if slices.Contains(placed, at) {
			t.Fatalf("wall places tile %d twice", at.Index())
		}
		slots[slot], filled[slot] = at, true
		placed = append(placed, at)
	}
	for _, s := range tile.Seats() {
		for i, held := range hands[s.Index()] {
			place(dealSlot(s.Index(), i), held)
		}
	}
	for i, drawn := range draws {
		place(firstDrawSlot+i, drawn)
	}

	var free []tile.TileID
	for _, unplaced := range tile.AllTileIDs() {
		if !slices.Contains(placed, unplaced) {
			free = append(free, unplaced)
		}
	}
	for slot := range slots {
		if !filled[slot] {
			slots[slot], free = free[0], free[1:]
		}
	}
	return slots
}

func shuffledWall(seed engine.Seed, round uint32) [tile.TileIDCount]tile.TileID {
	tiles, _ := engine.RoundWall(seed, round)
	return tiles
}

func junkHand(t *testing.T, first int) []tile.TileID {
	t.Helper()
	return copies(t, first, "1357m2468p1379s7z")
}

func doubleRonWall(t *testing.T) [tile.TileIDCount]tile.TileID {
	t.Helper()
	return fixedWall(t, [tile.SeatCount][]tile.TileID{
		junkHand(t, 2),
		copies(t, 0, "123456789m123p5s"),
		copies(t, 1, "123456789p111z5s"),
		junkHand(t, 3),
	}, copies(t, 3, "5s"))
}

func ronAndPonWall(t *testing.T) [tile.TileIDCount]tile.TileID {
	t.Helper()
	return fixedWall(t, [tile.SeatCount][]tile.TileID{
		junkHand(t, 2),
		copies(t, 0, "123456789m123p5s"),
		copies(t, 1, "1357m2468p55s79s6z"),
		junkHand(t, 3),
	}, copies(t, 3, "5s"))
}
