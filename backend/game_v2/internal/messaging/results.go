package messaging

import (
	"errors"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	yakumanHan   = 13
	paoShareAll  = "all"
	paoShareHalf = "half"
)

func roundEndFields(
	result play.RoundResult, scores [tile.SeatCount]int, riichiSticks int, record play.SeatRecord,
) (wire.Map, error) {
	if result == nil {
		return nil, errors.New("no round result to shape")
	}
	var before [tile.SeatCount]int
	for i, change := range result.TotalScoreChanges() {
		before[i] = scores[i] - change
	}

	var code wire.ResultType
	var fields wire.Map
	var err error
	honba := record.Header.Honba
	switch r := result.(type) {
	case play.Tsumo:
		code = wire.ResultTsumo
		fields, err = tsumoFields(r.Win, before, honba)
	case play.Ron:
		code = wire.ResultRon
		fields, err = ronFields(r, before, honba)
	case play.ExhaustiveDraw:
		code = wire.ResultExhaustiveDraw
		fields, err = exhaustiveDrawFields(r, before)
	case play.Abortive:
		code = wire.ResultAbortiveDraw
		fields, err = abortiveFields(r.Kind, before)
	}
	if err != nil {
		return nil, err
	}

	return append(wire.Map{
		{Key: wire.KeyResultType, Value: wire.Int(code)},
		{Key: wire.KeyRiichiSticks, Value: wire.Int(riichiSticks)},
		{Key: wire.KeyDealer, Value: seatValue(record.Header.Dealer)},
		{Key: wire.KeyDoraIndicators, Value: tilesValue(record.DoraIndicators)},
	}, fields...), nil
}

func tsumoFields(win play.WinResult, scores [tile.SeatCount]int, honba int) (wire.Map, error) {
	melds, err := packMelds(win.Winner, win.Melds)
	if err != nil {
		return nil, err
	}

	bonus := honba * engine.HonbaRonBonus
	m := wire.Map{
		{Key: wire.KeyWinnerSeat, Value: seatValue(win.Winner)},
		{Key: wire.KeyHandResult, Value: handResult(win, bonus)},
		{Key: wire.KeyScores, Value: scoreMap(scores)},
		{Key: wire.KeyScoreChanges, Value: scoreMap(win.ScoreChanges)},
		{Key: wire.KeyRiichiCollected, Value: wire.Int(collectedSticks(win))},
		{Key: wire.KeyClosedTiles, Value: tilesValue(win.Hand)},
		{Key: wire.KeyMelds, Value: melds},
		{Key: wire.KeyWinningTile, Value: tileValue(win.WinTile)},
		{Key: wire.KeyHonbaBonus, Value: scoreValue(bonus)},
	}
	return winExtras(m, win, bonus), nil
}

func ronFields(ron play.Ron, scores [tile.SeatCount]int, honba int) (wire.Map, error) {
	wins := make(wire.Array, 0, len(ron.Wins))
	winTile := tile.TileID{}
	for i, win := range ron.Wins {
		bonus := 0
		if i == 0 {
			bonus = honba * engine.HonbaRonBonus
		}
		shaped, err := ronWin(win, bonus)
		if err != nil {
			return nil, err
		}
		wins = append(wins, shaped)
		winTile = win.WinTile
	}

	m := wire.Map{
		{Key: wire.KeyLoserSeat, Value: seatValue(ron.Discarder)},
		{Key: wire.KeyWinningTile, Value: tileValue(winTile)},
		{Key: wire.KeyWinners, Value: wins},
		{Key: wire.KeyScores, Value: scoreMap(scores)},
		{Key: wire.KeyScoreChanges, Value: scoreMap(ron.TotalScoreChanges())},
	}
	if len(ron.HeadBumped) > 0 {
		m = append(m, wire.Field{Key: wire.KeyHeadBumpedSeats, Value: seatsValue(ron.HeadBumped)})
	}
	return m, nil
}

