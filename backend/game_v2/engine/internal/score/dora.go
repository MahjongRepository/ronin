package score

import "github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"

const (
	windCount   = 4
	dragonCount = 3
	suitRanks   = 9
)

func indicatorToDora(indicator tile.Kind) tile.Kind {
	if !indicator.IsHonor() {
		rank := tile.Kind(indicator.Simplify())
		return indicator - rank + (rank+1)%suitRanks
	}

	if indicator <= tile.KindNorth {
		return tile.KindEast + (indicator-tile.KindEast+1)%windCount
	}

	return tile.KindHaku + (indicator-tile.KindHaku+1)%dragonCount
}

func countDoraForHand(counts [tile.KindCount]uint8, indicators []tile.Tile) int {
	dora := 0
	for _, indicator := range indicators {
		dora += int(counts[indicatorToDora(indicator.Kind())])
	}
	return dora
}
