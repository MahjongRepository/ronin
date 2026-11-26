package offer_test

import (
	"errors"
	"math"
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/offer"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestKanOffers_WhenTwoQuadsAreHeld_ShouldNameTheFirstCopyOfEachInHandOrder(t *testing.T) {
	hand := concat(copies(t, 0, "2222m1111m"), copies(t, 0, "12345p"))

	got := offer.KanOffers(hand, nil, hand[0], false, [4]int{}, 10)

	want := []play.Action{play.KanAction(play.KanClosed, hand[0]), play.KanAction(play.KanClosed, hand[4])}
	if !slices.Equal(got, want) {
		t.Errorf("KanOffers = %v, want %v", got, want)
	}
}

func TestKansBySeat_ShouldCountEveryKanKindButNotAPon(t *testing.T) {
	seats := tile.Seats()
	quad := func(kind play.MeldKind, mpsz string) play.MeldView {
		return play.MeldView{Kind: kind, Tiles: copies(t, 0, mpsz)}
	}

	var melds [tile.SeatCount][]play.MeldView
	melds[0] = []play.MeldView{quad(play.MeldClosedKan, "1111p"), calledMeld(t, play.MeldPon, 0, "777z", seats[3])}
	melds[2] = []play.MeldView{quad(play.MeldOpenKan, "2222p"), quad(play.MeldAddedKan, "3333p")}

	if got := offer.KansBySeat(melds); got != [tile.SeatCount]int{1, 0, 2, 0} {
		t.Errorf("KansBySeat = %v, want [1 0 2 0]", got)
	}
}

func TestIsFourKans_WhenOneSeatHoldsAllFour_ShouldBeFalseUntilASecondSeatHoldsOne(t *testing.T) {
	var melds [tile.SeatCount][]play.MeldView
	melds[0] = []play.MeldView{
		closedKan(t, "1111s"), closedKan(t, "2222s"), closedKan(t, "3333s"), closedKan(t, "4444s"),
	}

	oneSeat := offer.KansBySeat(melds)
	melds[1] = melds[0][3:]
	melds[0] = melds[0][:3]
	twoSeats := offer.KansBySeat(melds)

	if offer.IsFourKans(oneSeat) || offer.MayAddKan(oneSeat, 10) {
		t.Errorf("IsFourKans, MayAddKan(%v) = %t, %t, want false, false",
			oneSeat, offer.IsFourKans(oneSeat), offer.MayAddKan(oneSeat, 10))
	}

	if !offer.IsFourKans(twoSeats) {
		t.Errorf("IsFourKans(%v) = false, want true", twoSeats)
	}
}

func TestKanOffers_WhenAClosedKanAndAPonsFourthCopyAreHeld_ShouldListTheClosedKanThenTheAddedKan(t *testing.T) {
	hand := concat(copies(t, 0, "1111m"), copies(t, 3, "5p"), copies(t, 0, "23s"))
	melds := []play.MeldView{
		calledMeld(t, play.MeldChi, 0, "789s", seat(t, 0)),
		calledMeld(t, play.MeldPon, 0, "555p", seat(t, 1)),
	}

	got, err := offer.CheckedKanOffers(hand, melds, hand[0], false, [4]int{1, 0, 0, 0}, 10)
	if err != nil {
		t.Fatalf("CheckedKanOffers error = %v", err)
	}

	want := []play.Action{play.KanAction(play.KanClosed, hand[0]), play.KanAction(play.KanAdded, hand[4])}
	if !slices.Equal(got, want) {
		t.Errorf("KanOffers = %v, want %v", got, want)
	}
}

func TestKanOffers_WhenInRiichi_ShouldKeepOnlyTheDrawnClosedKan(t *testing.T) {
	hand := copies(t, 0, "1111m78m234p567s99s")

	drewTheFourth := offer.KanOffers(hand, nil, hand[3], true, [4]int{}, 10)
	drewAnother := offer.KanOffers(hand, nil, hand[4], true, [4]int{}, 10)

	if want := []play.Action{play.KanAction(play.KanClosed, hand[0])}; !slices.Equal(drewTheFourth, want) {
		t.Errorf("KanOffers on the drawn fourth copy = %v, want %v", drewTheFourth, want)
	}

	if len(drewAnother) != 0 {
		t.Errorf("KanOffers on another draw = %v, want none", drewAnother)
	}
}

