package messaging_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func endedRound(honba int, dora ...int) play.SeatRecord {
	return play.SeatRecord{
		Header:         play.RoundHeader{Dealer: tile.Seats()[3], Honba: honba},
		DoraIndicators: idsOf(dora),
	}
}

func idsOf(ns []int) []tile.TileID {
	got := make([]tile.TileID, 0, len(ns))
	for _, n := range ns {
		got = append(got, tile.AllTileIDs()[n])
	}

	return got
}

func roundEnd(result play.RoundResult, riichiSticks int, scoreList ...int) play.RoundEnded {
	return play.RoundEnded{Result: result, Scores: [tile.SeatCount]int(scoreList), RiichiSticks: riichiSticks}
}

func handResult(t *testing.T, win wire.Map) wire.Map {
	t.Helper()
	return field(t, win, wire.KeyHandResult).(wire.Map)
}

func yakuEntry(id, han, yakuman int) wire.Map {
	return wire.Map{
		{Key: wire.KeyYakuID, Value: wire.Int(id)},
		{Key: wire.KeyHan, Value: wire.Int(han)},
		{Key: wire.KeyYakuYakumanCount, Value: wire.Int(yakuman)},
	}
}

func TestRoundEndPayload_WhenATsumoHasNoPaoOrUra_ShouldOmitThemAndNameTheScoresBeforePayment(t *testing.T) {
	win := play.WinResult{
		Winner: seat(t, 0), Hand: ids(t, 0, 1, 2), WinTile: id(t, 3), Value: play.Han{Han: 1, Fu: 30},
		Yaku: []play.YakuID{play.YakuTsumo}, ScoreChanges: [tile.SeatCount]int{1100, -500, -300, -300},
	}

	m := payload(t, roundEnd(play.Tsumo{Win: win}, 0, 26100, 24500, 24700, 24700), endedRound(0, 5, 9))

	assertMap(t, "tsumo", m, wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(4)},
		{Key: wire.KeyResultType, Value: wire.Int(0)},
		{Key: wire.KeyRiichiSticks, Value: wire.Int(0)},
		{Key: wire.KeyDealer, Value: wire.Int(3)},
		{Key: wire.KeyDoraIndicators, Value: intArray(5, 9)},
		{Key: wire.KeyWinnerSeat, Value: wire.Int(0)},
		{Key: wire.KeyHandResult, Value: wire.Map{
			{Key: wire.KeyHan, Value: wire.Int(1)},
			{Key: wire.KeyFu, Value: wire.Int(30)},
			{Key: wire.KeyYaku, Value: wire.Array{yakuEntry(0, 1, 0)}},
			{Key: wire.KeyPoints, Value: wire.Int(11)},
			{Key: wire.KeyHandLimit, Value: wire.Str("none")},
		}},
		{Key: wire.KeyScores, Value: scores(250, 250, 250, 250)},
		{Key: wire.KeyScoreChanges, Value: scores(11, -5, -3, -3)},
		{Key: wire.KeyRiichiCollected, Value: wire.Int(0)},
		{Key: wire.KeyClosedTiles, Value: intArray(0, 1, 2)},
		{Key: wire.KeyMelds, Value: wire.Array{}},
		{Key: wire.KeyWinningTile, Value: wire.Int(3)},
		{Key: wire.KeyHonbaBonus, Value: wire.Int(0)},
	})
}

func TestRoundEndPayload_WhenAYakumanTsumoHasPaoHonbaAndUra_ShouldNameWhatTheLiableSeatPays(t *testing.T) {
	win := play.WinResult{
		Winner: seat(t, 0), Hand: ids(t, 0, 1, 2), WinTile: id(t, 3), Value: play.Yakuman{Count: 1, Fu: play.Some(30)},
		Limit: play.Some(play.LimitYakuman), Yaku: []play.YakuID{play.YakuDaisangen}, UraIndicators: ids(t, 10),
		Pao: play.Some(seat(t, 2)), ScoreChanges: [tile.SeatCount]int{32600 + 2000, 0, -32600, 0},
	}

	m := payload(t, roundEnd(play.Tsumo{Win: win}, 0, 59600, 25000, -7600, 25000), endedRound(2))

	assertMap(t, "hand result", handResult(t, m), wire.Map{
		{Key: wire.KeyHan, Value: wire.Int(13)},
		{Key: wire.KeyFu, Value: wire.Int(30)},
		{Key: wire.KeyYaku, Value: wire.Array{yakuEntry(103, 13, 1)}},
		{Key: wire.KeyPoints, Value: wire.Int(320)},
		{Key: wire.KeyHandLimit, Value: wire.Str("yakuman")},
		{Key: wire.KeyYakumanCount, Value: wire.Int(1)},
	})
	for _, c := range []struct {
		key  wire.Key
		want wire.Value
	}{
		{wire.KeyRiichiCollected, wire.Int(2)},
		{wire.KeyHonbaBonus, wire.Int(6)},
		{wire.KeyPaoSeat, wire.Int(2)},
		{wire.KeyPaoLiability, wire.Map{
			{Key: wire.KeyYaku, Value: intArray(103)},
			{Key: wire.KeyPaoShare, Value: wire.Str("all")},
			{Key: wire.KeyPaysHonba, Value: wire.Bool(true)},
		}},
		{wire.KeyUraDora, intArray(10)},
	} {
		t.Run(c.key.String(), func(t *testing.T) {
			assertMap(t, c.key.String(), wire.Map{{Key: c.key, Value: field(t, m, c.key)}}, wire.Map{{Key: c.key, Value: c.want}})
		})
	}
}

