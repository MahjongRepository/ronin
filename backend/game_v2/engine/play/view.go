package play

import "github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"

// Phase is the phase of a game.
type Phase uint8

// The phases: a round is in play; a round has ended and the game goes on; the game has ended.
const (
	PhasePlaying Phase = iota
	PhaseRoundOver
	PhaseGameOver
)

// PublicSeat is what every seat sees of one seat: its score, the tiles of its closed hand seen
// face down, its discards as they fell with the called ones included, its declared melds in call
// order, its riichi once in effect (the riichi discard having passed every ron), and the seat
// that pays for its daisangen or daisuushii, having fed the set that completed it.
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

// SeatRecord is the facts of the game as one seat knows them, which its visible events alone
// rebuild. Hand holds the seat's concealed tiles in hand order, a drawn tile last; Drawn is the
// tile it drew, until its discard, call or the round's end; Furiten is what it was last shown.
// Players is every seat's public table, by seat. RiichiSticks are the sticks on the table, 0 once
// the game is over. Current is the seat whose turn it is or was last; LatestDiscard the seat whose
// discard is the table's last action, absent before the first discard, once a meld claimed it,
// once the next seat drew and once the round ended. Header is the round in play, or the one that ended while the game
// waits on its end or is over; Result is that round's result in PhaseRoundOver and PhaseGameOver,
// nil while a round is in play. FirstDealerDice are the two throws that chose the first dealer,
// and History every finished round in play order, the ended one included.
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
