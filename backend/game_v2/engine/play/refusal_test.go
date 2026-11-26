package play_test

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
)

func TestRefusalKindString_ShouldBeItsWireIdentifier(t *testing.T) {
	for kind, want := range map[play.RefusalKind]string{
		play.RefusalRule:       "rule",
		play.RefusalNotOffered: "not_offered",
		play.RefusalNotAwaited: "not_awaited",
		play.RefusalKind(3):    "play.RefusalKind(3)",
	} {
		if got := kind.String(); got != want {
			t.Errorf("RefusalKind(%d).String = %q, want %q", kind, got, want)
		}
	}
}

func TestRefusalCodeString_ShouldBeItsWireIdentifier(t *testing.T) {
	for code, want := range map[play.RefusalCode]string{
		play.CodeTileNotHeld:         "tile_not_held",
		play.CodeNotOffered:          "not_offered",
		play.CodeWrongPhase:          "wrong_phase",
		play.CodeSeatNotAwaited:      "seat_not_awaited",
		play.CodeAlreadyAnswered:     "already_answered",
		play.CodeRiichiDrawnTileOnly: "riichi_drawn_tile_only",
		play.CodeRiichiBreaksTenpai:  "riichi_breaks_tenpai",
		play.CodeKuikae:              "kuikae",
		play.RefusalCode(8):          "play.RefusalCode(8)",
	} {
		if got := code.String(); got != want {
			t.Errorf("RefusalCode(%d).String = %q, want %q", code, got, want)
		}
	}
}
