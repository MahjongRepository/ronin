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

func chiKuikae(t *testing.T, called, pair string) []tile.Kind {
	t.Helper()
	held := copies(t, 0, pair)
	return offer.KuikaeKinds(copyOf(t, 0, called), play.ChiCall{Held: [2]tile.TileID{held[0], held[1]}})
}

func TestKuikaeKinds_WhenPon_ShouldForbidTheCalledKind(t *testing.T) {
	held := [2]tile.TileID{copyOf(t, 1, "4m"), copyOf(t, 2, "4m")}

	got := offer.KuikaeKinds(copyOf(t, 0, "4m"), play.PonCall{Held: held})

	if want := []tile.Kind{kindOf(t, "4m")}; !slices.Equal(got, want) {
		t.Errorf("KuikaeKinds = %v, want %v", got, want)
	}
}

func TestKuikaeKinds_WhenOpenKan_ShouldForbidNothing(t *testing.T) {
	if got := offer.KuikaeKinds(copyOf(t, 0, "4m"), play.OpenKanCall{}); len(got) != 0 {
		t.Errorf("KuikaeKinds = %v, want none", got)
	}
}

func TestKuikaeKinds_WhenChi_ShouldForbidTheCalledKindAndTheSujiPastTheOtherEnd(t *testing.T) {
	tests := []struct {
		name, called, pair string
		want               []tile.Kind
	}{
		{name: "called lowest", called: "4m", pair: "56m", want: []tile.Kind{kindOf(t, "4m"), kindOf(t, "7m")}},
		{name: "called highest", called: "6m", pair: "45m", want: []tile.Kind{kindOf(t, "6m"), kindOf(t, "3m")}},
		{name: "called middle", called: "5m", pair: "46m", want: []tile.Kind{kindOf(t, "5m")}},
		{name: "no suji past nine", called: "7m", pair: "89m", want: []tile.Kind{kindOf(t, "7m")}},
		{name: "no suji below one", called: "3p", pair: "12p", want: []tile.Kind{kindOf(t, "3p")}},
	}
	for _, c := range tests {
		t.Run(c.name, func(t *testing.T) {
			if got := chiKuikae(t, c.called, c.pair); !slices.Equal(got, c.want) {
				t.Errorf("KuikaeKinds = %v, want %v", got, c.want)
			}
		})
	}
}

func TestChiOptions_WhenEveryRemainingTileWouldBeKuikaeRestricted_ShouldOfferNone(t *testing.T) {
	tests := []struct{ hand, called string }{
		{hand: "1234m", called: "1m"},
		{hand: "1223m", called: "2m"},
		{hand: "1112344m", called: "1m"},
	}
	for _, c := range tests {
		t.Run(c.hand+" on "+c.called, func(t *testing.T) {
			if got := offer.ChiOptions(copies(t, 0, c.hand), false, copyOf(t, 3, c.called)); len(got) != 0 {
				t.Errorf("ChiOptions(%s on %s) = %v, want none", c.hand, c.called, got)
			}
		})
	}
}

func TestChiOptions_WhenARemainingTileStaysDiscardable_ShouldOffer(t *testing.T) {
	hand := copies(t, 0, "1235m")

	got := offer.ChiOptions(hand, false, copyOf(t, 3, "1m"))
	if want := [][2]tile.TileID{{hand[1], hand[2]}}; !slices.Equal(got, want) {
		t.Errorf("ChiOptions = %v, want %v", got, want)
	}
}

func TestChiOptions_WhenHandHoldsRedAndPlainFives_ShouldOfferOneOptionPerLook(t *testing.T) {
	hand := concat(copies(t, 0, "556m"), copies(t, 2, "5m"), copies(t, 0, "123z"))
	red, plain, six := hand[0], hand[1], hand[2]
	if !red.Tile(tile.AkaDoraEnabled).IsRed() {
		t.Fatalf("%v is not a red five", red)
	}

	got := offer.ChiOptions(hand, false, copyOf(t, 3, "4m"))
	if want := [][2]tile.TileID{{red, six}, {plain, six}}; !slices.Equal(got, want) {
		t.Errorf("ChiOptions = %v, want %v", got, want)
	}
}

