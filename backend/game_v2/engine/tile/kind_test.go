package tile_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestTerminalAndHonorKinds_ShouldBeTheKindsIsTerminalOrHonorAccepts(t *testing.T) {
	var accepted []tile.Kind
	for kind := range tile.Kind(64) {
		if kind.IsTerminalOrHonor() {
			accepted = append(accepted, kind)
		}
	}

	listed := tile.TerminalAndHonorKinds()
	if !slices.Equal(accepted, listed[:]) {
		t.Errorf("kinds IsTerminalOrHonor accepts = %v, want %v", accepted, listed)
	}

	if got := tile.Mask(listed[:]...); got != tile.TerminalOrHonorMask {
		t.Errorf("Mask(TerminalAndHonorKinds) = %#x, want %#x", got, tile.TerminalOrHonorMask)
	}
}

func TestSuitStartsAndMasks_ShouldSpanTheNineKindsOfEachSuit(t *testing.T) {
	starts, masks := tile.SuitStarts(), tile.SuitMasks()
	for suit, start := range starts {
		var kinds []tile.Kind
		for rank := range tile.Kind(9) {
			kinds = append(kinds, start+rank)
		}
		if got := tile.Mask(kinds...); got != masks[suit] {
			t.Errorf("suit %d mask from start %d = %#x, want %#x", suit, start, got, masks[suit])
		}

		if start.Simplify() != 0 || (start+8).Simplify() != 8 || start.IsHonor() {
			t.Errorf("suit %d start %d does not begin a suit", suit, start)
		}
	}
}

func TestWindAndDragonKinds_ShouldMakeUpTheHonors(t *testing.T) {
	winds, dragons := tile.WindKinds(), tile.DragonKinds()
	for i, kind := range winds {
		if want := tile.Wind(i).Kind(); kind != want {
			t.Errorf("WindKinds()[%d] = %d, want %d", i, kind, want)
		}
	}

	if got := tile.Mask(append(winds[:], dragons[:]...)...); got != tile.HonorMask {
		t.Errorf("Mask(winds, dragons) = %#x, want %#x", got, tile.HonorMask)
	}
}