func ronWin(win play.WinResult, bonus int) (wire.Map, error) {
	melds, err := packMelds(win.Winner, win.Melds)
	if err != nil {
		return nil, err
	}

	m := wire.Map{
		{Key: wire.KeyWinnerSeat, Value: seatValue(win.Winner)},
		{Key: wire.KeyHandResult, Value: handResult(win, bonus)},
		{Key: wire.KeyScoreChanges, Value: scoreMap(win.ScoreChanges)},
		{Key: wire.KeyRiichiCollected, Value: wire.Int(collectedSticks(win))},
		{Key: wire.KeyClosedTiles, Value: tilesValue(win.Hand)},
		{Key: wire.KeyMelds, Value: melds},
		{Key: wire.KeyHonbaBonus, Value: scoreValue(bonus)},
	}
	return winExtras(m, win, bonus), nil
}

func winExtras(m wire.Map, win play.WinResult, bonus int) wire.Map {
	if win.Pao.OK {
		m = append(m,
			wire.Field{Key: wire.KeyPaoSeat, Value: seatValue(win.Pao.Value)},
			wire.Field{Key: wire.KeyPaoLiability, Value: paoLiability(win, bonus)})
	}
	if len(win.UraIndicators) > 0 {
		m = append(m, wire.Field{Key: wire.KeyUraDora, Value: tilesValue(win.UraIndicators)})
	}
	return m
}

func collectedSticks(win play.WinResult) int {
	moved := 0
	for _, change := range win.ScoreChanges {
		moved += change
	}
	return moved / engine.RiichiStickValue
}

func paoLiability(win play.WinResult, bonus int) wire.Map {
	var yaku wire.Array
	for _, id := range win.Yaku {
		if id == play.YakuDaisangen || id == play.YakuDaisuushii {
			yaku = append(yaku, wire.Int(id))
		}
	}
	share := paoShareAll
	if win.Loser.OK && win.Loser.Value != win.Pao.Value {
		share = paoShareHalf
	}
	return wire.Map{
		{Key: wire.KeyYaku, Value: yaku},
		{Key: wire.KeyPaoShare, Value: wire.Str(share)},
		{Key: wire.KeyPaysHonba, Value: wire.Bool(bonus > 0)},
	}
}

func handResult(win play.WinResult, bonus int) wire.Map {
	han, fu, yakumanCount := 0, 0, play.Option[int]{}
	switch v := win.Value.(type) {
	case play.Han:
		han, fu = v.Han, v.Fu
		if win.Limit == play.Some(play.LimitYakuman) {
			yakumanCount = play.Some(1)
		}
	case play.Yakuman:
		han, fu, yakumanCount = yakumanHan*v.Count, v.Fu.Value, play.Some(v.Count)
	}

	points := win.ScoreChanges[win.Winner.Index()] - bonus - collectedSticks(win)*engine.RiichiStickValue
	m := wire.Map{
		{Key: wire.KeyHan, Value: wire.Int(han)},
		{Key: wire.KeyFu, Value: wire.Int(fu)},
		{Key: wire.KeyYaku, Value: yakuList(win)},
		{Key: wire.KeyPoints, Value: scoreValue(points)},
		{Key: wire.KeyHandLimit, Value: wire.Str(limitName(win))},
	}
	return optionField(m, wire.KeyYakumanCount, yakumanCount, func(n int) wire.Value { return wire.Int(n) })
}

func limitName(win play.WinResult) string {
	if !win.Limit.OK {
		return wire.HandLimitNone
	}
	if _, counted := win.Value.(play.Han); counted && win.Limit.Value == play.LimitYakuman {
		return wire.HandLimitKazoeYakuman
	}
	return win.Limit.Value.String()
}

func yakuList(win play.WinResult) wire.Array {
	open := false
	for _, meld := range win.Melds {
		open = open || meld.Kind != play.MeldClosedKan
	}

	doraIDs := [...]int{wire.YakuIDDora, wire.YakuIDAkaDora, wire.YakuIDUraDora}
	counts := [len(doraIDs)]int{win.Dora.Dora, win.Dora.AkaDora, win.Dora.UraDora}
	list := make(wire.Array, 0, len(win.Yaku)+len(doraIDs))
	for _, id := range win.Yaku {
		list = append(list, yakuEntry(int(id), yakuHan(id, open), id.IsYakuman()))
	}
	for i, id := range doraIDs {
		if counts[i] > 0 {
			list = append(list, yakuEntry(id, counts[i], false))
		}
	}
	return list
}