func TestChiOptions_WhenInRiichiOrOnAnHonor_ShouldOfferNone(t *testing.T) {
	hand := copies(t, 0, "23m5566z")

	if got := offer.ChiOptions(hand, true, copyOf(t, 3, "4m")); len(got) != 0 {
		t.Errorf("ChiOptions in riichi = %v, want none", got)
	}

	if got := offer.ChiOptions(hand, false, copyOf(t, 3, "5z")); len(got) != 0 {
		t.Errorf("ChiOptions on an honor = %v, want none", got)
	}
}

func TestPonOptions_WhenHandHoldsRedAndPlainFives_ShouldOfferOnePairPerLook(t *testing.T) {
	hand := concat(copies(t, 1, "55m"), copies(t, 0, "5m"), copies(t, 0, "1z"))
	plain, otherPlain, red := hand[0], hand[1], hand[2]

	got := offer.PonOptions(hand, false, copyOf(t, 3, "5m"))
	withoutFirstPlain := offer.PonOptions(hand[1:], false, copyOf(t, 3, "5m"))

	if want := [][2]tile.TileID{{red, plain}, {plain, otherPlain}}; !slices.Equal(got, want) {
		t.Errorf("PonOptions = %v, want %v", got, want)
	}

	if want := [][2]tile.TileID{{red, otherPlain}}; !slices.Equal(withoutFirstPlain, want) {
		t.Errorf("PonOptions without the first plain five = %v, want %v", withoutFirstPlain, want)
	}
}

func TestPonOptions_WhenTheDiscardIsTheRedFive_ShouldOfferThePlainPairOnce(t *testing.T) {
	hand := copies(t, 1, "55m1z")

	got := offer.PonOptions(hand, false, copyOf(t, 0, "5m"))
	if want := [][2]tile.TileID{{hand[0], hand[1]}}; !slices.Equal(got, want) {
		t.Errorf("PonOptions = %v, want %v", got, want)
	}
}

func TestPonOptions_WhenThreePlainCopiesAreHeld_ShouldTakeTheFirstTwoInHandOrder(t *testing.T) {
	hand := copies(t, 1, "555p")

	got := offer.PonOptions(hand, false, copyOf(t, 0, "5p"))
	if want := [][2]tile.TileID{{hand[0], hand[1]}}; !slices.Equal(got, want) {
		t.Errorf("PonOptions = %v, want %v", got, want)
	}
}

func TestPonOptions_WhenInRiichiOrHoldingOneCopy_ShouldOfferNone(t *testing.T) {
	hand := copies(t, 0, "556m")

	if got := offer.PonOptions(hand, true, copyOf(t, 3, "5m")); len(got) != 0 {
		t.Errorf("PonOptions in riichi = %v, want none", got)
	}

	if got := offer.PonOptions(hand, false, copyOf(t, 3, "6m")); len(got) != 0 {
		t.Errorf("PonOptions with one copy = %v, want none", got)
	}
}

func TestPaoOfMeld_WhenPonCompletesTheThirdDragon_ShouldMakeTheDiscarderLiable(t *testing.T) {
	melds := []play.MeldView{
		calledMeld(t, play.MeldPon, 0, "555z", seat(t, 2)),
		calledMeld(t, play.MeldPon, 0, "666z", seat(t, 3)),
	}

	got := offer.PaoOfMeld(melds, calledMeld(t, play.MeldPon, 0, "777z", seat(t, 1)))
	if want := play.Some(seat(t, 1)); got != want {
		t.Errorf("PaoOfMeld = %v, want %v", got, want)
	}
}

func TestPaoOfMeld_WhenTwoDragonPonsAndASuitedPon_ShouldMakeNobodyLiable(t *testing.T) {
	melds := []play.MeldView{
		calledMeld(t, play.MeldPon, 0, "555z", seat(t, 2)),
		calledMeld(t, play.MeldPon, 0, "666z", seat(t, 3)),
	}

	if got := offer.PaoOfMeld(melds, calledMeld(t, play.MeldPon, 0, "999m", seat(t, 1))); got.OK {
		t.Errorf("PaoOfMeld = %v, want nobody", got)
	}
}

