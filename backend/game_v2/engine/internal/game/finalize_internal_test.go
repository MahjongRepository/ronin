package game

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func seat(t *testing.T, n int) tile.Seat {
	t.Helper()
	got, ok := tile.NewSeat(n)
	if !ok {
		t.Fatalf("NewSeat(%d) refused", n)
	}
	return got
}

func tsumo(t *testing.T, winner int) play.RoundResult {
	t.Helper()
	return play.Tsumo{Win: play.WinResult{Winner: seat(t, winner)}}
}

func ron(t *testing.T, winners []int, discarder int) play.RoundResult {
	t.Helper()
	wins := make([]play.WinResult, 0, len(winners))
	for _, winner := range winners {
		wins = append(wins, play.WinResult{Winner: seat(t, winner)})
	}
	return play.Ron{Discarder: seat(t, discarder), Wins: wins}
}

func drawWithNagashi(t *testing.T, tenpaiSeats []int, nagashi []play.NagashiRiver) play.RoundResult {
	t.Helper()
	tenpai := make([]play.ShownHand, 0, len(tenpaiSeats))
	for _, n := range tenpaiSeats {
		tenpai = append(tenpai, play.ShownHand{Seat: seat(t, n)})
	}
	return play.ExhaustiveDraw{Tenpai: tenpai, Nagashi: nagashi}
}

func draw(t *testing.T, tenpaiSeats []int) play.RoundResult {
	t.Helper()
	return drawWithNagashi(t, tenpaiSeats, nil)
}

func nagashi(t *testing.T, tenpaiSeats []int) play.RoundResult {
	t.Helper()
	return drawWithNagashi(t, tenpaiSeats, []play.NagashiRiver{{Seat: seat(t, 1)}})
}

func abortive() play.RoundResult {
	return play.Abortive{Kind: play.FourWinds{}}
}

func at(t *testing.T, uniqueDealers int, wind tile.Wind, dealer, honba int) position {
	t.Helper()
	return position{dealer: seat(t, dealer), wind: wind, uniqueDealers: uniqueDealers, honba: honba}
}

func eastOne(t *testing.T, honba int) position {
	t.Helper()
	return at(t, 1, tile.East, 0, honba)
}

type rotation struct {
	honba   int
	rotated bool
}

func rotationAfter(before position, result play.RoundResult) rotation {
	after := before.after(result)
	return rotation{honba: after.honba, rotated: after.dealer != before.dealer}
}

type ending struct {
	cause play.GameEndCause
	ends  bool
}

func playsOn() ending {
	return ending{}
}

func endsBy(cause play.GameEndCause) ending {
	return ending{cause: cause, ends: true}
}

func causeAfter(t *testing.T, ended position, result play.RoundResult, scores [tile.SeatCount]int) ending {
	t.Helper()
	cause, ends := gameEndCause(ended, ended.after(result), result, scores, seat(t, 0))
	return ending{cause: cause, ends: ends}
}

func TestPositionAfter_WhenTheDealerWinsByTsumo_ShouldKeepTheDealAndAddHonba(t *testing.T) {
	next := eastOne(t, 0).after(tsumo(t, 0))
	if next.dealer != seat(t, 0) || next.uniqueDealers != 1 || next.honba != 1 {
		t.Errorf("after = %+v, want dealer 0, 1 unique dealer, 1 honba", next)
	}
}

func TestPositionAfter_WhenTheDealerWinsByRon_ShouldKeepTheDealAndAddHonba(t *testing.T) {
	if got := rotationAfter(eastOne(t, 0), ron(t, []int{0}, 1)); got != (rotation{honba: 1}) {
		t.Errorf("rotation = %+v, want 1 honba kept", got)
	}
}

func TestPositionAfter_WhenTheDealerWinsInADoubleRon_ShouldKeepTheDealAndAddHonba(t *testing.T) {
	if got := rotationAfter(eastOne(t, 2), ron(t, []int{0, 2}, 1)); got != (rotation{honba: 3}) {
		t.Errorf("rotation = %+v, want 3 honba kept", got)
	}
}

