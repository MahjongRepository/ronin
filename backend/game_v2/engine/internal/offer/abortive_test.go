package offer_test

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/offer"
)

func TestHasNineTerminalKinds_WhenNineTerminalAndHonorKinds_ShouldAllow(t *testing.T) {
	if !offer.HasNineTerminalKinds(concat(copies(t, 0, "19m19p19s123z"), copies(t, 0, "22334m"))) {
		t.Error("HasNineTerminalKinds = false, want true")
	}
}

func TestHasNineTerminalKinds_WhenEightTerminalAndHonorKinds_ShouldForbid(t *testing.T) {
	if offer.HasNineTerminalKinds(concat(copies(t, 0, "19m19p19s12z"), copies(t, 0, "223345m"))) {
		t.Error("HasNineTerminalKinds = true, want false")
	}
}

func TestHasNineTerminalKinds_WhenTerminalsRepeat_ShouldCountEachKindOnce(t *testing.T) {
	if offer.HasNineTerminalKinds(concat(copies(t, 0, "1119m19p19s12z"), copies(t, 0, "2233m"))) {
		t.Error("HasNineTerminalKinds = true, want false")
	}
}

func TestIsFourWinds_WhenFourSameWindsAreDiscarded_ShouldAbort(t *testing.T) {
	if !offer.IsFourWinds(copies(t, 0, "1111z")) {
		t.Error("IsFourWinds = false, want true")
	}
}

func TestIsFourWinds_WhenTheWindsAreMixed_ShouldNotAbort(t *testing.T) {
	if offer.IsFourWinds(copies(t, 0, "1234z")) {
		t.Error("IsFourWinds = true, want false")
	}
}

func TestIsFourWinds_WhenTheTilesAreNotWinds_ShouldNotAbort(t *testing.T) {
	if offer.IsFourWinds(copies(t, 0, "1111m")) {
		t.Error("IsFourWinds of a suited kind = true, want false")
	}
	if offer.IsFourWinds(copies(t, 0, "5555z")) {
		t.Error("IsFourWinds of a dragon = true, want false")
	}
}

func TestIsFourWinds_WhenFewerOrMoreThanFourDiscards_ShouldNotAbort(t *testing.T) {
	if offer.IsFourWinds(copies(t, 0, "111z")) {
		t.Error("IsFourWinds of three discards = true, want false")
	}
	if offer.IsFourWinds(concat(copies(t, 0, "1111z"), copies(t, 1, "2z"))) {
		t.Error("IsFourWinds of five discards = true, want false")
	}
}
