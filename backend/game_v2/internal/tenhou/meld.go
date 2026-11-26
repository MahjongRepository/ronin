package tenhou

import (
	"errors"
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	meldChiFlag      = 1 << 2
	meldPonFlag      = 1 << 3
	meldAddedKanFlag = 1 << 4
	chiStartsPerSuit = 7
	ranksPerSuit     = 9
	setTiles         = 3
	copySum          = 0 + 1 + 2 + 3
)

var errMeldShape = errors.New("meld is no meld of its kind")

func meldCode(m wire.Meld) (int, error) {
	tiles := make([]int, 0, len(m.Tiles))
	for _, t := range m.Tiles {
		tiles = append(tiles, t.Index())
	}

	slices.Sort(tiles)
	if len(tiles) == 0 {
		return 0, errMeldShape
	}

	offset := 0
	if m.From.OK {
		offset = m.From.Value.DistanceFrom(m.Caller)
	}

	kind := tiles[0] / tile.CopiesPerKind
	switch m.Kind {
	case play.MeldChi:
		called := calledIndex(m, tiles)
		if len(tiles) != setTiles || called < 0 {
			return 0, errMeldShape
		}

		start := kind/ranksPerSuit*chiStartsPerSuit + kind%ranksPerSuit
		return (start*setTiles+called)<<10 | copyIndex(tiles[2])<<7 | copyIndex(tiles[1])<<5 | copyIndex(tiles[0])<<3 |
			meldChiFlag | offset, nil
	case play.MeldPon:
		called := calledIndex(m, tiles)
		if len(tiles) != setTiles || called < 0 {
			return 0, errMeldShape
		}

		unused := copySum - copyIndex(tiles[0]) - copyIndex(tiles[1]) - copyIndex(tiles[2])
		return (kind*setTiles+called)<<9 | unused<<5 | meldPonFlag | offset, nil
	case play.MeldAddedKan:
		if !m.Added.OK {
			return 0, errMeldShape
		}

		added := m.Added.Value.Index()
		pon := slices.DeleteFunc(slices.Clone(tiles), func(t int) bool { return t == added })
		called := calledIndex(m, pon)
		if len(pon) != setTiles || called < 0 {
			return 0, errMeldShape
		}

		return (kind*setTiles+called)<<9 | copyIndex(added)<<5 | meldAddedKanFlag | offset, nil
	case play.MeldOpenKan:
		if !m.Called.OK {
			return 0, errMeldShape
		}

		return m.Called.Value.Index()<<8 | offset, nil
	case play.MeldClosedKan:
		return (kind * tile.CopiesPerKind) << 8, nil
	}

	return 0, errMeldShape
}

func calledIndex(m wire.Meld, tiles []int) int {
	if !m.Called.OK {
		return -1
	}

	return slices.Index(tiles, m.Called.Value.Index())
}

func copyIndex(id int) int {
	return id % tile.CopiesPerKind
}
