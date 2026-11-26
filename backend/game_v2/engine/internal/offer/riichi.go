package offer

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func checkedRiichiDiscards(
	hand []tile.TileID, melds []play.MeldView, inRiichi bool, score, liveTiles int, ruleset play.Ruleset,
) ([]tile.TileID, error) {
	if err := meld.CheckHandInput(hand, melds); err != nil {
		return nil, err
	}

	return RiichiDiscards(hand, melds, inRiichi, score, liveTiles, ruleset), nil
}

func RiichiDiscards(
	held []tile.TileID, melds []play.MeldView, inRiichi bool, score, liveTiles int, ruleset play.Ruleset,
) []tile.TileID {
	closed := !slices.ContainsFunc(melds, func(view play.MeldView) bool { return view.Kind != play.MeldClosedKan })
	settings := rules.Of(ruleset)
	cannotAffordStick := !settings.ShakkinRiichi && score < settings.RiichiStickValue
	if inRiichi || !closed || cannotAffordStick || liveTiles < settings.RiichiMinWall {
		return nil
	}

	kinds := hand.TenpaiDiscards(countsOfDistinctIDs(held), countsOfDistinctIDs(meldedTiles(melds)))
	var discards []tile.TileID
	for _, id := range held {
		if kinds.Contains(id.Kind()) {
			discards = append(discards, id)
		}
	}

	return discards
}