func TestRoundEndPayload_WhenARonHasTwoWins_ShouldGiveTheCloserWinnerTheHonbaAndSticksOnly(t *testing.T) {
	closer := play.WinResult{
		Winner: seat(t, 2), Loser: play.Some(seat(t, 1)), WinTile: id(t, 50), Value: play.Han{Han: 2, Fu: 30},
		Yaku: []play.YakuID{play.YakuRiichi}, Dora: play.DoraCount{UraDora: 1}, UraIndicators: ids(t, 30),
		ScoreChanges: [tile.SeatCount]int{0, -2300, 2300 + 1000, 0},
	}
	farther := play.WinResult{
		Winner: seat(t, 3), Loser: play.Some(seat(t, 1)), WinTile: id(t, 50), Value: play.Han{Han: 3, Fu: 40},
		Melds: []play.MeldView{{
			Kind: play.MeldPon, Tiles: ids(t, 108, 109, 110), Called: play.Some(id(t, 108)), From: play.Some(seat(t, 0)),
		}},
		Yaku: []play.YakuID{play.YakuHonitsu, play.YakuHaku}, ScoreChanges: [tile.SeatCount]int{0, -5200, 0, 5200},
	}
	ron := play.Ron{Discarder: seat(t, 1), Wins: []play.WinResult{closer, farther}}

	m := payload(t, roundEnd(ron, 0, 25000, 17500, 28300, 30200), endedRound(1))

	if got, want := keys(m), []wire.Key{
		wire.KeyEventType, wire.KeyResultType, wire.KeyRiichiSticks, wire.KeyDealer, wire.KeyDoraIndicators,
		wire.KeyLoserSeat, wire.KeyWinningTile, wire.KeyWinners, wire.KeyScores, wire.KeyScoreChanges,
	}; !slices.Equal(got, want) {
		t.Errorf("ron keys = %v, want %v", got, want)
	}
	assertMap(t, "total changes", wire.Map{{Key: wire.KeyScoreChanges, Value: field(t, m, wire.KeyScoreChanges)}},
		wire.Map{{Key: wire.KeyScoreChanges, Value: scores(0, -75, 33, 52)}})
	wins := field(t, m, wire.KeyWinners).(wire.Array)
	first, second := wins[0].(wire.Map), wins[1].(wire.Map)
	if got, want := keys(first), []wire.Key{
		wire.KeyWinnerSeat, wire.KeyHandResult, wire.KeyScoreChanges, wire.KeyRiichiCollected, wire.KeyClosedTiles,
		wire.KeyMelds, wire.KeyHonbaBonus, wire.KeyUraDora,
	}; !slices.Equal(got, want) {
		t.Errorf("closer win keys = %v, want %v", got, want)
	}
	for _, c := range []struct {
		name string
		got  wire.Value
		want wire.Value
	}{
		{"closer honba", field(t, first, wire.KeyHonbaBonus), wire.Int(3)},
		{"closer sticks", field(t, first, wire.KeyRiichiCollected), wire.Int(1)},
		{"closer points", field(t, handResult(t, first), wire.KeyPoints), wire.Int(20)},
		{"closer yaku", field(t, handResult(t, first), wire.KeyYaku), wire.Array{yakuEntry(1, 1, 0), yakuEntry(122, 1, 0)}},
		{"farther honba", field(t, second, wire.KeyHonbaBonus), wire.Int(0)},
		{"farther sticks", field(t, second, wire.KeyRiichiCollected), wire.Int(0)},
		{"farther open yaku", field(t, handResult(t, second), wire.KeyYaku), wire.Array{yakuEntry(36, 2, 0), yakuEntry(15, 1, 0)}},
	} {
		t.Run(c.name, func(t *testing.T) {
			assertMap(t, c.name, wire.Map{{Key: wire.KeyHan, Value: c.got}}, wire.Map{{Key: wire.KeyHan, Value: c.want}})
		})
	}
	if _, ok := second.Get(wire.KeyUraDora); ok {
		t.Error("the farther win names ura dora it never counted")
	}
}