func TestPaoOfMeld_WhenThePonIsNotTheThirdDragon_ShouldMakeNobodyLiable(t *testing.T) {
	sixZ := calledMeld(t, play.MeldPon, 0, "666z", seat(t, 1))
	oneDragon := []play.MeldView{calledMeld(t, play.MeldPon, 0, "555z", seat(t, 2))}

	if got := offer.PaoOfMeld(nil, sixZ); got.OK {
		t.Errorf("PaoOfMeld with no dragon = %v, want nobody", got)
	}

	if got := offer.PaoOfMeld(oneDragon, sixZ); got.OK {
		t.Errorf("PaoOfMeld with one dragon = %v, want nobody", got)
	}
}

func TestPaoOfMeld_WhenTheThirdWindIsCalled_ShouldMakeNobodyLiable(t *testing.T) {
	melds := []play.MeldView{
		calledMeld(t, play.MeldPon, 0, "111z", seat(t, 1)),
		calledMeld(t, play.MeldPon, 0, "222z", seat(t, 1)),
	}

	if got := offer.PaoOfMeld(melds, calledMeld(t, play.MeldPon, 0, "333z", seat(t, 1))); got.OK {
		t.Errorf("PaoOfMeld = %v, want nobody", got)
	}
}

func TestPaoOfMeld_WhenTheFourthWindIsCalled_ShouldMakeTheDiscarderLiable(t *testing.T) {
	melds := []play.MeldView{
		calledMeld(t, play.MeldPon, 0, "111z", seat(t, 1)),
		calledMeld(t, play.MeldPon, 0, "222z", seat(t, 1)),
		calledMeld(t, play.MeldPon, 0, "333z", seat(t, 1)),
	}

	got := offer.PaoOfMeld(melds, calledMeld(t, play.MeldPon, 0, "444z", seat(t, 2)))
	if want := play.Some(seat(t, 2)); got != want {
		t.Errorf("PaoOfMeld = %v, want %v", got, want)
	}
}

func TestPaoOfMeld_WhenTheThirdDragonIsAddedOrClosedKan_ShouldMakeNobodyLiable(t *testing.T) {
	melds := []play.MeldView{
		calledMeld(t, play.MeldPon, 0, "555z", seat(t, 2)),
		calledMeld(t, play.MeldPon, 0, "666z", seat(t, 3)),
	}

	added := offer.PaoOfMeld(melds, calledMeld(t, play.MeldAddedKan, 0, "7777z", seat(t, 1)))
	closed := offer.PaoOfMeld(melds, closedKan(t, "7777z"))

	if added.OK {
		t.Errorf("PaoOfMeld of an added kan = %v, want nobody", added)
	}

	if closed.OK {
		t.Errorf("PaoOfMeld of a closed kan = %v, want nobody", closed)
	}
}

func TestNewMeldView_ShouldSortTheTilesAndNameTheCalledTileAndItsDiscarder(t *testing.T) {
	called, taken := copyOf(t, 3, "4m"), copies(t, 0, "56m")

	got := offer.NewMeldView(play.MeldChi, called, []tile.TileID{taken[1], taken[0]}, seat(t, 0))

	want := play.MeldView{
		Kind:   play.MeldChi,
		Tiles:  []tile.TileID{called, taken[0], taken[1]},
		Called: play.Some(called),
		From:   play.Some(seat(t, 0)),
	}

	sameTiles := slices.Equal(got.Tiles, want.Tiles)
	if got.Kind != want.Kind || !sameTiles || got.Called != want.Called || got.From != want.From {
		t.Errorf("NewMeldView = %v, want %v", got, want)
	}
}

