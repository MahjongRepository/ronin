package offer

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// CheckedRiichiDiscards returns RiichiDiscards for a hand and melds given from outside the
// engine; a meld.MisfitMeldError for the first meld that does not fit its kind, else a
// meld.DuplicateTileError for the first tile id held twice among hand and the melds' tiles.
func CheckedRiichiDiscards(
	hand []tile.TileID, melds []play.MeldView, inRiichi bool, score, liveTiles int,
) ([]tile.TileID, error) {
	if err := meld.CheckHandInput(hand, melds); err != nil {
		return nil, err
	}
	return RiichiDiscards(hand, melds, inRiichi, score, liveTiles), nil
}

// RiichiDiscards returns the riichi a seat on its turn may declare, as the held tiles whose
// discard keeps the hand tenpai, in hand order: none unless the hand is closed but for closed
// kans, not in riichi yet, with score points to pay the stick and liveTiles enough for a riichi.
func RiichiDiscards(held []tile.TileID, melds []play.MeldView, inRiichi bool, score, liveTiles int) []tile.TileID {
	closed := !slices.ContainsFunc(melds, func(view play.MeldView) bool { return view.Kind != play.MeldClosedKan })
	if inRiichi || !closed || score < rules.RiichiCost || liveTiles < rules.MinWallForRiichi {
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
