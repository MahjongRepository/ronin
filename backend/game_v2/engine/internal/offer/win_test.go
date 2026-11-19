package offer_test

import (
	"errors"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/offer"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestTsumoScoreChanges_ShouldChargeEachSeatItsShareAndHonba(t *testing.T) {
	payment := play.TsumoPayment{Dealer: 2000, NonDealer: 1000}

	got := offer.TsumoScoreChanges(seat(t, 1), seat(t, 0), payment, 1, 0, play.Option[tile.Seat]{})

	if want := [4]int{-2100, 4300, -1100, -1100}; got != want {
		t.Errorf("TsumoScoreChanges = %v, want %v", got, want)
	}
}

func TestTsumoScoreChanges_ShouldGiveTheRiichiSticksToTheWinner(t *testing.T) {
	payment := play.DealerTsumoPayment{NonDealer: 6000}

	got := offer.TsumoScoreChanges(seat(t, 0), seat(t, 0), payment, 1, 2, play.Option[tile.Seat]{})

	if want := [4]int{20300, -6100, -6100, -6100}; got != want {
		t.Errorf("TsumoScoreChanges = %v, want %v", got, want)
	}
}

func TestTsumoScoreChanges_WhenALiableSeat_ShouldChargeItEveryShareAndTheWholeHonba(t *testing.T) {
	payment := play.TsumoPayment{Dealer: 16000, NonDealer: 8000}

	got := offer.TsumoScoreChanges(seat(t, 1), seat(t, 0), payment, 1, 1, play.Some(seat(t, 2)))

	if want := [4]int{0, 33300, -32300, 0}; got != want {
		t.Errorf("TsumoScoreChanges = %v, want %v", got, want)
	}
}

func TestTsumoScoreChanges_WhenPaidARonPayment_ShouldChargeOnlyTheHonba(t *testing.T) {
	payment := play.RonPayment{Discarder: 8000}

	got := offer.TsumoScoreChanges(seat(t, 1), seat(t, 0), payment, 1, 0, play.Option[tile.Seat]{})

	if want := [4]int{-100, 300, -100, -100}; got != want {
		t.Errorf("TsumoScoreChanges = %v, want %v", got, want)
	}
}

func TestRonScoreChanges_ShouldChargeTheDiscarderAndGiveTheTableOnlyWhenTaken(t *testing.T) {
	payment := play.RonPayment{Discarder: 8000}

	taken := offer.RonScoreChanges(seat(t, 2), seat(t, 1), payment, 2, 2, play.Option[tile.Seat]{})
	left := offer.RonScoreChanges(seat(t, 2), seat(t, 1), payment, 0, 0, play.Option[tile.Seat]{})

	if want := [4]int{0, -8600, 10600, 0}; taken != want {
		t.Errorf("RonScoreChanges taking the table = %v, want %v", taken, want)
	}
	if want := [4]int{0, -8000, 8000, 0}; left != want {
		t.Errorf("RonScoreChanges leaving the table = %v, want %v", left, want)
	}
}

func TestRonScoreChanges_WhenALiableSeat_ShouldSplitTheHandWithItAndChargeItTheHonba(t *testing.T) {
	payment := play.RonPayment{Discarder: 32000}

	liableBeside := offer.RonScoreChanges(seat(t, 1), seat(t, 2), payment, 1, 0, play.Some(seat(t, 3)))
	liableDiscarder := offer.RonScoreChanges(seat(t, 1), seat(t, 3), payment, 1, 0, play.Some(seat(t, 3)))

	if want := [4]int{0, 32300, -16000, -16300}; liableBeside != want {
		t.Errorf("RonScoreChanges with another liable seat = %v, want %v", liableBeside, want)
	}
	if want := [4]int{0, 32300, 0, -32300}; liableDiscarder != want {
		t.Errorf("RonScoreChanges with the discarder liable = %v, want %v", liableDiscarder, want)
	}
}

func TestCompletes_WhenTheTileCompletesOrAKindIsHeldFiveTimes_ShouldReportOnlyTheCompleteHand(t *testing.T) {
	hand := copies(t, 0, "234567m234p55s67s")
	fiveOnes := concat(copies(t, 0, "1111m"), copies(t, 0, "23m456p789s99s"))

	if !offer.Completes(hand, copyOf(t, 1, "8s")) {
		t.Error("Completes on the wait = false, want true")
	}
	if offer.Completes(hand, copyOf(t, 1, "1m")) {
		t.Error("Completes off the waits = true, want false")
	}
	if offer.Completes(fiveOnes, fiveOnes[0]) {
		t.Error("Completes with a fifth copy = true, want false")
	}
}

func TestHandValue_WhenAMeldDoesNotFitItsKind_ShouldReportTheMisfitMeld(t *testing.T) {
	concealed := copies(t, 0, "234567m234p5s")
	melds := []play.MeldView{
		calledMeld(t, play.MeldPon, 0, "888s", seat(t, 1)),
		{Kind: play.MeldChi, Tiles: copies(t, 0, "135s")},
	}

	_, err := offer.HandValue(concealed, copyOf(t, 1, "5s"), offer.Scoring{Situation: ronSituation(), Melds: melds})

	if want := (meld.MisfitMeldError{Index: 1}); !errors.Is(err, want) {
		t.Errorf("HandValue error = %v, want %v", err, want)
	}
}