func yakuHan(id play.YakuID, open bool) int {
	if id.IsYakuman() {
		return yakumanHan
	}
	if han, ok := id.HanOpen(); open && ok {
		return han
	}
	return id.HanClosed()
}

func yakuEntry(id, han int, yakuman bool) wire.Map {
	count := 0
	if yakuman {
		count = 1
	}
	return wire.Map{
		{Key: wire.KeyYakuID, Value: wire.Int(id)},
		{Key: wire.KeyHan, Value: wire.Int(han)},
		{Key: wire.KeyYakuYakumanCount, Value: wire.Int(count)},
	}
}

func shownHands(hands []play.ShownHand) (wire.Array, error) {
	shown := make(wire.Array, 0, len(hands))
	for _, hand := range hands {
		melds, err := packMelds(hand.Seat, hand.Melds)
		if err != nil {
			return nil, err
		}
		shown = append(shown, wire.Map{
			{Key: wire.KeySeat, Value: seatValue(hand.Seat)},
			{Key: wire.KeyClosedTiles, Value: tilesValue(hand.Hand)},
			{Key: wire.KeyMelds, Value: melds},
		})
	}
	return shown, nil
}

func riverValue(river []play.RiverTile) wire.Array {
	discards := make(wire.Array, 0, len(river))
	for _, discard := range river {
		discards = append(discards, wire.Map{
			{Key: wire.KeyTileID, Value: tileValue(discard.Tile)},
			{Key: wire.KeyTsumogiri, Value: wire.Bool(discard.Tsumogiri)},
			{Key: wire.KeyRiichiDiscard, Value: wire.Bool(discard.Riichi)},
		})
	}
	return discards
}

func exhaustiveDrawFields(draw play.ExhaustiveDraw, scores [tile.SeatCount]int) (wire.Map, error) {
	hands, err := shownHands(draw.Tenpai)
	if err != nil {
		return nil, err
	}

	var m wire.Map
	if len(draw.Nagashi) > 0 {
		seats := make([]tile.Seat, 0, len(draw.Nagashi))
		rivers := make(wire.Array, 0, len(draw.Nagashi))
		for _, nagashi := range draw.Nagashi {
			seats = append(seats, nagashi.Seat)
			rivers = append(rivers, wire.Map{
				{Key: wire.KeySeat, Value: seatValue(nagashi.Seat)},
				{Key: wire.KeyDiscards, Value: riverValue(nagashi.River)},
			})
		}
		m = wire.Map{
			{Key: wire.KeyQualifyingSeats, Value: seatsValue(seats)},
			{Key: wire.KeyQualifyingRivers, Value: rivers},
		}
	}

	tenpai, noten := tenpaiSeats(draw)
	return append(m,
		wire.Field{Key: wire.KeyTenpaiSeats, Value: seatsValue(tenpai)},
		wire.Field{Key: wire.KeyNotenSeats, Value: seatsValue(noten)},
		wire.Field{Key: wire.KeyTenpaiHands, Value: hands},
		wire.Field{Key: wire.KeyScores, Value: scoreMap(scores)},
		wire.Field{Key: wire.KeyScoreChanges, Value: scoreMap(draw.ScoreChanges)},
	), nil
}

func tenpaiSeats(draw play.ExhaustiveDraw) (tenpai, noten []tile.Seat) {
	var isTenpai [tile.SeatCount]bool
	for _, hand := range draw.Tenpai {
		isTenpai[hand.Seat.Index()] = true
	}
	for _, s := range tile.Seats() {
		if isTenpai[s.Index()] {
			tenpai = append(tenpai, s)
		} else {
			noten = append(noten, s)
		}
	}
	return tenpai, noten
}

func abortReason(kind play.AbortKind) (wire.AbortReason, bool) {
	switch kind.(type) {
	case play.KyuushuKyuuhai:
		return wire.AbortNineTerminals, true
	case play.FourWinds:
		return wire.AbortFourWinds, true
	case play.FourRiichi:
		return wire.AbortFourRiichi, true
	case play.FourKans:
		return wire.AbortFourKans, true
	case play.TripleRon:
		return wire.AbortTripleRon, true
	}
	return "", false
}

