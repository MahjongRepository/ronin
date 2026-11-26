package offer

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// NagashiSeats returns the seats with a nagashi mangan, in seat order: every own discard a
// terminal or honor, and none of them called.
func NagashiSeats(rivers [tile.SeatCount][]play.RiverTile, melds [tile.SeatCount][]play.MeldView) []tile.Seat {
	var seats []tile.Seat
	for _, seat := range tile.Seats() {
		river := rivers[seat.Index()]
		allTerminalOrHonor := !slices.ContainsFunc(river, func(discard play.RiverTile) bool {
			return !discard.Tile.Kind().IsTerminalOrHonor()
		})
		if len(river) > 0 && allTerminalOrHonor && !isCalledFrom(melds, seat) {
			seats = append(seats, seat)
		}
	}

	return seats
}

func isCalledFrom(melds [tile.SeatCount][]play.MeldView, seat tile.Seat) bool {
	for _, seatMelds := range melds {
		for _, view := range seatMelds {
			if view.From.OK && view.From.Value == seat {
				return true
			}
		}
	}

	return false
}
