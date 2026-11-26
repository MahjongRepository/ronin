package main

import (
	"encoding/hex"
	"errors"
	"fmt"
	"slices"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	handSize    = 13
	dealtTiles  = tile.SeatCount * handSize
	controlName = "random.Random(experiment seed).shuffle, hands cut from the front of the permutation"
)

type roundSample struct {
	roundNumber int
	dealer      int
	permutation [tile.TileIDCount]int
	dice        tile.Dice
	deal        play.RoundDeal
}

func (s roundSample) dealerHand() []tile.TileID {
	return append(slices.Clone(s.deal.Hands[s.dealer]), s.deal.DealerDraw)
}

func (s roundSample) handAtOffset(offset int) []tile.TileID {
	return s.deal.Hands[(s.dealer+offset)%tile.SeatCount]
}

type gameSample struct {
	seed        string
	seats       [tile.SeatCount]int
	firstDealer int
	firstRoll   tile.Dice
	secondRoll  tile.Dice
	rounds      []roundSample
}

type controlRound struct {
	hands      [tile.SeatCount][]int
	dealerHand []int
}

func sampleEngineGame(seedHex string, rounds int) (gameSample, error) {
	seed, err := engine.ParseSeed(seedHex)
	if err != nil {
		return gameSample{}, fmt.Errorf("parse seed %s: %w", seedHex, err)
	}

	dealer, firstRoll, secondRoll := engine.FirstDealer(seed)
	game := gameSample{
		seed:        seedHex,
		firstDealer: dealer.Index(),
		firstRoll:   firstRoll,
		secondRoll:  secondRoll,
	}
	for i, s := range engine.SeatPermutation(seed) {
		game.seats[i] = s.Index()
	}

	for roundNumber := range rounds {
		game.rounds = append(game.rounds, sampleRound(seed, roundNumber, (dealer.Index()+roundNumber)%tile.SeatCount))
	}

	return game, nil
}

func sampleRound(seed engine.Seed, roundNumber, dealer int) roundSample {
	shuffled, dice := engine.RoundWall(seed, uint32(roundNumber))
	sample := roundSample{
		roundNumber: roundNumber,
		dealer:      dealer,
		dice:        dice,
		deal:        engine.DealRound(seed, uint32(roundNumber), tile.Seats()[dealer]),
	}
	for i, id := range shuffled {
		sample.permutation[i] = id.Index()
	}

	return sample
}

func checkRound(s roundSample) error {
	where := "round " + strconv.Itoa(s.roundNumber)
	if !isEveryID(s.permutation[:]) {
		return errors.New(where + ": the permutation is not the 136 tile ids")
	}

	wallTiles := indexes(slices.Concat(s.deal.Live, s.deal.DeadWall))
	if !isEveryID(wallTiles) {
		return errors.New(where + ": the live and dead walls do not own every tile once")
	}

	if slices.ContainsFunc(s.deal.Hands[:], func(hand []tile.TileID) bool { return len(hand) != handSize }) {
		return errors.New(where + ": the deal is not 4 hands of 13")
	}

	dealt := indexes(slices.Concat(s.deal.Hands[:]...))
	front := indexes(s.deal.Live[:min(dealtTiles, len(s.deal.Live))])
	slices.Sort(dealt)
	slices.Sort(front)
	if !slices.Equal(dealt, front) || len(s.deal.Live) <= dealtTiles || s.deal.DealerDraw != s.deal.Live[dealtTiles] {
		return errors.New(where + ": the hands and the dealer's draw are not the front of the live wall")
	}

	return nil
}

func isEveryID(ids []int) bool {
	return slices.Equal(slices.Sorted(slices.Values(ids)), identity(tile.TileIDCount))
}

func indexes(ids []tile.TileID) []int {
	out := make([]int, len(ids))
	for i, id := range ids {
		out[i] = id.Index()
	}

	return out
}

func engineSeeds(experimentSeed, games int) []string {
	stream := newPythonRandom("ronin-measure-wall-engine-" + strconv.Itoa(experimentSeed))
	seeds := make([]string, games)
	for i := range seeds {
		seeds[i] = hex.EncodeToString(stream.randBytes(engine.SeedBytes))
	}

	return seeds
}

func controlRounds(experimentSeed, count int) []controlRound {
	stream := newPythonRandom("ronin-measure-wall-control-" + strconv.Itoa(experimentSeed))
	rounds := make([]controlRound, count)
	for i := range rounds {
		tiles := identity(tile.TileIDCount)
		stream.shuffle(tiles)
		for seat := range tile.SeatCount {
			rounds[i].hands[seat] = tiles[seat*handSize : (seat+1)*handSize]
		}

		rounds[i].dealerHand = append(slices.Clone(rounds[i].hands[0]), tiles[dealtTiles])
	}

	return rounds
}

func identity(n int) []int {
	items := make([]int, n)
	for i := range items {
		items[i] = i
	}

	return items
}