func abortiveFields(kind play.AbortKind, scores [tile.SeatCount]int) (wire.Map, error) {
	reason, ok := abortReason(kind)
	if !ok {
		return nil, errors.New("no abort kind to shape")
	}
	m := wire.Map{
		{Key: wire.KeyAbortiveReason, Value: wire.Str(reason)},
		{Key: wire.KeyScores, Value: scoreMap(scores)},
		{Key: wire.KeyScoreChanges, Value: scoreMap([tile.SeatCount]int{})},
	}

	var hands []play.ShownHand
	switch k := kind.(type) {
	case play.KyuushuKyuuhai:
		m = append(m, wire.Field{Key: wire.KeySeat, Value: seatValue(k.Seat)})
		hands = []play.ShownHand{{Seat: k.Seat, Hand: k.Hand}}
	case play.FourRiichi:
		hands = k.Hands
	case play.TripleRon:
		callers := make([]tile.Seat, 0, len(k.Hands))
		for _, hand := range k.Hands {
			callers = append(callers, hand.Seat)
		}
		m = append(m, wire.Field{Key: wire.KeyRonCallers, Value: seatsValue(callers)})
		hands = k.Hands
	case play.FourWinds, play.FourKans:
	}
	if len(hands) == 0 {
		return m, nil
	}

	shown, err := shownHands(hands)
	if err != nil {
		return nil, err
	}
	return append(m, wire.Field{Key: wire.KeyShownHands, Value: shown}), nil
}

func historyEntry(round play.FinishedRound) wire.Map {
	m := wire.Map{
		{Key: wire.KeyWind, Value: wire.Int(round.Header.Wind)},
		{Key: wire.KeyDealer, Value: seatValue(round.Header.Dealer)},
		{Key: wire.KeyHonba, Value: wire.Int(round.Header.Honba)},
	}

	var winners, pao []tile.Seat
	var loser play.Option[tile.Seat]
	var tenpai play.Option[[]tile.Seat]
	switch r := round.Result.(type) {
	case play.Tsumo:
		m = append(m, wire.Field{Key: wire.KeyResultType, Value: wire.Int(wire.ResultTsumo)})
		winners, pao = []tile.Seat{r.Win.Winner}, paoSeats([]play.WinResult{r.Win})
	case play.Ron:
		m = append(m, wire.Field{Key: wire.KeyResultType, Value: wire.Int(wire.ResultRon)})
		for _, win := range r.Wins {
			winners = append(winners, win.Winner)
		}
		loser, pao = play.Some(r.Discarder), paoSeats(r.Wins)
	case play.ExhaustiveDraw:
		m = append(m, wire.Field{Key: wire.KeyResultType, Value: wire.Int(wire.ResultExhaustiveDraw)})
		seats, _ := tenpaiSeats(r)
		tenpai = play.Some(seats)
	case play.Abortive:
		reason, _ := abortReason(r.Kind)
		m = append(m,
			wire.Field{Key: wire.KeyResultType, Value: wire.Int(wire.ResultAbortiveDraw)},
			wire.Field{Key: wire.KeyAbortiveReason, Value: wire.Str(reason)})
	}

	m = append(m,
		wire.Field{Key: wire.KeyRiichiSeats, Value: seatsValue(round.RiichiSeats)},
		wire.Field{Key: wire.KeyWinnerSeat, Value: seatsValue(winners)})
	m = optionField(m, wire.KeyLoserSeat, loser, func(s tile.Seat) wire.Value { return seatValue(s) })
	m = append(m, wire.Field{Key: wire.KeyPaoSeat, Value: seatsValue(pao)})
	m = optionField(m, wire.KeyTenpaiSeats, tenpai, func(s []tile.Seat) wire.Value { return seatsValue(s) })
	var changes [tile.SeatCount]int
	if round.Result != nil {
		changes = round.Result.TotalScoreChanges()
	}
	return append(m, wire.Field{Key: wire.KeyScoreChanges, Value: scoreMap(changes)})
}

func paoSeats(wins []play.WinResult) []tile.Seat {
	var liable [tile.SeatCount]bool
	for _, win := range wins {
		if win.Pao.OK {
			liable[win.Pao.Value.Index()] = true
		}
	}
	var seats []tile.Seat
	for _, s := range tile.Seats() {
		if liable[s.Index()] {
			seats = append(seats, s)
		}
	}
	return seats
}
