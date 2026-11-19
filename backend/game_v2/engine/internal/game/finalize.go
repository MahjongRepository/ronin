// Package game moves a game on from round to round: the position each round is dealt at, how a
// round's end counts the honba and passes the deal, the rule that ends the game and its final
// standings. A game is a hanchan: East and South, then the West extension, played until a seat
// reaches the winning threshold or the last West round ends.
//
// Ported from mahjong-rs's mahjong-game at commit 0d8733f: its finalize module.
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
) (play.GameEndCause, bool) {
	if rules.Tobi && slices.ContainsFunc(scores[:], func(score int) bool {
		return score < rules.TobiThreshold
	}) {
		return play.EndTobi, true
	}

	targetCause := play.EndTargetReached
	if ended.wind == tile.East || ended.wind == tile.South {
		targetCause = play.EndLength
	}
	if rules.Agariyame && next.dealer == ended.dealer && next.uniqueDealers >= hanchanDealers {
		_, isAbortive := result.(play.Abortive)
		first := placementOrder(scores, firstDealer)[0]
		dealerFirstAtTarget := first == next.dealer &&
			scores[first.Index()] >= rules.WinningScoreThreshold
		if isAbortive || !dealerFirstAtTarget {
			return 0, false
		}
		return targetCause, true
	}

	hasWinner := slices.ContainsFunc(scores[:], func(score int) bool {
		return score >= rules.WinningScoreThreshold
	})
	if next.uniqueDealers > hanchanDealers && hasWinner {
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
) play.Standings {
	order := placementOrder(scores, firstDealer)
	scores[order[0].Index()] += riichiSticks * rules.RiichiStickValue

	var scoresByPlace [tile.SeatCount]int
	for place, seat := range order {
		scoresByPlace[place] = scores[seat.Index()]
	}
	pointsByPlace := finalPoints(scoresByPlace)

	standings := play.Standings{Cause: cause, Scores: scores}
	for place, seat := range order {
		standings.Placements[seat.Index()] = place + 1
		standings.Points[seat.Index()] = pointsByPlace[place]
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

func finalPoints(scoresByPlace [tile.SeatCount]int) [tile.SeatCount]int {
	oka := (rules.TargetScore - rules.StartingScore) * tile.SeatCount / scorePerTenth
	var points [tile.SeatCount]int
	for place, score := range scoresByPlace {
		points[place] = (score-rules.TargetScore)/scorePerTenth + rules.Uma[place]*tenthsPerPoint
	}
	points[0] += oka
	return points
}
