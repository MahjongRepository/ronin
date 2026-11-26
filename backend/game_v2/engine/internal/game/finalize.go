package game

import (
	"cmp"
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	dealersPerWind   = tile.SeatCount
	eastDealers      = dealersPerWind
	hanchanDealers   = dealersPerWind * 2
	extensionDealers = dealersPerWind * 3
	scorePerTenth    = 100
	tenthsPerPoint   = 10
)

type position struct {
	roundNumber   uint32
	dealer        tile.Seat
	wind          tile.Wind
	uniqueDealers int
	honba         int
}

func (p position) after(result play.RoundResult) position {
	honba, dealerStays := p.honba+1, false
	switch result := result.(type) {
	case play.Abortive:
		dealerStays = true
	case play.ExhaustiveDraw:
		dealerStays = slices.ContainsFunc(result.Tenpai, func(hand play.ShownHand) bool {
			return hand.Seat == p.dealer
		})
	case play.Tsumo:
		honba, dealerStays = p.afterWins([]play.WinResult{result.Win})
	case play.Ron:
		honba, dealerStays = p.afterWins(result.Wins)
	}

	next := p
	next.roundNumber++
	next.honba = honba
	if !dealerStays {
		next.dealer = p.dealer.Next()
		next.uniqueDealers++
		next.wind = windOf(next.uniqueDealers)
	}

	return next
}

func (p position) afterWins(wins []play.WinResult) (honba int, dealerStays bool) {
	if slices.ContainsFunc(wins, func(win play.WinResult) bool { return win.Winner == p.dealer }) {
		return p.honba + 1, true
	}

	return 0, false
}

func windOf(uniqueDealers int) tile.Wind {
	switch {
	case uniqueDealers <= eastDealers:
		return tile.East
	case uniqueDealers <= hanchanDealers:
		return tile.South
	default:
		return tile.West
	}
}

func gameEndCause(
	ended, next position,
	result play.RoundResult,
	scores [tile.SeatCount]int,
	firstDealer tile.Seat,
	ruleset rules.Ruleset,
) (play.GameEndCause, bool) {
	if slices.ContainsFunc(scores[:], ruleset.Tobi.Busts) {
		return play.EndTobi, true
	}

	targetCause := play.EndTargetReached
	if ended.wind == tile.East || ended.wind == tile.South {
		targetCause = play.EndLength
	}

	if ruleset.Agariyame && next.dealer == ended.dealer && next.uniqueDealers >= hanchanDealers {
		_, isAbortive := result.(play.Abortive)
		first := placementOrder(scores, firstDealer)[0]
		dealerFirstAtTarget := first == next.dealer &&
			scores[first.Index()] >= ruleset.WinningScoreThreshold
		if isAbortive || !dealerFirstAtTarget {
			return 0, false
		}

		return targetCause, true
	}

	hasWinner := slices.ContainsFunc(scores[:], func(score int) bool {
		return score >= ruleset.WinningScoreThreshold
	})
	if next.uniqueDealers > hanchanDealers && (hasWinner || !ruleset.WestRound) {
		return targetCause, true
	}

	if next.uniqueDealers > extensionDealers {
		return play.EndExtensionLimit, true
	}

	return 0, false
}

func finalStandings(
	scores [tile.SeatCount]int,
	riichiSticks int,
	firstDealer tile.Seat,
	cause play.GameEndCause,
	ruleset rules.Ruleset,
) play.Standings {
	order := placementOrder(scores, firstDealer)
	var scoresByOrder [tile.SeatCount]int
	for i, seat := range order {
		scoresByOrder[i] = scores[seat.Index()]
	}

	places := placesOf(scoresByOrder, ruleset.SplitTiedPlaces)
	if ruleset.LeftoverRiichiSticksToFirst {
		scoresByOrder = withLeftoverSticks(scoresByOrder, places, riichiSticks*ruleset.RiichiStickValue)
	}

	pointsByOrder := finalPoints(scoresByOrder, places, ruleset)
	standings := play.Standings{Cause: cause}
	for i, seat := range order {
		standings.Scores[seat.Index()] = scoresByOrder[i]
		standings.Placements[seat.Index()] = places[i] + 1
		standings.Points[seat.Index()] = pointsByOrder[i]
	}

	return standings
}

func placementOrder(scores [tile.SeatCount]int, firstDealer tile.Seat) [tile.SeatCount]tile.Seat {
	order := tile.Seats()
	slices.SortFunc(order[:], func(a, b tile.Seat) int {
		return cmp.Or(
			cmp.Compare(scores[b.Index()], scores[a.Index()]),
			cmp.Compare(a.DistanceFrom(firstDealer), b.DistanceFrom(firstDealer)),
		)
	})
	return order
}

func placesOf(scoresByOrder [tile.SeatCount]int, splitTies bool) [tile.SeatCount]int {
	var places [tile.SeatCount]int
	for i := range places {
		places[i] = i
		if splitTies && i > 0 && scoresByOrder[i] == scoresByOrder[i-1] {
			places[i] = places[i-1]
		}
	}

	return places
}

func withLeftoverSticks(scoresByOrder, places [tile.SeatCount]int, leftover int) [tile.SeatCount]int {
	leaders := 0
	for _, place := range places {
		if place == 0 {
			leaders++
		}
	}

	shares := evenShares(leftover/scorePerTenth, leaders)
	for i, share := range shares {
		scoresByOrder[i] += share * scorePerTenth
	}

	return scoresByOrder
}

func evenShares(total, count int) []int {
	share, remainder := total/count, total%count
	if remainder < 0 {
		share, remainder = share-1, remainder+count
	}

	shares := make([]int, count)
	for i := range shares {
		shares[i] = share
		if i < remainder {
			shares[i]++
		}
	}

	return shares
}

func finalPoints(scoresByOrder, places [tile.SeatCount]int, ruleset rules.Ruleset) [tile.SeatCount]int {
	var bonuses [tile.SeatCount]int
	for i, uma := range ruleset.Uma {
		bonuses[i] = uma * tenthsPerPoint
	}

	bonuses[0] += (ruleset.TargetScore - ruleset.StartingScore) * tile.SeatCount / scorePerTenth
	var points [tile.SeatCount]int
	for first := 0; first < tile.SeatCount; {
		next := first + 1
		for next < tile.SeatCount && places[next] == places[first] {
			next++
		}

		shares := evenShares(sum(bonuses[first:next]), next-first)
		for i, share := range shares {
			points[first+i] = (scoresByOrder[first+i]-ruleset.TargetScore)/scorePerTenth + share
		}

		first = next
	}

	if ruleset.RoundFinalPoints {
		return roundedPoints(points)
	}

	return points
}

func sum(values []int) int {
	total := 0
	for _, v := range values {
		total += v
	}

	return total
}

func roundedPoints(points [tile.SeatCount]int) [tile.SeatCount]int {
	total := sum(points[:])
	rounded := points
	for place := 1; place < tile.SeatCount; place++ {
		rounded[place] = roundedToWholePoint(points[place])
		total -= rounded[place]
	}

	rounded[0] = total
	return rounded
}

func roundedToWholePoint(tenths int) int {
	half := tenthsPerPoint / 2
	if tenths < 0 {
		return -((-tenths + half) / tenthsPerPoint * tenthsPerPoint)
	}

	return (tenths + half) / tenthsPerPoint * tenthsPerPoint
}
