package record

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// fromStart returns the record of seat after the events game.New returned; false when they lack
// the GameStarted or the seat's RoundStarted.
func fromStart(seat tile.Seat, events []play.Emitted) (play.SeatRecord, bool) {
	var started play.GameStarted
	var dealt play.RoundStarted
	foundGame, foundRound := false, false
	for _, e := range events {
		if event, ok := e.Event.(play.GameStarted); ok && !foundGame {
			started, foundGame = event, true
		}

		if event, ok := e.Event.(play.RoundStarted); ok && !foundRound && event.Seat == seat {
			dealt, foundRound = event, true
		}
	}

	if !foundGame || !foundRound {
		return play.SeatRecord{}, false
	}

	r := startedRecord(seat, started, dealt.Header)
	for _, e := range events {
		r = Apply(r, e)
	}

	return r, true
}

func startedRecord(seat tile.Seat, started play.GameStarted, header play.RoundHeader) play.SeatRecord {
	r := play.SeatRecord{
		Seat:            seat,
		RiichiSticks:    header.RiichiSticks,
		Current:         header.Dealer,
		Header:          header,
		Phase:           play.PhasePlaying,
		FirstDealer:     started.FirstDealer,
		FirstDealerDice: started.Dice,
	}

	for _, player := range tile.Seats() {
		r.Players[player.Index()].Seat = player
	}

	return r
}

// Apply returns r after the next event of the game, taken in the order the game returned it; an
// event r's seat may not see changes nothing.
func Apply(r play.SeatRecord, e play.Emitted) play.SeatRecord {
	if !e.To.Includes(r.Seat) {
		return r
	}

	switch event := e.Event.(type) {
	case play.GameStarted:
		r.FirstDealer = event.FirstDealer
		r.FirstDealerDice = event.Dice
		r.History = nil
	case play.RoundStarted:
		if event.Seat == r.Seat {
			r = startRound(r, event)
		}
	case play.Drew:
		if event.Seat == r.Seat {
			r.Hand = append(slices.Clip(r.Hand), event.Tile)
			r.Drawn = play.Some(event.Tile)
			r = draw(r, event.Seat, event.Rinshan)
		}
	case play.DrewNotice:
		r = draw(r, event.Seat, event.Rinshan)
	case play.Discarded:
		r = discard(r, event)
	case play.RiichiDeposited:
		r = depositRiichi(r, event)
	case play.FuritenChanged:
		if event.Seat == r.Seat {
			r.Furiten = event.Furiten
		}
	case play.Called:
		r = call(r, event.Seat, event.Meld)
	case play.PaoAssigned:
		r.Players[event.Seat.Index()].Pao = play.Some(event.Liable)
	case play.DoraRevealed:
		r.DoraIndicators = append(slices.Clip(r.DoraIndicators), event.Indicator)
	case play.RoundEnded:
		r = endRound(r, event)
	case play.GameEnded:
		r.Players = withScores(r.Players, event.Standings.Scores)
		r.RiichiSticks = 0
		r.Phase = play.PhaseGameOver
	}

	return r
}

func startRound(r play.SeatRecord, event play.RoundStarted) play.SeatRecord {
	r.Hand = slices.Clone(event.Hand)
	r.Drawn = play.Option[tile.TileID]{}
	r.Furiten = false
	for i := range r.Players {
		r.Players[i] = play.PublicSeat{Seat: r.Players[i].Seat, ClosedTiles: len(event.Hand)}
	}

	r.Players = withScores(r.Players, event.Scores)
	r.DoraIndicators = slices.Clone(event.DoraIndicators)
	r.LiveTiles = event.LiveTiles
	r.RiichiSticks = event.Header.RiichiSticks

	r.Current = event.Header.Dealer
	r.LatestDiscard = play.Option[tile.Seat]{}
	r.Header = event.Header
	r.Result = nil
	r.Phase = play.PhasePlaying
	return r
}

func withScores(players [tile.SeatCount]play.PublicSeat, scores [tile.SeatCount]int) [tile.SeatCount]play.PublicSeat {
	for i := range players {
		players[i].Score = scores[i]
	}

	return players
}

func draw(r play.SeatRecord, seat tile.Seat, rinshan bool) play.SeatRecord {
	r.Current = seat
	r.LiveTiles = max(0, r.LiveTiles-1)
	r.Players[seat.Index()].ClosedTiles++
	if rinshan {
		return endEveryIppatsu(r)
	}

	r.LatestDiscard = play.Option[tile.Seat]{}
	return r
}

