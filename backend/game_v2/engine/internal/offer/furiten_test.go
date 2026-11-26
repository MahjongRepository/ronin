package offer_test

import (
	"errors"
	"strings"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/offer"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/score"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func waitsOf(t *testing.T, mpsz string) tile.Kinds {
	t.Helper()
	parsed, err := tile.ParseTiles(mpsz)
	if err != nil {
		t.Fatalf("ParseTiles(%q) error = %v", mpsz, err)
	}

	closed, err := tile.CountsFromTiles(parsed)
	if err != nil {
		t.Fatalf("CountsFromTiles(%q) error = %v", mpsz, err)
	}

	return hand.Waits(closed, tile.Counts{})
}

func ronSituation() score.Situation {
	return offer.BaseSituation(score.WinRon, tile.South, tile.East, play.Option[play.Riichi]{})
}

func tanyaoHand(t *testing.T) []tile.TileID {
	t.Helper()
	return copies(t, 0, "234567m234p55s67s")
}

func openNoYakuHand(t *testing.T) ([]tile.TileID, []play.MeldView) {
	t.Helper()
	return concat(copies(t, 0, "567p789s456s"), copies(t, 0, "1z")),
		[]play.MeldView{calledMeld(t, play.MeldChi, 0, "234m", seat(t, 3))}
}

func TestIsDiscardFuriten_WhenNoWaitIsDiscarded_ShouldBeFalse(t *testing.T) {
	if offer.IsDiscardFuriten(waitsOf(t, "123456789m1255p"), river(copies(t, 0, "1m"))) {
		t.Error("IsDiscardFuriten = true, want false")
	}
}

func TestIsDiscardFuriten_WhenAWaitIsDiscarded_ShouldBeTrue(t *testing.T) {
	if !offer.IsDiscardFuriten(waitsOf(t, "123456789m1255p"), river(copies(t, 0, "3p"))) {
		t.Error("IsDiscardFuriten = false, want true")
	}
}

func TestIsDiscardFuriten_WhenOneOfManyDiscardsIsAWait_ShouldBeTrue(t *testing.T) {
	if !offer.IsDiscardFuriten(waitsOf(t, "123456789m4555p"), river(copies(t, 0, "1m6p"))) {
		t.Error("IsDiscardFuriten = false, want true")
	}
}

func TestFuritenBlocksRon_WhenTemporaryOrRiichiFuriten_ShouldBeTrue(t *testing.T) {
	if !(offer.Furiten{Temporary: true}).BlocksRon() || !(offer.Furiten{Riichi: true}).BlocksRon() {
		t.Error("BlocksRon = false for temporary or riichi furiten, want true")
	}

	if (offer.Furiten{Shown: true}).BlocksRon() {
		t.Error("BlocksRon = true for a shown value only, want false")
	}
}

func TestFuriten_WhenARonIsDeclinedOrMissed_ShouldSetTheFlagsOfTheSeatsRiichi(t *testing.T) {
	tests := []struct {
		name string
		got  offer.Furiten
		want offer.Furiten
	}{
		{name: "declined", got: offer.Furiten{}.DeclineRon(false), want: offer.Furiten{Temporary: true}},
		{name: "declined in riichi", got: offer.Furiten{}.DeclineRon(true), want: offer.Furiten{Temporary: true, Riichi: true}},
		{name: "missed", got: offer.Furiten{}.MissRon(false), want: offer.Furiten{Temporary: true}},
		{name: "missed in riichi", got: offer.Furiten{}.MissRon(true), want: offer.Furiten{Riichi: true}},
		{
			name: "declined after riichi furiten",
			got:  offer.Furiten{Riichi: true}.DeclineRon(false),
			want: offer.Furiten{Temporary: true, Riichi: true},
		},
	}
	for _, c := range tests {
		t.Run(c.name, func(t *testing.T) {
			if c.got != c.want {
				t.Errorf("furiten = %+v, want %+v", c.got, c.want)
			}
		})
	}
}

func TestDiscardRon_WhenTheTileDoesNotComplete_ShouldBeNotComplete(t *testing.T) {
	candidate := offer.RonCandidate{Hand: tanyaoHand(t)}

	if got := offer.DiscardRon(candidate, copyOf(t, 1, "1m"), ronSituation()); got != offer.RonNotComplete {
		t.Errorf("DiscardRon = %v, want %v", got, offer.RonNotComplete)
	}
}

func TestDiscardRon_WhenTheCompleteOpenHandHasNoYaku_ShouldBeMissed(t *testing.T) {
	concealed, melds := openNoYakuHand(t)
	candidate := offer.RonCandidate{Hand: concealed, Melds: melds}

	if got := offer.DiscardRon(candidate, copyOf(t, 1, "1z"), ronSituation()); got != offer.RonMissed {
		t.Errorf("DiscardRon = %v, want %v", got, offer.RonMissed)
	}
}

func TestDiscardRon_WhenTheCompleteHandHasAYaku_ShouldBeOffered(t *testing.T) {
	candidate := offer.RonCandidate{Hand: tanyaoHand(t)}

	if got := offer.DiscardRon(candidate, copyOf(t, 1, "8s"), ronSituation()); got != offer.RonOffered {
		t.Errorf("DiscardRon = %v, want %v", got, offer.RonOffered)
	}
}

func TestDiscardRon_WhenFuritenOrAWaitIsInTheRiver_ShouldBeMissed(t *testing.T) {
	tests := []struct {
		name      string
		candidate offer.RonCandidate
	}{
		{name: "temporary furiten", candidate: offer.RonCandidate{Hand: tanyaoHand(t), Furiten: offer.Furiten{Temporary: true}}},
		{name: "discarded wait", candidate: offer.RonCandidate{Hand: tanyaoHand(t), River: river(copies(t, 2, "5s"))}},
	}
	for _, c := range tests {
		t.Run(c.name, func(t *testing.T) {
			if got := offer.DiscardRon(c.candidate, copyOf(t, 1, "8s"), ronSituation()); got != offer.RonMissed {
				t.Errorf("DiscardRon = %v, want %v", got, offer.RonMissed)
			}
		})
	}
}

func TestDiscardRon_ShouldMatchScoringWithRealDoraIndicators(t *testing.T) {
	noYakuHand, melds := openNoYakuHand(t)
	noYakuTile := copyOf(t, 1, "1z")
	tanyao, tanyaoTile := tanyaoHand(t), copyOf(t, 1, "8s")

	_, noYakuErr := offer.HandValue(noYakuHand, noYakuTile, offer.Scoring{
		Situation: ronSituation(), Melds: melds, DoraIndicators: copies(t, 0, "4z"),
	})
	_, tanyaoErr := offer.HandValue(tanyao, tanyaoTile, offer.Scoring{
		Situation: ronSituation(), DoraIndicators: copies(t, 0, "4s"),
	})

	if !errors.Is(noYakuErr, score.NoYakuError{}) {
		t.Errorf("HandValue with an east dora error = %v, want %v", noYakuErr, score.NoYakuError{})
	}

	noYakuCandidate := offer.RonCandidate{Hand: noYakuHand, Melds: melds}
	if got := offer.DiscardRon(noYakuCandidate, noYakuTile, ronSituation()); got != offer.RonMissed {
		t.Errorf("DiscardRon of the no-yaku hand = %v, want %v", got, offer.RonMissed)
	}

	if tanyaoErr != nil {
		t.Errorf("HandValue of tanyao error = %v, want nil", tanyaoErr)
	}

	if got := offer.DiscardRon(offer.RonCandidate{Hand: tanyao}, tanyaoTile, ronSituation()); got != offer.RonOffered {
		t.Errorf("DiscardRon of tanyao = %v, want %v", got, offer.RonOffered)
	}
}

func TestDiscardRon_WhenTheScorerRejectsTheCompletedHand_ShouldPanicWithAnEngineFault(t *testing.T) {
	candidate := offer.RonCandidate{Hand: []tile.TileID{id(t, 0)}}

	fault := faultOf(t, func() { offer.DiscardRon(candidate, id(t, 1), ronSituation()) })

	wrongCount, ok := errors.AsType[score.WrongTileCountError](fault)
	if !ok {
		t.Fatalf("DiscardRon fault = %v, want a score.WrongTileCountError", fault)
	}

	if !strings.Contains(fault.Error(), wrongCount.Error()) {
		t.Errorf("DiscardRon fault text = %q, want it to name %q", fault.Error(), wrongCount.Error())
	}
}

func TestMayRobKan_WhenWaitingOnTheTile_ShouldRobAnAddedKanButAClosedKanOnlyOnAKokushiWait(t *testing.T) {
	tanyao := offer.RonCandidate{Hand: tanyaoHand(t)}
	kokushi := offer.RonCandidate{Hand: copies(t, 0, "19m19p19s1234567z")}
	kokushiWithAPair := offer.RonCandidate{Hand: copies(t, 0, "119m19p19s123456z")}
	terminalChiitoitsu := offer.RonCandidate{Hand: copies(t, 0, "1199m1199p1199s1z")}
	furiten := offer.RonCandidate{Hand: tanyaoHand(t), Furiten: offer.Furiten{Riichi: true}}

	tests := []struct {
		name      string
		candidate offer.RonCandidate
		kind      play.KanKind
		robbed    tile.TileID
		want      bool
	}{
		{name: "added kan on a wait", candidate: tanyao, kind: play.KanAdded, robbed: copyOf(t, 1, "8s"), want: true},
		{name: "added kan off the waits", candidate: tanyao, kind: play.KanAdded, robbed: copyOf(t, 1, "9s"), want: false},
		{name: "closed kan on a plain wait", candidate: tanyao, kind: play.KanClosed, robbed: copyOf(t, 1, "8s"), want: false},
		{name: "closed kan on a kokushi wait", candidate: kokushi, kind: play.KanClosed, robbed: copyOf(t, 1, "1m"), want: true},
		{
			name:      "closed kan on a twelve-kind kokushi wait",
			candidate: kokushiWithAPair,
			kind:      play.KanClosed,
			robbed:    copyOf(t, 1, "7z"),
			want:      true,
		},
		{
			name:      "closed kan on a terminal and honor chiitoitsu wait",
			candidate: terminalChiitoitsu,
			kind:      play.KanClosed,
			robbed:    copyOf(t, 2, "1z"),
			want:      false,
		},
		{name: "furiten", candidate: furiten, kind: play.KanAdded, robbed: copyOf(t, 1, "8s"), want: false},
	}
	for _, c := range tests {
		t.Run(c.name, func(t *testing.T) {
			if got := offer.MayRobKan(c.candidate, c.kind, c.robbed); got != c.want {
				t.Errorf("MayRobKan = %t, want %t", got, c.want)
			}
		})
	}
}
