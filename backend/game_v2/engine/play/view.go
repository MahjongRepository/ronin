package play

import "github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"

// Phase is the phase of a game.
type Phase uint8

const (
	PhasePlaying Phase = iota
	PhaseRoundOver
	PhaseGameOver
)

// PublicSeat is what every seat sees of one seat; Riichi is set only once the riichi discard has
// passed every ron.
type PublicSeat struct {
	Seat        tile.Seat
	Score       int
	ClosedTiles int
	River       []RiverTile
	Melds       []MeldView
	Riichi      Option[Riichi]
	Pao         Option[tile.Seat]
}

// DeclaredRiichi reports whether the seat declared riichi: from its riichi discard on, before that
// discard passes every ron and sets Riichi too.
func (s PublicSeat) DeclaredRiichi() bool {
	if s.Riichi.OK {
		return true
	}
	for _, discard := range s.River {
		if discard.Riichi {
			return true
		}
	}
	return false
}

// FinishedRound is a finished round: its header, how it ended, and the seats whose riichi discard
// passed every ron, so their stick was deposited, in seat order.
type FinishedRound struct {
	Header      RoundHeader
	Result      RoundResult
	RiichiSeats []tile.Seat
}

// SeatRecord is the facts of the game as one seat knows them, rebuilt from its visible events
// alone. Hand is in hand order, a drawn tile last. LatestDiscard is absent before the first
// discard and once a meld claimed it, the next seat drew or the round ended. Result is nil while a
// round is in play.
type SeatRecord struct {
	Seat            tile.Seat
	Hand            []tile.TileID
	Drawn           Option[tile.TileID]
	Furiten         bool
	Players         [tile.SeatCount]PublicSeat
	DoraIndicators  []tile.TileID
	LiveTiles       int
	RiichiSticks    int
	Current         tile.Seat
	LatestDiscard   Option[tile.Seat]
	Header          RoundHeader
	Result          RoundResult
	Phase           Phase
	FirstDealer     tile.Seat
	FirstDealerDice [2]tile.Dice
	History         []FinishedRound
}

// SeatView is what one seat may see of the game now: the facts it knows, and its prompt, absent
// when the game does not await it. It never holds another seat's concealed tiles, decision,
// furiten or pending call answer.
type SeatView struct {
	Record   SeatRecord
	Decision Option[Decision]
}
