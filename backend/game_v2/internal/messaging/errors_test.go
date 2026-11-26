package messaging_test

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func TestRefusalError_WhenTheEngineRefusesAnAction_ShouldAnswerItsWireCodeAndMessage(t *testing.T) {
	notAwaited := play.Refusal{Kind: play.RefusalNotAwaited, Code: play.CodeSeatNotAwaited}
	for _, c := range []struct {
		name    string
		action  play.Action
		refusal play.Refusal
		code    messaging.GameErrorCode
		message string
	}{
		{
			"round not in play", play.PassAction(),
			play.Refusal{Kind: play.RefusalNotAwaited, Code: play.CodeWrongPhase},
			"invalid_action", "round is not in progress",
		},
		{"discard out of turn", play.DiscardAction(id(t, 10)), notAwaited, "not_your_turn", "not your turn"},
		{"closed kan out of turn", play.KanAction(play.KanClosed, id(t, 8)), notAwaited, "not_your_turn", "not your turn"},
		{
			"pon answered twice", play.PonAction([2]tile.TileID{id(t, 41), id(t, 42)}),
			play.Refusal{Kind: play.RefusalNotAwaited, Code: play.CodeAlreadyAnswered},
			"invalid_pon", "no pending call prompt",
		},
		{"open kan without a prompt", play.KanAction(play.KanOpen, id(t, 8)), notAwaited, "invalid_kan", "no pending call prompt"},
		{"pass without a prompt", play.PassAction(), notAwaited, "invalid_pass", "no pending call prompt"},
		{
			"kuikae discard", play.DiscardAction(id(t, 10)),
			play.Refusal{Kind: play.RefusalRule, Code: play.CodeKuikae},
			"invalid_discard", "tile 10 is not a legal discard (kuikae or riichi tsumogiri)",
		},
		{
			"riichi discard of a held tile", play.DiscardAction(id(t, 12)),
			play.Refusal{Kind: play.RefusalRule, Code: play.CodeRiichiDrawnTileOnly},
			"invalid_discard", "tile 12 is not a legal discard (kuikae or riichi tsumogiri)",
		},
		{
			"riichi breaking tenpai", play.RiichiAction(id(t, 7)),
			play.Refusal{Kind: play.RefusalRule, Code: play.CodeRiichiBreaksTenpai},
			"invalid_riichi", "hand is not tenpai after discarding tile 7",
		},
	} {
		t.Run(c.name, func(t *testing.T) {
			got, ok := messaging.RefusalError(c.action, c.refusal, 6)
			want := messaging.GameError{Code: c.code, Message: c.message, WaitID: 6}
			if !ok || got != want {
				t.Errorf("%s: RefusalError = %+v, %v; want %+v", c.name, got, ok, want)
			}
		})
	}
}

func TestRefusalError_WhenTheInputIsNoneAClientBuilds_ShouldHaveNoGameError(t *testing.T) {
	for _, refusal := range []play.Refusal{
		{Kind: play.RefusalNotOffered, Code: play.CodeTileNotHeld},
		{Kind: play.RefusalNotOffered, Code: play.CodeNotOffered},
	} {
		if got, ok := messaging.RefusalError(play.DiscardAction(id(t, 10)), refusal, 6); ok {
			t.Errorf("RefusalError(%+v) = %+v, want none", refusal, got)
		}
	}
}

func TestGameError_ShouldShapeTheErrorEventNamingTheEchoedWaitID(t *testing.T) {
	pon := play.PonAction([2]tile.TileID{id(t, 41), id(t, 42)})
	for _, c := range []struct {
		name string
		got  messaging.GameError
		want wire.Map
	}{
		{"called tile mismatch", messaging.CalledTileMismatch(pon, 3), wire.Map{
			{Key: wire.KeyEventType, Value: wire.Int(7)},
			{Key: wire.KeyGameErrorCode, Value: wire.Str("invalid_pon")},
			{Key: wire.KeyGameErrorMessage, Value: wire.Str("tile_id mismatch")},
			{Key: wire.KeyWaitID, Value: wire.Int(3)},
		}},
		{"stale action", messaging.StaleAction(2), wire.Map{
			{Key: wire.KeyEventType, Value: wire.Int(7)},
			{Key: wire.KeyGameErrorCode, Value: wire.Str("stale_action")},
			{Key: wire.KeyGameErrorMessage, Value: wire.Str("the wait this action answers has already ended")},
			{Key: wire.KeyWaitID, Value: wire.Int(2)},
		}},
	} {
		t.Run(c.name, func(t *testing.T) {
			assertMap(t, c.name, c.got.Payload(), c.want)
		})
	}
}
