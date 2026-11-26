package testkit

import (
	"errors"
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// Junk returns a hand of copy first of 1357m2468p13579s: no pair, no wait, no call.
func Junk(first int) ([]tile.TileID, error) {
	return Copies(first, "1357m2468p13579s")
}

// NotenWall returns a wall that deals every seat Junk, copies 0 to 3, so the round draws with every
// seat noten.
func NotenWall() (StartWall, error) {
	var b builder
	var w StartWall
	for i := range w.Hands {
		w.Hands[i] = b.copies(i, "1357m2468p13579s")
	}

	return w, b.err
}

// DealerPonFromSeatThree returns DealerCallFromSeatThree with the dealer's pon of called, on the
// first two copies of its kind in dealer.
func DealerPonFromSeatThree(
	dealer []tile.TileID, called, discardAfterPon tile.TileID, laterDraws []tile.TileID,
	dora play.Option[tile.TileID],
) (game.Game, error) {
	held := append(slices.Collect(tile.HeldCopies(dealer, called.Kind())), tile.TileID{}, tile.TileID{})
	pon := play.PonAction([2]tile.TileID{held[0], held[1]})
	return DealerCallFromSeatThree(dealer, called, pon, discardAfterPon, laterDraws, dora)
}

func DealerCallFromSeatThree(
	dealer []tile.TileID, called tile.TileID, call play.Action, discardAfterCall tile.TileID,
	laterDraws []tile.TileID, dora play.Option[tile.TileID],
) (game.Game, error) {
	var b builder
	seats := tile.Seats()
	w := StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			dealer,
			b.copies(1, "123456789p1379s"),
			b.copies(2, "123456789p1379s"),
			append(b.copies(3, "123456789p139s"), called),
		},
		Draws: append(b.copies(0, "1234z"), laterDraws...),
		Dora:  dora,
	}
	g, err := BegunGame(w, play.Option[play.StartPosition]{})
	g, _, drawnErr := DiscardDrawn(g, 3)
	g, _, scriptErr := Script(g,
		SeatAction{Seat: seats[3], Action: play.DiscardAction(called)},
		SeatAction{Seat: seats[0], Action: call},
		SeatAction{Seat: seats[0], Action: play.DiscardAction(discardAfterCall)},
	)
	return g, errors.Join(b.err, err, drawnErr, scriptErr)
}

// ThreePinWithTwoRonCallers returns the game where seat 2 has just discarded the fourth 3p, which
// seats 0 and 3 may ron and seat 3 may also chi.
func ThreePinWithTwoRonCallers() (game.Game, error) {
	var b builder
	w := StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			b.copies(0, "123456789m1255p"),
			b.copies(2, "123456789s1234z"),
			b.copies(3, "123456789s1234z"),
			slices.Concat(b.copies(1, "123456789m12p"), b.copies(2, "55p")),
		},
		Draws: []tile.TileID{b.tile(0, "7z"), b.tile(1, "7z"), b.tile(3, "3p")},
	}
	g, err := BegunGame(w, play.Option[play.StartPosition]{})
	g, _, drawnErr := DiscardDrawn(g, 3)
	return g, errors.Join(b.err, err, drawnErr)
}

// EastStart returns the start position of East 1 dealt by seat 0, with scores, honba and
// riichiSticks.
func EastStart(scores [tile.SeatCount]int, honba, riichiSticks int) play.StartPosition {
	return play.StartPosition{Scores: scores, Honba: honba, RiichiSticks: riichiSticks, Dealer: tile.Seats()[0], Wind: tile.East}
}
