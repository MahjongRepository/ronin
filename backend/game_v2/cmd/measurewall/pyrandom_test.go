package main

import (
	"encoding/hex"
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestPythonRandom_WhenSeededWithAString_ShouldYieldPythonsBytes(t *testing.T) {
	r := newPythonRandom("ronin-measure-wall-engine-0")

	first := hex.EncodeToString(r.randBytes(96))
	second := hex.EncodeToString(r.randBytes(96))

	want := "946c4802c4114d3dd93d49d4a525bcf6c6ba1538618eff0c5bde595f1aed822ab06f6232b4ec358f2b5a0c494ee9f2d80d" +
		"1bacbfbd53d79d94f210bd60275a337db83c4f8d15013e8e5ae3ba14d1f2a7916e94d74fe3a0b20ff8f2d3fb5d5aaf"
	if first != want {
		t.Errorf("first randBytes(96) = %s, want %s", first, want)
	}

	if second[:32] != "ea4716b130ac7090457e87f5e84297bf" {
		t.Errorf("second randBytes(96) starts %s, want ea4716b130ac7090457e87f5e84297bf", second[:32])
	}
}

func TestPythonRandom_WhenShufflingTheTileIDs_ShouldDealPythonsPermutations(t *testing.T) {
	r := newPythonRandom("ronin-measure-wall-control-0")
	first := identity(tile.TileIDCount)
	second := identity(tile.TileIDCount)

	r.shuffle(first)
	r.shuffle(second)

	wantHead := []int{45, 69, 124, 42, 115, 81, 40, 50, 11, 25, 63, 8, 98, 110, 22, 64, 80, 23, 62, 54}
	if !slices.Equal(first[:20], wantHead) || !slices.Equal(first[131:], []int{78, 102, 118, 60, 133}) {
		t.Errorf("first shuffle = %v, want head %v and tail [78 102 118 60 133]", first, wantHead)
	}

	if want := []int{101, 53, 130, 26, 69, 129, 47, 94, 23, 61}; !slices.Equal(second[:10], want) {
		t.Errorf("second shuffle head = %v, want %v", second[:10], want)
	}
}
