package wall_test

import (
	"errors"
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/wall"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

type kanStep int

const (
	kanRevealedNow kanStep = iota
	kanRevealedLater
	revealPending
	clearPending
)

func checkIndicatorIntegrity(t *testing.T, w wall.Wall, drawn []tile.TileID) {
	t.Helper()
	dead := w.Tiles()[w.LiveCount():]
	if len(dead) != 14 {
		t.Errorf("dead wall holds %d tiles, want 14", len(dead))
	}

	for _, played := range append(drawn, w.Live()...) {
		if slices.Contains(dead, played) {
			t.Errorf("tile %d is both in play and in the dead wall", played.Index())
		}
	}
	if w.RevealedCount()+w.PendingDoraCount() > 5 {
		t.Errorf("revealed %d + pending %d exceed 5", w.RevealedCount(), w.PendingDoraCount())
	}

	dora, ura := w.DoraIndicators(), w.UraIndicators()
	if len(dora) != len(ura) {
		t.Fatalf("%d dora indicators but %d ura", len(dora), len(ura))
	}
	stacks := w.Indicators()
	for i, indicator := range dora {
		at := slices.IndexFunc(stacks[:], func(s wall.Stack) bool { return s.Top == indicator })
		if at < 0 || stacks[at].Bottom != ura[i] {
			t.Errorf("dora %d has ura %d, not the tile beneath it", indicator.Index(), ura[i].Index())
		}
	}
}

func TestDoraReveals_WhenKansAndRevealsInterleave_ShouldKeepIndicatorsPairedAndOutOfPlay(t *testing.T) {
	sequences := [][]kanStep{
		{kanRevealedNow, kanRevealedNow, kanRevealedNow, kanRevealedNow},
		{kanRevealedLater, revealPending, kanRevealedLater, revealPending, kanRevealedLater, revealPending, kanRevealedLater, revealPending},
		{kanRevealedLater, kanRevealedNow, revealPending, kanRevealedLater, kanRevealedLater, revealPending},
		{kanRevealedLater, clearPending, kanRevealedNow, kanRevealedNow, kanRevealedLater, clearPending},
		{kanRevealedLater, kanRevealedLater, kanRevealedLater, kanRevealedLater, revealPending},
	}

	for _, sequence := range sequences {
		w := wall.FromSeed(fixedSeed(t), 0, seat(t, 0))
		original := w.Indicators()
		var drawn []tile.TileID
		kans := 0
		for _, step := range sequence {
			switch step {
			case kanRevealedNow:
				drawn = append(drawn, mustDrawRinshan(t, &w))
				kans++
				mustAddDoraIndicator(t, &w)
			case kanRevealedLater:
				drawn = append(drawn, mustDrawRinshan(t, &w))
				kans++
				mustIncrementPendingDora(t, &w)
			case revealPending:
				w.RevealPendingDora()
			case clearPending:
				w.ClearPendingDora()
			}

			checkIndicatorIntegrity(t, w, drawn)
			if w.Indicators() != original {
				t.Errorf("sequence %v: indicator stacks changed", sequence)
			}
		}

		if len(w.Reserve()) != kans {
			t.Errorf("sequence %v: reserve holds %d, want %d", sequence, len(w.Reserve()), kans)
		}
	}
}

func TestAddDoraIndicator_ShouldRevealSuccessiveIndicatorTops(t *testing.T) {
	w := orderedWall(t)
	first, second := mustAddDoraIndicator(t, &w), mustAddDoraIndicator(t, &w)

	if first.Index() != 125 || second.Index() != 126 {
		t.Errorf("revealed %d, %d; want 125, 126", first.Index(), second.Index())
	}
	if got := numbers(w.DoraIndicators()); !slices.Equal(got, []int{124, 125, 126}) {
		t.Errorf("dora indicators = %v", got)
	}
}

func TestAddDoraIndicator_WhenAllFiveAreRevealed_ShouldRefuse(t *testing.T) {
	w := orderedWall(t)
	for range 4 {
		mustAddDoraIndicator(t, &w)
	}

	if _, err := w.AddDoraIndicator(); !errors.Is(err, wall.IndicatorsExhaustedError{}) {
		t.Errorf("AddDoraIndicator error = %v, want indicators exhausted", err)
	}
}

func TestRevealPendingDora_WhenTwoArePending_ShouldRevealBothInOrderAndClearPending(t *testing.T) {
	w := orderedWall(t)
	mustIncrementPendingDora(t, &w)
	mustIncrementPendingDora(t, &w)

	if got := numbers(w.RevealPendingDora()); !slices.Equal(got, []int{125, 126}) {
		t.Errorf("revealed = %v, want [125 126]", got)
	}
	if w.PendingDoraCount() != 0 {
		t.Errorf("pending = %d, want 0", w.PendingDoraCount())
	}
	if got := numbers(w.DoraIndicators()); !slices.Equal(got, []int{124, 125, 126}) {
		t.Errorf("dora indicators = %v", got)
	}
}

func TestRevealPendingDora_WhenNoneArePending_ShouldChangeNothing(t *testing.T) {
	w := orderedWall(t)
	if got := w.RevealPendingDora(); len(got) != 0 {
		t.Errorf("revealed = %v, want none", numbers(got))
	}
	if w != orderedWall(t) {
		t.Error("the wall changed")
	}
}

func TestIncrementPendingDora_WhenRevealedAndPendingMakeFive_ShouldRefuse(t *testing.T) {
	w := orderedWall(t)
	for range 2 {
		mustAddDoraIndicator(t, &w)
	}

	for range 2 {
		mustIncrementPendingDora(t, &w)
	}

	if err := w.IncrementPendingDora(); !errors.Is(err, wall.IndicatorsExhaustedError{}) {
		t.Errorf("IncrementPendingDora error = %v, want indicators exhausted", err)
	}
}

func TestAddDoraIndicator_WhenPendingRevealsFillTheFive_ShouldRefuseAndChangeNothing(t *testing.T) {
	w := orderedWall(t)
	for range 2 {
		mustAddDoraIndicator(t, &w)
	}

	for range 2 {
		mustIncrementPendingDora(t, &w)
	}

	before := w

	if _, err := w.AddDoraIndicator(); !errors.Is(err, wall.IndicatorsExhaustedError{}) {
		t.Errorf("AddDoraIndicator error = %v, want indicators exhausted", err)
	}
	if w != before {
		t.Error("the refused reveal changed the wall")
	}
	if got := numbers(w.RevealPendingDora()); !slices.Equal(got, []int{127, 128}) {
		t.Errorf("pending revealed = %v, want [127 128]", got)
	}
}

func TestClearPendingDora_ShouldDropThemWithoutRevealing(t *testing.T) {
	w := orderedWall(t)
	mustIncrementPendingDora(t, &w)
	w.ClearPendingDora()

	if w.PendingDoraCount() != 0 {
		t.Errorf("pending = %d, want 0", w.PendingDoraCount())
	}
	if got := numbers(w.DoraIndicators()); !slices.Equal(got, []int{124}) {
		t.Errorf("dora indicators = %v, want [124]", got)
	}
}

func TestUraIndicators_WhenAKanDoraIsRevealed_ShouldGiveOnePerRevealedDora(t *testing.T) {
	w := orderedWall(t)
	mustAddDoraIndicator(t, &w)

	if got := numbers(w.UraIndicators()); !slices.Equal(got, []int{131, 132}) {
		t.Errorf("ura indicators = %v, want [131 132]", got)
	}
}