func discard(r play.SeatRecord, event play.Discarded) play.SeatRecord {
	player := &r.Players[event.Seat.Index()]
	player.River = append(slices.Clip(player.River), play.RiverTile{
		Tile: event.Tile, Tsumogiri: event.Tsumogiri, Riichi: event.Riichi,
	})
	player.ClosedTiles = max(0, player.ClosedTiles-1)
	if player.Riichi.OK {
		player.Riichi.Value.Ippatsu = false
	}

	r.Current = event.Seat
	r.LatestDiscard = play.Some(event.Seat)
	if event.Seat != r.Seat {
		return r
	}

	if position := slices.Index(r.Hand, event.Tile); position >= 0 {
		r.Hand = slices.Delete(slices.Clone(r.Hand), position, position+1)
	}

	r.Drawn = play.Option[tile.TileID]{}
	return r
}

func depositRiichi(r play.SeatRecord, event play.RiichiDeposited) play.SeatRecord {
	double := len(r.Players[event.Seat.Index()].River) == 1
	for _, player := range r.Players {
		double = double && len(player.Melds) == 0
	}

	player := &r.Players[event.Seat.Index()]
	player.Riichi = play.Some(play.Riichi{Double: double, Ippatsu: true})
	player.Score = event.Score
	r.RiichiSticks = event.RiichiSticks
	return r
}

func call(r play.SeatRecord, seat tile.Seat, meld play.MeldView) play.SeatRecord {
	player := &r.Players[seat.Index()]
	var taken []tile.TileID
	if pon := addedPon(player.Melds, meld); pon >= 0 {
		for _, id := range meld.Tiles {
			if !slices.Contains(player.Melds[pon].Tiles, id) {
				taken = append(taken, id)
			}
		}

		player.Melds = slices.Clone(player.Melds)
		player.Melds[pon] = cloneMeld(meld)
	} else {
		for _, id := range meld.Tiles {
			if !meld.Called.OK || meld.Called.Value != id {
				taken = append(taken, id)
			}
		}

		player.Melds = append(slices.Clip(player.Melds), cloneMeld(meld))
	}

	player.ClosedTiles = max(0, player.ClosedTiles-len(taken))
	r.Current = seat
	switch meld.Kind {
	case play.MeldChi, play.MeldPon, play.MeldOpenKan:
		r = endEveryIppatsu(r)
		r.LatestDiscard = play.Option[tile.Seat]{}
	case play.MeldAddedKan, play.MeldClosedKan:
	}

	if seat == r.Seat {
		r.Hand = slices.DeleteFunc(slices.Clone(r.Hand), func(held tile.TileID) bool { return slices.Contains(taken, held) })
		r.Drawn = play.Option[tile.TileID]{}
	}

	return r
}

func addedPon(melds []play.MeldView, meld play.MeldView) int {
	if meld.Kind != play.MeldAddedKan {
		return -1
	}

	return slices.IndexFunc(melds, func(pon play.MeldView) bool {
		return pon.Kind == play.MeldPon && pon.Called == meld.Called
	})
}

func endEveryIppatsu(r play.SeatRecord) play.SeatRecord {
	for i := range r.Players {
		if r.Players[i].Riichi.OK {
			r.Players[i].Riichi.Value.Ippatsu = false
		}
	}

	return r
}

func endRound(r play.SeatRecord, event play.RoundEnded) play.SeatRecord {
	if _, exhaustive := event.Result.(play.ExhaustiveDraw); exhaustive {
		r.Current = r.Current.Next()
	}

	r.Players = withScores(r.Players, event.Scores)
	r.RiichiSticks = event.RiichiSticks
	r.Drawn = play.Option[tile.TileID]{}
	r.LatestDiscard = play.Option[tile.Seat]{}
	r.Phase = play.PhaseRoundOver
	r.Result = CloneResult(event.Result)

	var riichiSeats []tile.Seat
	for _, seat := range tile.Seats() {
		if r.Players[seat.Index()].Riichi.OK {
			riichiSeats = append(riichiSeats, seat)
		}
	}

	r.History = append(slices.Clip(r.History), play.FinishedRound{
		Header:      r.Header,
		Result:      CloneResult(event.Result),
		RiichiSeats: riichiSeats,
	})
	return r
}