func TestRoundEndPayload_WhenARonOfAnotherSeatHasPao_ShouldNameAHalfShare(t *testing.T) {
	win := play.WinResult{
		Winner: seat(t, 0), Loser: play.Some(seat(t, 1)), WinTile: id(t, 3), Value: play.Yakuman{Count: 2},
		Limit: play.Some(play.LimitYakuman), Yaku: []play.YakuID{play.YakuDaisangen, play.YakuTsuuiisou},
		Pao: play.Some(seat(t, 2)), ScoreChanges: [tile.SeatCount]int{64000, -32000, -32000, 0},
	}

	m := payload(t, roundEnd(play.Ron{Discarder: seat(t, 1), Wins: []play.WinResult{win}}, 0, 89000, -7000, -7000, 25000), endedRound(0))

	only := field(t, m, wire.KeyWinners).(wire.Array)[0].(wire.Map)
	assertMap(t, "pao", wire.Map{{Key: wire.KeyPaoLiability, Value: field(t, only, wire.KeyPaoLiability)}}, wire.Map{
		{Key: wire.KeyPaoLiability, Value: wire.Map{
			{Key: wire.KeyYaku, Value: intArray(103)},
			{Key: wire.KeyPaoShare, Value: wire.Str("half")},
			{Key: wire.KeyPaysHonba, Value: wire.Bool(false)},
		}},
	})
	assertMap(t, "double yakuman hand", handResult(t, only), wire.Map{
		{Key: wire.KeyHan, Value: wire.Int(26)},
		{Key: wire.KeyFu, Value: wire.Int(0)},
		{Key: wire.KeyYaku, Value: wire.Array{yakuEntry(103, 13, 1), yakuEntry(107, 13, 1)}},
		{Key: wire.KeyPoints, Value: wire.Int(640)},
		{Key: wire.KeyHandLimit, Value: wire.Str("yakuman")},
		{Key: wire.KeyYakumanCount, Value: wire.Int(2)},
	})
}

func TestRoundEndPayload_WhenAHandIsPaidAtALimit_ShouldNameTheLimitAndKazoeApart(t *testing.T) {
	for _, c := range []struct {
		name    string
		value   play.Value
		limit   play.Option[play.Limit]
		want    string
		yakuman play.Option[int]
	}{
		{"mangan", play.Han{Han: 5, Fu: 30}, play.Some(play.LimitMangan), "mangan", play.Option[int]{}},
		{"kazoe yakuman", play.Han{Han: 13, Fu: 40}, play.Some(play.LimitYakuman), "kazoe_yakuman", play.Some(1)},
		{"double yakuman", play.Yakuman{Count: 2}, play.Some(play.LimitYakuman), "yakuman", play.Some(2)},
	} {
		t.Run(c.name, func(t *testing.T) {
			win := play.WinResult{Winner: seat(t, 0), Value: c.value, Limit: c.limit, ScoreChanges: [tile.SeatCount]int{12000, -4000, -4000, -4000}}

			hand := handResult(t, payload(t, roundEnd(play.Tsumo{Win: win}, 0, 37000, 21000, 21000, 21000), endedRound(0)))

			count, hasCount := hand.Get(wire.KeyYakumanCount)
			if field(t, hand, wire.KeyHandLimit) != wire.Str(c.want) || hasCount != c.yakuman.OK ||
				(hasCount && count != wire.Int(c.yakuman.Value)) {
				t.Errorf("%s: hand result = %v, want limit %q and yakuman count %v", c.name, hand, c.want, c.yakuman)
			}
		})
	}
}

