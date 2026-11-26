package offer_test

import (
	"errors"
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/offer"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func tenpaiOnOneAndNineManAfterDrawingEast(t *testing.T) []tile.TileID {
	t.Helper()
	return concat(copies(t, 0, "1123456788899m"), copies(t, 0, "1z"))
}

func offersRiichi(t *testing.T, hand []tile.TileID, melds []play.MeldView, inRiichi bool, score, liveTiles int) bool {
	t.Helper()
	discards, err := offer.CheckedRiichiDiscards(hand, melds, inRiichi, score, liveTiles)
	if err != nil {
		t.Fatalf("CheckedRiichiDiscards error = %v", err)
	}

	return len(discards) > 0
}

func TestRiichiDiscards_WhenTheHandIsClosedAndTenpai_ShouldOfferRiichi(t *testing.T) {
	if !offersRiichi(t, tenpaiOnOneAndNineManAfterDrawingEast(t), nil, false, 25000, 70) {
		t.Error("riichi not offered, want offered")
	}
}

func TestRiichiDiscards_WhenAlreadyInRiichi_ShouldOfferNone(t *testing.T) {
	if offersRiichi(t, tenpaiOnOneAndNineManAfterDrawingEast(t), nil, true, 24000, 70) {
		t.Error("riichi offered, want none")
	}
}

func TestRiichiDiscards_WhenBelowTheRiichiCost_ShouldOfferNone(t *testing.T) {
	hand := tenpaiOnOneAndNineManAfterDrawingEast(t)

	if offersRiichi(t, hand, nil, false, 999, 70) {
		t.Error("riichi offered at 999 points, want none")
	}

	if !offersRiichi(t, hand, nil, false, 1000, 70) {
		t.Error("riichi not offered at 1000 points, want offered")
	}
}

func TestRiichiDiscards_WhenFewerThanFourLiveTiles_ShouldOfferNone(t *testing.T) {
	hand := tenpaiOnOneAndNineManAfterDrawingEast(t)

	if offersRiichi(t, hand, nil, false, 25000, 3) {
		t.Error("riichi offered with 3 live tiles, want none")
	}

	if !offersRiichi(t, hand, nil, false, 25000, 4) {
		t.Error("riichi not offered with 4 live tiles, want offered")
	}
}

func TestRiichiDiscards_WhenTheHandIsFarFromTenpai_ShouldOfferNone(t *testing.T) {
	farFromTenpai := concat(copies(t, 3, "13579m2468p1357s"), copies(t, 0, "1z"))

	if offersRiichi(t, farFromTenpai, nil, false, 25000, 70) {
		t.Error("riichi offered, want none")
	}
}

func TestRiichiDiscards_WhenBesideAClosedKanOrAnOpenMeld_ShouldOfferOnlyBesideTheClosedKan(t *testing.T) {
	hand := concat(copies(t, 0, "1123456788m"), copies(t, 0, "1z"))

	got := offer.RiichiDiscards(hand, []play.MeldView{closedKan(t, "9999m")}, false, 25000, 70)

	if want := copies(t, 0, "1z"); !slices.Equal(got, want) {
		t.Errorf("RiichiDiscards beside a closed kan = %v, want %v", got, want)
	}

	if offersRiichi(t, hand, []play.MeldView{calledMeld(t, play.MeldPon, 0, "999m", seat(t, 1))}, false, 25000, 70) {
		t.Error("riichi offered beside a pon, want none")
	}
}

func TestRiichiDiscards_WhenTheDrawnHandIsComplete_ShouldOfferEveryDiscard(t *testing.T) {
	hand := concat(copies(t, 0, "1123456788899m"), copies(t, 3, "9m"))

	if got := offer.RiichiDiscards(hand, nil, false, 25000, 70); !slices.Equal(got, hand) {
		t.Errorf("RiichiDiscards = %v, want %v", got, hand)
	}
}

func TestRiichiDiscards_ShouldListOnlyTheTenpaiKeepingTilesInHandOrder(t *testing.T) {
	hand := concat(copies(t, 0, "123456789m1p"), copies(t, 1, "1p"), copies(t, 0, "23p9s"))

	got := offer.RiichiDiscards(hand, nil, false, 25000, 70)
	if want := concat(copies(t, 0, "1p"), copies(t, 1, "1p"), copies(t, 0, "9s")); !slices.Equal(got, want) {
		t.Errorf("RiichiDiscards = %v, want %v", got, want)
	}
}

func TestCheckedRiichiDiscards_WhenOneIDIsHeldFiveTimes_ShouldReportTheDuplicateEvenInRiichi(t *testing.T) {
	zero := id(t, 0)

	_, err := offer.CheckedRiichiDiscards([]tile.TileID{zero, zero, zero, zero, zero}, nil, true, 25000, 70)

	if want := (meld.DuplicateTileError{Tile: zero}); !errors.Is(err, want) {
		t.Errorf("CheckedRiichiDiscards error = %v, want %v", err, want)
	}
}
