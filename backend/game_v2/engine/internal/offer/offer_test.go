package offer_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/offer"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestTurnDiscards_WhenInRiichiAfterADraw_ShouldAllowOnlyTheDrawnTile(t *testing.T) {
	hand := copies(t, 0, "123456789m12345p")
	drawn := hand[13]

	inRiichi := offer.TurnDiscards(hand, play.Some(drawn), true, nil)
	notInRiichi := offer.TurnDiscards(hand, play.Some(drawn), false, nil)

	if want := []tile.TileID{drawn}; !slices.Equal(inRiichi, want) {
		t.Errorf("TurnDiscards in riichi = %v, want %v", inRiichi, want)
	}

	if !slices.Equal(notInRiichi, hand) {
		t.Errorf("TurnDiscards out of riichi = %v, want %v", notInRiichi, hand)
	}
}

func TestTurnDiscards_WhenAfterACall_ShouldLeaveOutTheKuikaeKindsInHandOrder(t *testing.T) {
	hand := copies(t, 0, "1145m")
	kuikae := []tile.Kind{hand[2].Kind(), hand[0].Kind()}

	restricted := offer.TurnDiscards(hand, play.Option[tile.TileID]{}, false, kuikae)
	free := offer.TurnDiscards(hand, play.Option[tile.TileID]{}, false, nil)

	if want := []tile.TileID{hand[3]}; !slices.Equal(restricted, want) {
		t.Errorf("TurnDiscards with kuikae = %v, want %v", restricted, want)
	}

	if !slices.Equal(free, hand) {
		t.Errorf("TurnDiscards without kuikae = %v, want %v", free, hand)
	}
}

func TestLastTileFlags_ShouldNeedAnEmptyLiveWallAndNoKanTile(t *testing.T) {
	if !offer.IsHaitei(0, false) || offer.IsHaitei(0, true) || offer.IsHaitei(1, false) {
		t.Error("IsHaitei is not true only for a live draw from an empty wall")
	}

	if !offer.IsHoutei(0, play.SourceDiscard) || offer.IsHoutei(0, play.SourceAddedKan) ||
		offer.IsHoutei(0, play.SourceClosedKan) || offer.IsHoutei(1, play.SourceDiscard) {
		t.Error("IsHoutei is not true only for a discard on an empty wall")
	}
}