func TestPositionAfter_WhenTheDealerIsTenpaiAtADraw_ShouldKeepTheDealAndAddHonba(t *testing.T) {
	if got := rotationAfter(eastOne(t, 1), draw(t, []int{0, 1})); got != (rotation{honba: 2}) {
		t.Errorf("rotation = %+v, want 2 honba kept", got)
	}
}

func TestPositionAfter_WhenTheDealerIsNotenAtADraw_ShouldPassTheDealOnAndAddHonba(t *testing.T) {
	next := eastOne(t, 1).after(draw(t, []int{1, 2}))
	if next.dealer != seat(t, 1) || next.honba != 2 {
		t.Errorf("after = %+v, want dealer 1, 2 honba", next)
	}
}

func TestPositionAfter_WhenTheRoundIsAborted_ShouldKeepTheDealAndAddHonba(t *testing.T) {
	if got := rotationAfter(eastOne(t, 0), abortive()); got != (rotation{honba: 1}) {
		t.Errorf("rotation = %+v, want 1 honba kept", got)
	}
}

func TestPositionAfter_WhenANonDealerWinsByTsumo_ShouldPassTheDealOnAndResetHonba(t *testing.T) {
	next := eastOne(t, 3).after(tsumo(t, 2))
	if next.dealer != seat(t, 1) || next.uniqueDealers != 2 || next.honba != 0 {
		t.Errorf("after = %+v, want dealer 1, 2 unique dealers, 0 honba", next)
	}
}

func TestPositionAfter_WhenANonDealerWinsByRon_ShouldPassTheDealOnAndResetHonba(t *testing.T) {
	if got := rotationAfter(eastOne(t, 1), ron(t, []int{1}, 3)); got != (rotation{rotated: true}) {
		t.Errorf("rotation = %+v, want 0 honba rotated", got)
	}
}

func TestPositionAfter_WhenADoubleRonLeavesOutTheDealer_ShouldPassTheDealOnAndResetHonba(t *testing.T) {
	if got := rotationAfter(eastOne(t, 2), ron(t, []int{1, 3}, 2)); got != (rotation{rotated: true}) {
		t.Errorf("rotation = %+v, want 0 honba rotated", got)
	}
}

func TestPositionAfter_WhenEverySeatIsNotenAtADraw_ShouldPassTheDealOnAndAddHonba(t *testing.T) {
	if got := rotationAfter(eastOne(t, 0), draw(t, nil)); got != (rotation{honba: 1, rotated: true}) {
		t.Errorf("rotation = %+v, want 1 honba rotated", got)
	}
}

func TestPositionAfter_WhenTheDealerAtSeatThreePassesTheDeal_ShouldWrapToSeatZeroInSouth(t *testing.T) {
	next := at(t, 4, tile.East, 3, 0).after(tsumo(t, 1))
	if next.dealer != seat(t, 0) || next.wind != tile.South {
		t.Errorf("after = %+v, want dealer 0 in South", next)
	}
}

func TestPositionAfter_WhenNagashiManganPaysWithTheDealerTenpai_ShouldKeepTheDealAndAddHonba(t *testing.T) {
	if got := rotationAfter(eastOne(t, 2), nagashi(t, []int{0, 1})); got != (rotation{honba: 3}) {
		t.Errorf("rotation = %+v, want 3 honba kept", got)
	}
}

func TestPositionAfter_WhenNagashiManganPaysWithTheDealerNoten_ShouldPassTheDealOnAndAddHonba(t *testing.T) {
	if got := rotationAfter(eastOne(t, 0), nagashi(t, []int{1})); got != (rotation{honba: 1, rotated: true}) {
		t.Errorf("rotation = %+v, want 1 honba rotated", got)
	}
}

func TestPositionAfter_WhenTheDealRepeats_ShouldStillCountTheRound(t *testing.T) {
	renchan := eastOne(t, 0).after(abortive())
	if got := renchan.after(tsumo(t, 1)).roundNumber; got != 2 {
		t.Errorf("round number = %d, want 2", got)
	}
}