func TestRoundEndPayload_WhenAnExhaustiveDrawHasANagashi_ShouldLeadWithTheQualifyingRivers(t *testing.T) {
	draw := play.ExhaustiveDraw{
		Tenpai: []play.ShownHand{{Seat: seat(t, 2), Hand: ids(t, 0, 1, 2)}},
		Nagashi: []play.NagashiRiver{{Seat: seat(t, 1), River: []play.RiverTile{
			{Tile: id(t, 0), Tsumogiri: true}, {Tile: id(t, 135), Riichi: true},
		}}},
		ScoreChanges: [tile.SeatCount]int{-4000, 8000, -2000, -2000},
	}

	m := payload(t, roundEnd(draw, 1, 21000, 33000, 23000, 22000), endedRound(0))

	assertMap(t, "nagashi", m[5:], wire.Map{
		{Key: wire.KeyQualifyingSeats, Value: intArray(1)},
		{Key: wire.KeyQualifyingRivers, Value: wire.Array{wire.Map{
			{Key: wire.KeySeat, Value: wire.Int(1)},
			{Key: wire.KeyDiscards, Value: wire.Array{
				wire.Map{
					{Key: wire.KeyTileID, Value: wire.Int(0)},
					{Key: wire.KeyTsumogiri, Value: wire.Bool(true)},
					{Key: wire.KeyRiichiDiscard, Value: wire.Bool(false)},
				},
				wire.Map{
					{Key: wire.KeyTileID, Value: wire.Int(135)},
					{Key: wire.KeyTsumogiri, Value: wire.Bool(false)},
					{Key: wire.KeyRiichiDiscard, Value: wire.Bool(true)},
				},
			}},
		}}},
		{Key: wire.KeyTenpaiSeats, Value: intArray(2)},
		{Key: wire.KeyNotenSeats, Value: intArray(0, 1, 3)},
		{Key: wire.KeyTenpaiHands, Value: wire.Array{wire.Map{
			{Key: wire.KeySeat, Value: wire.Int(2)},
			{Key: wire.KeyClosedTiles, Value: intArray(0, 1, 2)},
			{Key: wire.KeyMelds, Value: wire.Array{}},
		}}},
		{Key: wire.KeyScores, Value: scores(250, 250, 250, 240)},
		{Key: wire.KeyScoreChanges, Value: scores(-40, 80, -20, -20)},
	})
}

func TestRoundEndPayload_WhenARoundIsAborted_ShouldShowTheHandsThatCausedItSortedNotInDrawOrder(t *testing.T) {
	kyuushuHand := ids(t, 0, 32, 36, 68, 72, 104, 108, 112, 116, 120, 124, 128, 132, 1)
	riichiHands := []play.ShownHand{{Seat: seat(t, 0), Hand: ids(t, 4)}, {Seat: seat(t, 1), Hand: ids(t, 5)}}
	ronHands := []play.ShownHand{{Seat: seat(t, 3), Hand: ids(t, 6)}, {Seat: seat(t, 0), Hand: ids(t, 7)}}
	shown := func(hands ...wire.Value) wire.Field {
		return wire.Field{Key: wire.KeyShownHands, Value: wire.Array(hands)}
	}

	hand := func(s int, tiles wire.Array) wire.Map {
		return wire.Map{
			{Key: wire.KeySeat, Value: wire.Int(s)},
			{Key: wire.KeyClosedTiles, Value: tiles},
			{Key: wire.KeyMelds, Value: wire.Array{}},
		}
	}

	head := func(reason string) wire.Map {
		return wire.Map{
			{Key: wire.KeyAbortiveReason, Value: wire.Str(reason)},
			{Key: wire.KeyScores, Value: scores(250, 250, 250, 250)},
			{Key: wire.KeyScoreChanges, Value: scores(0, 0, 0, 0)},
		}
	}

	for _, c := range []struct {
		kind play.AbortKind
		want wire.Map
	}{
		{play.KyuushuKyuuhai{Seat: seat(t, 2), Hand: kyuushuHand}, append(head("nine_terminals"),
			wire.Field{Key: wire.KeySeat, Value: wire.Int(2)},
			shown(hand(2, intArray(0, 1, 32, 36, 68, 72, 104, 108, 112, 116, 120, 124, 128, 132))))},
		{play.FourWinds{}, head("four_winds")},
		{play.FourKans{}, head("four_kans")},
		{play.FourRiichi{Hands: riichiHands}, append(head("four_riichi"), shown(hand(0, intArray(4)), hand(1, intArray(5))))},
		{play.TripleRon{Discarder: seat(t, 2), Tile: id(t, 9), Hands: ronHands, RobbedKan: play.Some(play.KanAdded)}, append(head("triple_ron"),
			wire.Field{Key: wire.KeyRonCallers, Value: intArray(3, 0)},
			shown(hand(3, intArray(6)), hand(0, intArray(7))))},
	} {
		reason := string(field(t, c.want, wire.KeyAbortiveReason).(wire.Str))
		t.Run(reason, func(t *testing.T) {
			m := payload(t, roundEnd(play.Abortive{Kind: c.kind}, 0, 25000, 25000, 25000, 25000), endedRound(0))
			assertMap(t, reason, m[5:], c.want)
		})
	}
}
