package tenhou

import (
	"regexp"
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replay"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	handSize       = 13
	liveWallSize   = 122
	dealBlocks     = 3
	dealBlockSize  = 4
	dealRoundSize  = tile.SeatCount * dealBlockSize
	finalDealStart = dealBlocks * dealRoundSize
	firstDrawSlot  = tile.SeatCount * handSize
)

var rinshanSlots = [...]int{122, 129, 123, 130}

var testRoster = messaging.Roster{GameID: "game-0001", Names: [tile.SeatCount]string{"P0", "P1", "P2", "P3"}}

func seat(t *testing.T, n int) tile.Seat {
	t.Helper()
	got, ok := tile.NewSeat(n)
	if !ok {
		t.Fatalf("NewSeat(%d) refused", n)
	}
	return got
}

func copies(t *testing.T, first int, mpsz string) []tile.TileID {
	t.Helper()
	parsed, err := tile.ParseTiles(mpsz)
	if err != nil {
		t.Fatalf("ParseTiles(%q) error = %v", mpsz, err)
	}
	var seen [tile.KindCount]int
	ids := make([]tile.TileID, 0, len(parsed))
	for _, p := range parsed {
		kind := p.Kind()
		id, ok := tile.NewTileID(int(kind)*tile.CopiesPerKind + first + seen[kind])
		if !ok {
			t.Fatalf("no copy %d of %v", first+seen[kind], kind)
		}
		ids = append(ids, id)
		seen[kind]++
	}
	return ids
}

func copyOf(t *testing.T, first int, mpsz string) tile.TileID {
	t.Helper()
	ids := copies(t, first, mpsz)
	if len(ids) != 1 {
		t.Fatalf("%q holds %d tiles, want 1", mpsz, len(ids))
	}
	return ids[0]
}

func join(parts ...[]tile.TileID) []tile.TileID {
	return slices.Concat(parts...)
}

type stagedWall struct {
	hands   [tile.SeatCount][]tile.TileID
	draws   []tile.TileID
	rinshan []tile.TileID
}

func dealSlot(seatIndex, i int) int {
	if block := i / dealBlockSize; block < dealBlocks {
		return block*dealRoundSize + seatIndex*dealBlockSize + i%dealBlockSize
	}
	return finalDealStart + seatIndex
}

func (w stagedWall) tiles(t *testing.T) [tile.TileIDCount]tile.TileID {
	t.Helper()
	var slots [tile.TileIDCount]tile.TileID
	var filled [tile.TileIDCount]bool
	var placed []tile.TileID
	place := func(slot int, at tile.TileID) {
		if slices.Contains(placed, at) {
			t.Fatalf("staged wall places tile %d twice", at.Index())
		}
		slots[slot], filled[slot] = at, true
		placed = append(placed, at)
	}
	for s, hand := range w.hands {
		if len(hand) != handSize {
			t.Fatalf("staged wall deals seat %d %d tiles", s, len(hand))
		}
		for i, held := range hand {
			place(dealSlot(s, i), held)
		}
	}
	for i, drawn := range w.draws {
		place(firstDrawSlot+i, drawn)
	}
	for i, drawn := range w.rinshan {
		place(rinshanSlots[i], drawn)
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

func stagedSetup(t *testing.T, w stagedWall, start play.Option[play.StartPosition]) engine.Setup {
	t.Helper()
	return engine.Setup{Walls: play.Fixed{Walls: [][tile.TileIDCount]tile.TileID{w.tiles(t)}}, Start: start}
}

func act(t *testing.T, n int, action play.Action) replay.SeatAction {
	t.Helper()
	return replay.SeatAction{Seat: seat(t, n), Action: action}
}

func playedReplay(t *testing.T, setup engine.Setup, actions []replay.SeatAction) []byte {
	t.Helper()
	steps, err := replay.Run(setup, actions)
	if err != nil {
		t.Fatalf("replay.Run error = %v", err)
	}
	return recordedReplay(t, engine.Seed{}, steps)
}

func recordedReplay(t *testing.T, seed engine.Seed, steps []replay.Step) []byte {
	t.Helper()
	log := messaging.NewReplayLog(seed, testRoster)
	for _, step := range steps {
		table := func() messaging.Table {
			return messaging.Table{Roster: testRoster, Record: step.Game.View(tile.Seats()[0]).Record}
		}
		if err := log.Collect(step.Events, table); err != nil {
			t.Fatalf("Collect error = %v", err)
		}
	}

	content, err := wire.EncodeReplay(append([]wire.Map{wire.VersionRecord()}, log.Records()...))
	if err != nil {
		t.Fatalf("EncodeReplay error = %v", err)
	}
	return content
}

func converted(t *testing.T, content []byte) string {
	t.Helper()
	xml, err := Convert(content)
	if err != nil {
		t.Fatalf("Convert error = %v", err)
	}
	return xml
}

func tags(xml, pattern string) []string {
	return regexp.MustCompile(pattern).FindAllString(xml, -1)
}