func TestPositionAfter_WhenTheDealPassesToTheNinthToTwelfthDealer_ShouldPlayWest(t *testing.T) {
	for uniqueDealers := 8; uniqueDealers < 12; uniqueDealers++ {
		dealer := (uniqueDealers - 1) % tile.SeatCount
		ended := at(t, uniqueDealers, windOf(uniqueDealers), dealer, 0)
		next := ended.after(tsumo(t, (dealer+1)%tile.SeatCount))
		if next.uniqueDealers != uniqueDealers+1 || next.dealer != ended.dealer.Next() || next.wind != tile.West {
			t.Errorf("after %d unique dealers = %+v, want the next dealer in West", uniqueDealers, next)
		}
	}
}

func TestGameEndCause_WhenEastEnds_ShouldPlayOn(t *testing.T) {
	ended := at(t, 4, tile.East, 3, 0)
	if got := causeAfter(t, ended, draw(t, nil), [tile.SeatCount]int{35000, 35000, 35000, 35000}); got != playsOn() {
		t.Errorf("end = %+v, want play on", got)
	}
}

func TestGameEndCause_WhenSouthEndsWithASeatAtTheThreshold_ShouldEndByLength(t *testing.T) {
	ended := at(t, 8, tile.South, 3, 0)
	got := causeAfter(t, ended, draw(t, nil), [tile.SeatCount]int{35000, 21667, 21667, 21666})
	if got != endsBy(play.EndLength) {
		t.Errorf("end = %+v, want by length", got)
	}
}

func TestGameEndCause_WhenAScoreFallsBelowZero_ShouldEndByTobi(t *testing.T) {
	got := causeAfter(t, eastOne(t, 0), tsumo(t, 1), [tile.SeatCount]int{33367, 33367, 33366, -100})
	if got != endsBy(play.EndTobi) {
		t.Errorf("end = %+v, want by tobi", got)
	}
}

func TestGameEndCause_WhenAScoreIsExactlyZero_ShouldPlayOn(t *testing.T) {
	got := causeAfter(t, eastOne(t, 0), tsumo(t, 1), [tile.SeatCount]int{33334, 33333, 33333, 0})
	if got != playsOn() {
		t.Errorf("end = %+v, want play on", got)
	}
}

func TestGameEndCause_WhenAWestRoundEndsWithASeatAtTheThreshold_ShouldEndByTarget(t *testing.T) {
	westOne := causeAfter(t, at(t, 9, tile.West, 0, 0), tsumo(t, 1), [tile.SeatCount]int{30000, 25000, 22000, 23000})
	if westOne != endsBy(play.EndTargetReached) {
		t.Errorf("end after West 1 = %+v, want by target", westOne)
	}
	westTwo := causeAfter(t, at(t, 10, tile.West, 1, 0), tsumo(t, 2), [tile.SeatCount]int{35000, 20000, 22000, 23000})
	if westTwo != endsBy(play.EndTargetReached) {
		t.Errorf("end after West 2 = %+v, want by target", westTwo)
	}
}

func TestGameEndCause_WhenAWestRoundEndsWithNoSeatAtTheThreshold_ShouldPlayOn(t *testing.T) {
	got := causeAfter(t, at(t, 9, tile.West, 0, 0), tsumo(t, 1), [tile.SeatCount]int{29000, 25000, 23000, 23000})
	if got != playsOn() {
		t.Errorf("end = %+v, want play on", got)
	}
}

func TestGameEndCause_WhenSouthThreeEndsWithASeatAtTheThreshold_ShouldPlayOn(t *testing.T) {
	got := causeAfter(t, at(t, 6, tile.South, 1, 0), tsumo(t, 2), [tile.SeatCount]int{35000, 20000, 22000, 23000})
	if got != playsOn() {
		t.Errorf("end = %+v, want play on", got)
	}
}

func TestGameEndCause_WhenAWestDealerWinsAtTheThreshold_ShouldEndByTarget(t *testing.T) {
	ended := at(t, 9, tile.West, 0, 0)
	if next := ended.after(tsumo(t, 0)); next.uniqueDealers != 9 || next.dealer != seat(t, 0) {
		t.Errorf("after = %+v, want dealer 0 again, 9 unique dealers", next)
	}
	got := causeAfter(t, ended, tsumo(t, 0), [tile.SeatCount]int{30000, 24000, 23000, 23000})
	if got != endsBy(play.EndTargetReached) {
		t.Errorf("end = %+v, want by target", got)
	}
}

