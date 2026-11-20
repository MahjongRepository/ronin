package main

import (
	"errors"
	"fmt"
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	handSize       = 13
	liveWallSize   = tile.TileIDCount - deadWallSize
	deadWallSize   = 14
	firstDrawSlot  = tile.SeatCount * handSize
	dealBlocks     = 3
	dealBlockSize  = 4
	dealRoundSize  = tile.SeatCount * dealBlockSize
	finalDealStart = dealBlocks * dealRoundSize
	firstUraSlot   = 9
	maxRinshan     = 4
	maxUra         = 5
	fillerWalls    = 40
)

const stagedSeedByte = 0x55

func stagedSeed() engine.Seed {
	var seed engine.Seed
	for i := range seed {
		seed[i] = stagedSeedByte
	}
	return seed
}

type stagedDraw struct {
	seat tile.Seat
	id   tile.TileID
}

type stagedWall struct {
	hands   [tile.SeatCount][]tile.TileID
	draws   []stagedDraw
	rinshan []tile.TileID
	ura     []tile.TileID
	dealer  tile.Seat
}

func (w stagedWall) drawOf(id tile.TileID) (int, bool) {
	index := slices.IndexFunc(w.draws, func(d stagedDraw) bool { return d.id == id })
	return index, index >= 0
}

func (w stagedWall) tiles() ([tile.TileIDCount]tile.TileID, error) {
	var tiles [tile.TileIDCount]tile.TileID
	switch {
	case slices.ContainsFunc(w.hands[:], func(h []tile.TileID) bool { return len(h) > handSize }):
		return tiles, errors.New("a staged hand holds more than 13 tiles")
	case firstDrawSlot+len(w.draws) > liveWallSize:
		return tiles, fmt.Errorf("%d staged draws spill past the live wall", len(w.draws))
	case len(w.rinshan) > maxRinshan || len(w.ura) > maxUra:
		return tiles, errors.New("the dead wall holds 4 rinshan tiles and 5 ura indicators")
	}

	placed := map[int]tile.TileID{}
	for _, seat := range tile.Seats() {
		for i, id := range w.hands[seat.Index()] {
			placed[dealSlot(seat.DistanceFrom(w.dealer), i)] = id
		}
	}
	for i, d := range w.draws {
		placed[firstDrawSlot+i] = d.id
	}
	for i, id := range w.rinshan {
		placed[liveWallSize+rinshanSlots()[i]] = id
	}
	for i, id := range w.ura {
		placed[liveWallSize+firstUraSlot+i] = id
	}

	var used [tile.TileIDCount]bool
	for _, id := range placed {
		if used[id.Index()] {
			return tiles, fmt.Errorf("a staged wall places tile %d twice", id.Index())
		}
		used[id.Index()] = true
	}
	var rest []tile.TileID
	for _, id := range tile.AllTileIDs() {
		if !used[id.Index()] {
			rest = append(rest, id)
		}
	}
	for slot := range tiles {
		id, ok := placed[slot]
		if !ok {
			id, rest = rest[0], rest[1:]
		}
		tiles[slot] = id
	}
	return tiles, nil
}

func rinshanSlots() [maxRinshan]int {
	return [maxRinshan]int{0, 7, 1, 8}
}

func dealSlot(offset, i int) int {
	if block := i / dealBlockSize; block < dealBlocks {
		return block*dealRoundSize + offset*dealBlockSize + i%dealBlockSize
	}
	return finalDealStart + offset
}

func stagedSetup(
	seed engine.Seed, rounds []stagedWall, start play.Option[play.StartPosition], dealers fillerDealers,
) (engine.Setup, error) {
	walls := make([][tile.TileIDCount]tile.TileID, 0, len(rounds)+fillerWalls)
	for _, round := range rounds {
		tiles, err := round.tiles()
		if err != nil {
			return engine.Setup{}, err
		}
		walls = append(walls, tiles)
	}
	for n := range uint32(fillerWalls) {
		roundNumber := firstFillerRound(rounds, start) + n
		walls = append(walls, seededWall(seed, roundNumber, dealers.of(roundNumber, rounds[len(rounds)-1].dealer)))
	}
	return engine.Setup{Walls: play.Fixed{Walls: walls}, Start: start}, nil
}

func firstFillerRound(rounds []stagedWall, start play.Option[play.StartPosition]) uint32 {
	return start.Value.RoundNumber + uint32(len(rounds))
}

type fillerDealers map[uint32]tile.Seat

func (d fillerDealers) of(roundNumber uint32, lastStaged tile.Seat) tile.Seat {
	dealer := lastStaged
	for n := range roundNumber + 1 {
		if known, ok := d[n]; ok {
			dealer = known
		}
	}
	return dealer
}

const (
	stacksPerSeat  = 17
	totalStacks    = tile.SeatCount * stacksPerSeat
	deadWallStacks = deadWallSize / 2
)

func seededWall(seed engine.Seed, roundNumber uint32, dealer tile.Seat) [tile.TileIDCount]tile.TileID {
	shuffled, dice := engine.RoundWall(seed, roundNumber)
	diceSum := dice.Sum()
	target := (dealer.Index() + diceSum - 1) % tile.SeatCount
	start := ((target+1)*stacksPerSeat - diceSum) % totalStacks

	var tiles [tile.TileIDCount]tile.TileID
	for i := range deadWallStacks {
		k := (start + i) % totalStacks
		tiles[liveWallSize+i], tiles[liveWallSize+deadWallStacks+i] = shuffled[2*k], shuffled[2*k+1]
	}
	for i := range totalStacks - deadWallStacks {
		k := (start + totalStacks - 1 - i) % totalStacks
		tiles[2*i], tiles[2*i+1] = shuffled[2*k], shuffled[2*k+1]
	}
	return tiles
}

type staging struct {
	err error
}

func (s *staging) ids(first int, mpsz string) []tile.TileID {
	parsed, err := tile.ParseTiles(mpsz)
	if err != nil {
		s.err = errors.Join(s.err, err)
		return nil
	}

	var seen [tile.KindCount]int
	ids := make([]tile.TileID, 0, len(parsed))
	for _, p := range parsed {
		kind := p.Kind()
		copyIndex := first + seen[kind]
		id, ok := tile.NewTileID(int(kind)*tile.CopiesPerKind + copyIndex)
		if !ok || copyIndex >= tile.CopiesPerKind {
			s.err = errors.Join(s.err, fmt.Errorf("%q repeats a kind past its copies", mpsz))
			return nil
		}
		ids = append(ids, id)
		seen[kind]++
	}
	return ids
}

func (s *staging) id(first int, mpsz string) tile.TileID {
	ids := s.ids(first, mpsz)
	if len(ids) != 1 {
		s.err = errors.Join(s.err, fmt.Errorf("%q names %d tiles, not one", mpsz, len(ids)))
		return tile.TileID{}
	}
	return ids[0]
}

func (s *staging) seat(n int) tile.Seat {
	seat, ok := tile.NewSeat(n)
	if !ok {
		s.err = errors.Join(s.err, fmt.Errorf("no seat %d", n))
	}
	return seat
}

func (s *staging) draw(seat int, id tile.TileID) stagedDraw {
	return stagedDraw{seat: s.seat(seat), id: id}
}
