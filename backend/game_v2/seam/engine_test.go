package seam_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
)

func TestNewGame_ShouldYieldStartedEventWithFullWall(t *testing.T) {
	_, events := engine.NewGame("seed")

	want := []engine.Event{{Kind: engine.EventGameStarted, WallTileCount: 136}}
	if !slices.Equal(events, want) {
		t.Errorf("NewGame events = %v, want %v", events, want)
	}
}

func TestAct_WhenGameIsNew_ShouldRefuseAsNotAwaited(t *testing.T) {
	game, _ := engine.NewGame("seed")

	events, refusal := game.Act(0, engine.Action{Kind: engine.ActionDiscard})

	if refusal == nil {
		t.Fatalf("Act refusal = nil, want %q", engine.RefusalNotAwaited)
	}
	if refusal.Reason != engine.RefusalNotAwaited {
		t.Errorf("Act refusal reason = %q, want %q", refusal.Reason, engine.RefusalNotAwaited)
	}
	if len(events) != 0 {
		t.Errorf("Act events = %v, want none", events)
	}
}