func TestMeldOffers_WhenTheDiscardIsTheKamichas_ShouldListTheOpenKanThePonThenTheChis(t *testing.T) {
	hand := copies(t, 0, "444m56m19p")
	discard := copyOf(t, 3, "4m")
	caller, kamicha := seat(t, 1), seat(t, 0)

	fromKamicha, err := offer.CheckedMeldOffers(hand, false, caller, kamicha, discard, [4]int{}, 10)
	if err != nil {
		t.Fatalf("CheckedMeldOffers error = %v", err)
	}

	fromToimen := offer.MeldOffers(hand, false, caller, seat(t, 2), discard, [4]int{}, 10)

	kan, pon := play.KanAction(play.KanOpen, discard), play.PonAction([2]tile.TileID{hand[0], hand[1]})
	chi := play.ChiAction([2]tile.TileID{hand[3], hand[4]})
	if want := []play.Action{kan, pon, chi}; !slices.Equal(fromKamicha, want) {
		t.Errorf("MeldOffers from the kamicha = %v, want %v", fromKamicha, want)
	}

	if want := []play.Action{kan, pon}; !slices.Equal(fromToimen, want) {
		t.Errorf("MeldOffers from the toimen = %v, want %v", fromToimen, want)
	}
}

func TestMeldOffers_WhenFourKansAbortOrTheWallIsEmpty_ShouldStop(t *testing.T) {
	hand := copies(t, 0, "444m56m19p")
	discard := copyOf(t, 3, "4m")
	pon := play.PonAction([2]tile.TileID{hand[0], hand[1]})

	if got := offer.MeldOffers(hand, false, seat(t, 1), seat(t, 0), discard, [4]int{2, 2, 0, 0}, 10); len(got) != 0 {
		t.Errorf("MeldOffers at four kans by two seats = %v, want none", got)
	}

	oneSeat := offer.MeldOffers(hand, false, seat(t, 1), seat(t, 2), discard, [4]int{4, 0, 0, 0}, 10)
	if want := []play.Action{pon}; !slices.Equal(oneSeat, want) {
		t.Errorf("MeldOffers at four kans by one seat = %v, want %v", oneSeat, want)
	}

	if got := offer.MeldOffers(hand, false, seat(t, 1), seat(t, 0), discard, [4]int{}, 0); len(got) != 0 {
		t.Errorf("MeldOffers on an empty wall = %v, want none", got)
	}
}

func TestMeldOffers_WhenTheCallerIsTheDiscarder_ShouldOfferNone(t *testing.T) {
	hand := copies(t, 0, "444m56m19p")

	if got := offer.MeldOffers(hand, false, seat(t, 1), seat(t, 1), copyOf(t, 3, "4m"), [4]int{}, 10); len(got) != 0 {
		t.Errorf("MeldOffers = %v, want none", got)
	}
}

func TestCheckedMeldOffers_WhenAHandIDIsHeldTwice_ShouldReportTheDuplicate(t *testing.T) {
	heldTwice := []tile.TileID{id(t, 1), id(t, 1)}

	_, err := offer.CheckedMeldOffers(heldTwice, false, seat(t, 1), seat(t, 0), id(t, 2), [4]int{}, 10)

	if want := (meld.DuplicateTileError{Tile: id(t, 1)}); !errors.Is(err, want) {
		t.Errorf("CheckedMeldOffers error = %v, want %v", err, want)
	}
}

func TestMeldOffers_WhenKanCountsAreHuge_ShouldCountThemAsFourOrMore(t *testing.T) {
	triplet := copies(t, 0, "444m56m")
	fourMan := copyOf(t, 3, "4m")

	oneSeat := offer.MeldOffers(triplet, false, seat(t, 1), seat(t, 2), fourMan, [4]int{math.MaxInt, 0, 0, 0}, 10)
	twoSeats := offer.MeldOffers(triplet, false, seat(t, 1), seat(t, 0), fourMan, [4]int{math.MaxInt, 1, 0, 0}, 10)

	if want := []play.Action{play.PonAction([2]tile.TileID{triplet[0], triplet[1]})}; !slices.Equal(oneSeat, want) {
		t.Errorf("MeldOffers with one seat's huge count = %v, want %v", oneSeat, want)
	}

	if len(twoSeats) != 0 {
		t.Errorf("MeldOffers with two seats' kans = %v, want none", twoSeats)
	}
}