func TestGameEndCause_WhenAWestDealerWinsBelowTheThreshold_ShouldPlayOn(t *testing.T) {
	got := causeAfter(t, at(t, 9, tile.West, 0, 0), tsumo(t, 0), [tile.SeatCount]int{29000, 24000, 24000, 23000})
	if got != playsOn() {
		t.Errorf("end = %+v, want play on", got)
	}
}

func TestGameEndCause_WhenAWestDealerIsTenpaiAtTheThreshold_ShouldEndByTarget(t *testing.T) {
	ended := at(t, 10, tile.West, 1, 0)
	if next := ended.after(draw(t, []int{1})); next.dealer != seat(t, 1) {
		t.Errorf("after = %+v, want dealer 1 again", next)
	}
	got := causeAfter(t, ended, draw(t, []int{1}), [tile.SeatCount]int{24000, 31000, 22000, 23000})
	if got != endsBy(play.EndTargetReached) {
		t.Errorf("end = %+v, want by target", got)
	}
}

func TestGameEndCause_WhenAWestDealerIsTenpaiBelowTheThreshold_ShouldPlayOn(t *testing.T) {
	got := causeAfter(t, at(t, 10, tile.West, 1, 0), draw(t, []int{1}), [tile.SeatCount]int{29000, 24000, 24000, 23000})
	if got != playsOn() {
		t.Errorf("end = %+v, want play on", got)
	}
}

func TestGameEndCause_WhenTheDealerWinsFromSouthFourOn_ShouldEndOnlyInFirstPlaceAtTheThreshold(t *testing.T) {
	cases := []struct {
		uniqueDealers int
		wind          tile.Wind
		dealer        int
		scores        [tile.SeatCount]int
		want          ending
	}{
		{8, tile.South, 3, [tile.SeatCount]int{24000, 23000, 23000, 30000}, endsBy(play.EndLength)},
		{8, tile.South, 3, [tile.SeatCount]int{24000, 23000, 23000, 29900}, playsOn()},
		{8, tile.South, 3, [tile.SeatCount]int{24000, 32000, 23000, 31000}, playsOn()},
		{8, tile.South, 3, [tile.SeatCount]int{30000, 23000, 23000, 30000}, playsOn()},
		{9, tile.West, 0, [tile.SeatCount]int{30000, 30000, 20000, 20000}, endsBy(play.EndTargetReached)},
		{12, tile.West, 3, [tile.SeatCount]int{31000, 23000, 23000, 23000}, playsOn()},
	}
	for _, tc := range cases {
		ended := at(t, tc.uniqueDealers, tc.wind, tc.dealer, 0)
		if got := causeAfter(t, ended, tsumo(t, tc.dealer), tc.scores); got != tc.want {
			t.Errorf("end with %v = %+v, want %+v", tc.scores, got, tc.want)
		}
	}
}

func TestGameEndCause_WhenTheSouthFourDealerIsTenpaiInFirstPlaceAtTheThreshold_ShouldEndByLength(t *testing.T) {
	ended := at(t, 8, tile.South, 3, 0)
	scores := [tile.SeatCount]int{24000, 23000, 23000, 30000}
	if got := causeAfter(t, ended, draw(t, []int{3}), scores); got != endsBy(play.EndLength) {
		t.Errorf("end after a draw = %+v, want by length", got)
	}
	if got := causeAfter(t, ended, nagashi(t, []int{3}), scores); got != endsBy(play.EndLength) {
		t.Errorf("end after nagashi mangan = %+v, want by length", got)
	}
}

func TestGameEndCause_WhenTheSouthThreeWinnerBecomesTheFirstPlacedDealer_ShouldPlaySouthFour(t *testing.T) {
	got := causeAfter(t, at(t, 7, tile.South, 2, 0), tsumo(t, 3), [tile.SeatCount]int{23000, 23000, 23000, 31000})
	if got != playsOn() {
		t.Errorf("end = %+v, want play on", got)
	}
}

