package offer

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func isKan(view play.MeldView) bool {
	return view.Kind == play.MeldOpenKan || view.Kind == play.MeldAddedKan || view.Kind == play.MeldClosedKan
}

// KansBySeat returns the kans each seat declared in the round, from its melds.
func KansBySeat(melds [tile.SeatCount][]play.MeldView) [tile.SeatCount]int {
	var kans [tile.SeatCount]int
	for seat, seatMelds := range melds {
		kans[seat] = KanCount(seatMelds)
	}
	return kans
}

// KanCount returns the kans among one seat's melds.
func KanCount(melds []play.MeldView) int {
	count := 0
	for _, view := range melds {
		if isKan(view) {
			count++
		}
	}
	return count
}

// MayAddKan reports whether one more kan may stand beside the kans of each seat: a live tile left
// for the dead wall to take and a rinshan tile left to draw.
func MayAddKan(kans [tile.SeatCount]int, liveTiles int) bool {
	return liveTiles >= rules.MinWallForKan && totalKans(kans) < rules.MaxKans
}

func totalKans(kans [tile.SeatCount]int) int {
	total := 0
	for _, count := range kans {
		total += min(count, rules.MaxKans)
	}
	return total
}

// IsFourKans reports whether four kans stand and more than one seat declared them.
func IsFourKans(kans [tile.SeatCount]int) bool {
	declaring := 0
	for _, count := range kans {
		if count > 0 {
			declaring++
		}
	}
	return rules.Suukaikan && totalKans(kans) >= rules.MaxKans && declaring >= rules.MinPlayersForKanAbort
}

// CheckedKanOffers returns KanOffers for a hand and melds given from outside the engine; a
// meld.MisfitMeldError for the first meld that does not fit its kind, else a
// meld.DuplicateTileError for the first tile id held twice among hand and the melds' tiles.
func CheckedKanOffers(
	hand []tile.TileID, melds []play.MeldView, drawn tile.TileID, inRiichi bool,
	kans [tile.SeatCount]int, liveTiles int,
) ([]play.Action, error) {
	if err := meld.CheckHandInput(hand, melds); err != nil {
		return nil, err
	}
	return KanOffers(hand, melds, drawn, inRiichi, kans, liveTiles), nil
}

// KanOffers returns the closed kans, then the added kans, a seat may declare after drawing drawn,
// its hand holding the drawn tile, beside the kans of each seat, 0 or more. A closed kan names
// the first held copy of its kind, an added kan the held fourth copy of its pon. In riichi only a
// closed kan of the drawn kind that keeps the waits.
func KanOffers(
	hand []tile.TileID, melds []play.MeldView, drawn tile.TileID, inRiichi bool,
	kans [tile.SeatCount]int, liveTiles int,
) []play.Action {
	if !MayAddKan(kans, liveTiles) {
		return nil
	}

	var offers []play.Action
	riichiDrawn := play.Option[tile.TileID]{Value: drawn, OK: inRiichi}
	for _, id := range closedKanTiles(hand, melds, riichiDrawn) {
		offers = append(offers, play.KanAction(play.KanClosed, id))
	}
	if inRiichi {
		return offers
	}
	for _, id := range addedKanTiles(hand, melds) {
		offers = append(offers, play.KanAction(play.KanAdded, id))
	}
	return offers
}

func closedKanTiles(hand []tile.TileID, melds []play.MeldView, riichiDrawn play.Option[tile.TileID]) []tile.TileID {
	var held [tile.KindCount]int
	for _, id := range hand {
		held[id.Kind()]++
	}

	var tiles []tile.TileID
	var seen tile.Kinds
	for _, id := range hand {
		kind := id.Kind()
		if seen.Contains(kind) || held[kind] < tile.CopiesPerKind {
			continue
		}
		seen = seen.With(kind)

		allowed := !riichiDrawn.OK || (riichiDrawn.Value.Kind() == kind && kanKeepsWaits(hand, melds, kind))
		if allowed {
			tiles = append(tiles, id)
		}
	}
	return tiles
}

func kanKeepsWaits(held []tile.TileID, melds []play.MeldView, kind tile.Kind) bool {
	melded := meldedTiles(melds)
	before, _ := countsOfDistinctIDs(held).WithoutOne(kind)
	after := slices.DeleteFunc(slices.Clone(held), func(id tile.TileID) bool { return id.Kind() == kind })
	meldedAfter := slices.AppendSeq(slices.Clone(melded), tile.HeldCopies(held, kind))

	waitsBefore := hand.Waits(before, countsOfDistinctIDs(melded))
	waitsAfter := hand.Waits(countsOfDistinctIDs(after), countsOfDistinctIDs(meldedAfter))
	return waitsBefore == waitsAfter
}

func addedKanTiles(hand []tile.TileID, melds []play.MeldView) []tile.TileID {
	var tiles []tile.TileID
	for _, view := range melds {
		if view.Kind != play.MeldPon || len(view.Tiles) == 0 {
			continue
		}
		if fourth := slices.Collect(tile.HeldCopies(hand, view.Tiles[0].Kind())); len(fourth) > 0 {
			tiles = append(tiles, fourth[0])
		}
	}
	return tiles
}
