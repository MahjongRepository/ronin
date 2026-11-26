package offer

import (
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func CheckedKanOffers(
	hand []tile.TileID, melds []play.MeldView, drawn tile.TileID, inRiichi bool,
	kans [tile.SeatCount]int, liveTiles int,
) ([]play.Action, error) {
	return checkedKanOffers(hand, melds, drawn, inRiichi, kans, liveTiles, play.RulesetTenhou)
}

func CheckedMeldOffers(
	hand []tile.TileID, inRiichi bool, seat, from tile.Seat, discard tile.TileID,
	kans [tile.SeatCount]int, liveTiles int,
) ([]play.Action, error) {
	return checkedMeldOffers(hand, inRiichi, seat, from, discard, kans, liveTiles, play.RulesetTenhou)
}

func CheckedRiichiDiscards(
	hand []tile.TileID, melds []play.MeldView, inRiichi bool, score, liveTiles int,
) ([]tile.TileID, error) {
	return checkedRiichiDiscards(hand, melds, inRiichi, score, liveTiles, play.RulesetTenhou)
}

func KanCount(melds []play.MeldView) int {
	return kanCount(melds)
}

func MayAddKan(kans [tile.SeatCount]int, liveTiles int) bool {
	return mayAddKan(kans, liveTiles)
}

func PonOptions(hand []tile.TileID, inRiichi bool, discard tile.TileID) [][2]tile.TileID {
	return ponOptions(hand, inRiichi, discard, tile.AkaDoraEnabled)
}

func ChiOptions(hand []tile.TileID, inRiichi bool, discard tile.TileID) [][2]tile.TileID {
	return chiOptions(hand, inRiichi, discard, tile.AkaDoraEnabled)
}
