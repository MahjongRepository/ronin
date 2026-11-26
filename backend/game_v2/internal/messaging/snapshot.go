package messaging

import (
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func ReconnectionPayload(
	record play.SeatRecord, roster Roster, standIns [tile.SeatCount]play.Option[wire.SeatControlReason],
) (wire.Map, error) {
	players, err := playerStates(record.Players)
	if err != nil {
		return nil, err
	}

	header := record.Header
	m := wire.Map{
		{Key: wire.KeyGameID, Value: wire.Str(roster.GameID)},
		{Key: wire.KeyGameType, Value: wire.Int(wire.GameHanchan)},
		{Key: wire.KeyPlayers, Value: rosterPlayers(roster, standIns)},
		{Key: wire.KeyDealer, Value: seatValue(header.Dealer)},
		{Key: wire.KeyFirstDealer, Value: seatValue(record.FirstDealer)},
		{Key: wire.KeyDealerDice, Value: dealerDice(record.FirstDealerDice)},
		{Key: wire.KeyRiichiStickValue, Value: scoreValue(record.RiichiStickValue)},
		{Key: wire.KeySeat, Value: seatValue(record.Seat)},
		{Key: wire.KeyWind, Value: wire.Int(header.Wind)},
		{Key: wire.KeyRoundNumber, Value: wire.Int(header.RoundNumber)},
		{Key: wire.KeyRoundInWind, Value: wire.Int(header.RoundInWind)},
		{Key: wire.KeyCurrentPlayer, Value: seatValue(record.Current)},
	}
	m = optionField(m, wire.KeyLatestDiscardSeat, record.LatestDiscard, func(s tile.Seat) wire.Value {
		return seatValue(s)
	})

	m = append(m,
		wire.Field{Key: wire.KeyDoraIndicators, Value: tilesValue(record.DoraIndicators)},
		wire.Field{Key: wire.KeyHonba, Value: wire.Int(header.Honba)},
		wire.Field{Key: wire.KeyRiichiSticks, Value: wire.Int(record.RiichiSticks)},
		wire.Field{Key: wire.KeyMyTiles, Value: tilesValue(record.Hand)},
		wire.Field{Key: wire.KeyDice, Value: diceValue(header.Dice)},
		wire.Field{Key: wire.KeyTilesRemaining, Value: wire.Int(record.LiveTiles)},
		wire.Field{Key: wire.KeyPlayerStates, Value: players},
		wire.Field{Key: wire.KeyFuriten, Value: wire.Bool(record.Furiten)},
		wire.Field{Key: wire.KeyRoundHistory, Value: roundHistory(record.History)},
	)
	if record.Result == nil {
		return m, nil
	}

	var scores [tile.SeatCount]int
	for i, player := range record.Players {
		scores[i] = player.Score
	}

	result, err := roundEndFields(record.Result, scores, record.RiichiSticks, record)
	if err != nil {
		return nil, err
	}

	return append(m, wire.Field{Key: wire.KeyRoundResult, Value: result}), nil
}

func playerStates(players [tile.SeatCount]play.PublicSeat) (wire.Array, error) {
	states := make(wire.Array, 0, len(players))
	for _, player := range players {
		melds, err := packMelds(player.Seat, player.Melds)
		if err != nil {
			return nil, err
		}

		state := wire.Map{
			{Key: wire.KeySeat, Value: seatValue(player.Seat)},
			{Key: wire.KeyScore, Value: scoreValue(player.Score)},
			{Key: wire.KeyDiscards, Value: riverValue(player.River)},
			{Key: wire.KeyMelds, Value: melds},
			{Key: wire.KeyIsRiichi, Value: wire.Bool(player.Riichi.OK)},
			{Key: wire.KeyTileCount, Value: wire.Int(player.ClosedTiles)},
		}
		states = append(states, optionField(state, wire.KeyPaoSeat, player.Pao, func(s tile.Seat) wire.Value {
			return seatValue(s)
		}))
	}

	return states, nil
}

func roundHistory(history []play.FinishedRound) wire.Array {
	entries := make(wire.Array, 0, len(history))
	for _, round := range history {
		entries = append(entries, historyEntry(round))
	}

	return entries
}