func TestKanOffers_WhenInRiichiAndTheKanChangesTheWaits_ShouldOfferNone(t *testing.T) {
	hand := copies(t, 0, "1111m2m456p789s123s")

	if got := offer.KanOffers(hand, nil, hand[3], true, [4]int{}, 10); len(got) != 0 {
		t.Errorf("KanOffers = %v, want none", got)
	}
}

func TestKanOffers_WhenInRiichi_ShouldOfferNoAddedKan(t *testing.T) {
	hand := concat(copies(t, 3, "5p"), copies(t, 0, "23s"))
	melds := []play.MeldView{calledMeld(t, play.MeldPon, 0, "555p", seat(t, 1))}

	if got := offer.KanOffers(hand, melds, hand[0], true, [4]int{1, 0, 0, 0}, 10); len(got) != 0 {
		t.Errorf("KanOffers = %v, want none", got)
	}
}

func TestKanOffers_WhenNoKanIsLeftToSpareOrNoLiveTile_ShouldOfferNone(t *testing.T) {
	hand := copies(t, 0, "1111m78m234p567s99s")

	if got := offer.KanOffers(hand, nil, hand[0], false, [4]int{2, 2, 0, 0}, 10); len(got) != 0 {
		t.Errorf("KanOffers at four kans = %v, want none", got)
	}

	if got := offer.KanOffers(hand, nil, hand[0], false, [4]int{}, 0); len(got) != 0 {
		t.Errorf("KanOffers on an empty wall = %v, want none", got)
	}

	lastLiveTile := offer.KanOffers(hand, nil, hand[0], false, [4]int{}, 1)
	if want := []play.Action{play.KanAction(play.KanClosed, hand[0])}; !slices.Equal(lastLiveTile, want) {
		t.Errorf("KanOffers on the last live tile = %v, want %v", lastLiveTile, want)
	}
}

func TestCheckedKanOffers_WhenAHandTileIsAlsoMelded_ShouldReportTheDuplicate(t *testing.T) {
	hand := concat(copies(t, 0, "1111m"), copies(t, 2, "5p"), copies(t, 0, "23s"))
	melds := []play.MeldView{calledMeld(t, play.MeldPon, 0, "555p", seat(t, 1))}

	_, err := offer.CheckedKanOffers(hand, melds, hand[0], false, [4]int{1, 0, 0, 0}, 10)

	if want := (meld.DuplicateTileError{Tile: copyOf(t, 2, "5p")}); !errors.Is(err, want) {
		t.Errorf("CheckedKanOffers error = %v, want %v", err, want)
	}
}

func TestCheckedKanOffers_WhenAPonIsEmpty_ShouldReportTheMisfitMeldBeforeAnyDuplicate(t *testing.T) {
	melds := []play.MeldView{closedKan(t, "9999m"), {Kind: play.MeldPon}}

	_, err := offer.CheckedKanOffers([]tile.TileID{id(t, 0), id(t, 0)}, melds, id(t, 0), false, [4]int{1, 0, 0, 0}, 10)

	if want := (meld.MisfitMeldError{Index: 1}); !errors.Is(err, want) {
		t.Errorf("CheckedKanOffers error = %v, want %v", err, want)
	}
}

func TestKanOffers_WhenKanCountsAreHuge_ShouldCountThemAsFourOrMore(t *testing.T) {
	quad := copies(t, 0, "1111m444p")

	huge := [4]int{math.MaxInt, math.MaxInt, math.MaxInt, math.MaxInt}

	if got := offer.KanOffers(quad, nil, quad[0], false, huge, 10); len(got) != 0 {
		t.Errorf("KanOffers = %v, want none", got)
	}
}