func TestGameEndCause_WhenADoubleRonLiftsOnlyTheNonDealerToTheThreshold_ShouldRepeatTheDeal(t *testing.T) {
	got := causeAfter(t, at(t, 9, tile.West, 0, 0), ron(t, []int{0, 1}, 2), [tile.SeatCount]int{28000, 32000, 20000, 20000})
	if got != playsOn() {
		t.Errorf("end = %+v, want play on", got)
	}
}

func TestGameEndCause_WhenWestFourAbortsWithTheDealerFirstAtTheThreshold_ShouldRepeatTheDeal(t *testing.T) {
	got := causeAfter(t, at(t, 12, tile.West, 3, 0), abortive(), [tile.SeatCount]int{23000, 23000, 23000, 31000})
	if got != playsOn() {
		t.Errorf("end = %+v, want play on", got)
	}
}

func TestGameEndCause_WhenANonDealerWinsWestFour_ShouldEndByExtensionLimit(t *testing.T) {
	ended := at(t, 12, tile.West, 3, 0)
	if next := ended.after(tsumo(t, 1)); next.uniqueDealers != 13 {
		t.Errorf("unique dealers after = %d, want 13", next.uniqueDealers)
	}
	got := causeAfter(t, ended, tsumo(t, 1), [tile.SeatCount]int{25000, 25000, 25000, 25000})
	if got != endsBy(play.EndExtensionLimit) {
		t.Errorf("end = %+v, want by extension limit", got)
	}
}

func TestGameEndCause_WhenTheWestFourDealerIsNotenAtADraw_ShouldEndByExtensionLimit(t *testing.T) {
	got := causeAfter(t, at(t, 12, tile.West, 3, 0), draw(t, []int{0}), [tile.SeatCount]int{25000, 25000, 25000, 25000})
	if got != endsBy(play.EndExtensionLimit) {
		t.Errorf("end = %+v, want by extension limit", got)
	}
}

func TestGameEndCause_WhenTheWestFourDealerWinsBelowTheThreshold_ShouldPlayOn(t *testing.T) {
	ended := at(t, 12, tile.West, 3, 0)
	if next := ended.after(tsumo(t, 3)); next.uniqueDealers != 12 || next.dealer != seat(t, 3) {
		t.Errorf("after = %+v, want dealer 3 again, 12 unique dealers", next)
	}
	got := causeAfter(t, ended, tsumo(t, 3), [tile.SeatCount]int{29000, 24000, 24000, 23000})
	if got != playsOn() {
		t.Errorf("end = %+v, want play on", got)
	}
}

func TestGameEndCause_WhenTheWestFourDealerWinsAtTheThreshold_ShouldEndByTarget(t *testing.T) {
	got := causeAfter(t, at(t, 12, tile.West, 3, 0), tsumo(t, 3), [tile.SeatCount]int{23000, 23000, 24000, 30000})
	if got != endsBy(play.EndTargetReached) {
		t.Errorf("end = %+v, want by target", got)
	}
}

func TestFinalPoints_WhenScoresAreDistinct_ShouldAddUmaAndOkaSummingToZero(t *testing.T) {
	want := [tile.SeatCount]int{523, 81, -214, -390}
	if got := finalPoints([tile.SeatCount]int{42300, 28100, 18600, 11000}); got != want {
		t.Errorf("finalPoints = %v, want %v", got, want)
	}
}

func TestFinalPoints_WhenScoresAreEqual_ShouldGiveEachPlaceItsUma(t *testing.T) {
	want := [tile.SeatCount]int{350, 50, -150, -250}
	if got := finalPoints([tile.SeatCount]int{25000, 25000, 25000, 25000}); got != want {
		t.Errorf("finalPoints = %v, want %v", got, want)
	}
}

func TestFinalPoints_WhenScoresTie_ShouldGiveTheOkaToFirstPlaceOnly(t *testing.T) {
	want := [tile.SeatCount]int{400, 100, -200, -300}
	if got := finalPoints([tile.SeatCount]int{30000, 30000, 20000, 20000}); got != want {
		t.Errorf("finalPoints = %v, want %v", got, want)
	}
}

