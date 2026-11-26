package session

import (
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
)

// seatClaim is who may hold a seat: the claim that took it last, and the version a newer claim
// must name to take it over. A claim's own retries keep it; an older claim is fenced off for good.
type seatClaim struct {
	version int
	owner   string
}

func newSeatClaims(players []PlayerSpec) map[string]*seatClaim {
	claims := make(map[string]*seatClaim, len(players))
	for _, spec := range players {
		claims[spec.Ticket] = &seatClaim{}
	}

	return claims
}

// take reports whether claim may hold the seat, making it the owner when it names the current
// version. A connection that claims nothing, such as a bot's, binds only while no claim owns the seat.
func (c *seatClaim) take(claim play.Option[messaging.Claim]) bool {
	switch {
	case !claim.OK:
		return c.owner == ""
	case claim.Value.ID == c.owner:
		return true
	case claim.Value.SeatVersion != c.version:
		return false
	}

	c.owner = claim.Value.ID
	c.version++
	return true
}