func TestFinalPoints_WhenARawScoreIsNegative_ShouldStillSumToZero(t *testing.T) {
	want := [tile.SeatCount]int{650, 50, -150, -550}
	if got := finalPoints([tile.SeatCount]int{55000, 25000, 25000, -5000}); got != want {
		t.Errorf("finalPoints = %v, want %v", got, want)
	}
}

func TestFinalPoints_WhenScoresHaveHundreds_ShouldKeepThemUnrounded(t *testing.T) {
	want := [tile.SeatCount]int{406, 105, -205, -306}
	if got := finalPoints([tile.SeatCount]int{30600, 30500, 19500, 19400}); got != want {
		t.Errorf("finalPoints = %v, want %v", got, want)
	}
}

func TestFinalStandings_WhenSeatsAreOutOfOrder_ShouldPlaceThemByScore(t *testing.T) {
	standings := finalStandings([tile.SeatCount]int{28100, 11000, 42300, 18600}, 0, seat(t, 0), play.EndLength)
	if want := [tile.SeatCount]int{2, 4, 1, 3}; standings.Placements != want {
		t.Errorf("placements = %v, want %v", standings.Placements, want)
	}
	if want := [tile.SeatCount]int{81, -390, 523, -214}; standings.Points != want {
		t.Errorf("points = %v, want %v", standings.Points, want)
	}
}

func TestFinalStandings_WhenRiichiSticksAreLeft_ShouldGiveThemToTheTopPlayer(t *testing.T) {
	standings := finalStandings([tile.SeatCount]int{30000, 25000, 22000, 23000}, 2, seat(t, 0), play.EndTobi)
	if want := [tile.SeatCount]int{32000, 25000, 22000, 23000}; standings.Scores != want {
		t.Errorf("scores = %v, want %v", standings.Scores, want)
	}
	if want := [tile.SeatCount]int{1, 2, 4, 3}; standings.Placements != want {
		t.Errorf("placements = %v, want %v", standings.Placements, want)
	}
}

func TestFinalStandings_WhenScoresAreEqual_ShouldRankBySeatFromTheFirstDealer(t *testing.T) {
	equal := [tile.SeatCount]int{25000, 25000, 25000, 25000}
	if got, want := finalStandings(equal, 0, seat(t, 0), play.EndLength).Placements, [tile.SeatCount]int{1, 2, 3, 4}; got != want {
		t.Errorf("placements from seat 0 = %v, want %v", got, want)
	}
	if got, want := finalStandings(equal, 0, seat(t, 2), play.EndLength).Placements, [tile.SeatCount]int{3, 4, 1, 2}; got != want {
		t.Errorf("placements from seat 2 = %v, want %v", got, want)
	}
}

func TestFinalStandings_WhenScoresDiffer_ShouldRankByScoreBeforeSeatOrder(t *testing.T) {
	standings := finalStandings([tile.SeatCount]int{24000, 26000, 25000, 25000}, 0, seat(t, 0), play.EndLength)
	if want := [tile.SeatCount]int{4, 1, 2, 3}; standings.Placements != want {
		t.Errorf("placements = %v, want %v", standings.Placements, want)
	}
}

func TestPlacementOrder_WhenScoresTie_ShouldPlaceTheSeatNearerAfterTheFirstDealerFirst(t *testing.T) {
	cases := []struct {
		scores      [tile.SeatCount]int
		firstDealer int
		want        [tile.SeatCount]int
	}{
		{[tile.SeatCount]int{25000, 30000, 25000, 25000}, 3, [tile.SeatCount]int{1, 3, 0, 2}},
		{[tile.SeatCount]int{24000, 24000, 26000, 26000}, 1, [tile.SeatCount]int{2, 3, 1, 0}},
	}
	for _, tc := range cases {
		order := placementOrder(tc.scores, seat(t, tc.firstDealer))
		var got [tile.SeatCount]int
		for place, placed := range order {
			got[place] = placed.Index()
		}
		if got != tc.want {
			t.Errorf("placementOrder(%v, %d) = %v, want %v", tc.scores, tc.firstDealer, got, tc.want)
		}
	}
}
