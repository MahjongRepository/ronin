package messaging_test

import (
	"errors"
	"strings"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func gameAction(action messaging.GameAction, fields ...wire.Field) wire.Map {
	return append(wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(messaging.ClientGameAction)},
		{Key: wire.KeyWaitID, Value: wire.Int(4)},
		{Key: wire.KeyAction, Value: wire.Int(action)},
	}, fields...)
}

func tileField(n int) wire.Field {
	return wire.Field{Key: wire.KeyTileID, Value: wire.Int(n)}
}

func heldField(values ...wire.Value) wire.Field {
	return wire.Field{Key: wire.KeySequenceTiles, Value: wire.Array(values)}
}

func kanTypeField(name string) wire.Field {
	return wire.Field{Key: wire.KeyActionKanType, Value: wire.Str(name)}
}

func ticketMessage(typ messaging.ClientMessageType, ticket string) wire.Map {
	return wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(typ)},
		{Key: wire.KeyGameTicket, Value: wire.Str(ticket)},
	}
}

func isInvalidMessage(err error) bool {
	_, isType := errors.AsType[messaging.InvalidMessageError](err)
	return isType
}

func TestParseClientMessage_WhenAGameActionIsWellFormed_ShouldCarryItsEngineActionAndCalledTile(t *testing.T) {
	for _, c := range []struct {
		name    string
		message wire.Map
		want    messaging.GameActionMessage
	}{
		{"discard", gameAction(messaging.GameActionDiscard, tileField(135)), messaging.GameActionMessage{
			Action: messaging.GameActionDiscard, WaitID: 4, Play: play.Some(play.DiscardAction(id(t, 135))),
		}},
		{"riichi", gameAction(messaging.GameActionRiichi, tileField(8)), messaging.GameActionMessage{
			Action: messaging.GameActionRiichi, WaitID: 4, Play: play.Some(play.RiichiAction(id(t, 8))),
		}},
		{"pon", gameAction(messaging.GameActionPon, tileField(40), heldField(wire.Int(41), wire.Int(42))), messaging.GameActionMessage{
			Action: messaging.GameActionPon, WaitID: 4,
			Play: play.Some(play.PonAction([2]tile.TileID{id(t, 41), id(t, 42)})), Called: play.Some(id(t, 40)),
		}},
		{"chi", gameAction(messaging.GameActionChi, tileField(40), heldField(wire.Int(44), wire.Int(48))), messaging.GameActionMessage{
			Action: messaging.GameActionChi, WaitID: 4,
			Play: play.Some(play.ChiAction([2]tile.TileID{id(t, 44), id(t, 48)})), Called: play.Some(id(t, 40)),
		}},
		{"open kan", gameAction(messaging.GameActionKan, tileField(8), kanTypeField("open")), messaging.GameActionMessage{
			Action: messaging.GameActionKan, WaitID: 4, Play: play.Some(play.KanAction(play.KanOpen, id(t, 8))),
			Called: play.Some(id(t, 8)),
		}},
		{"closed kan", gameAction(messaging.GameActionKan, tileField(8), kanTypeField("closed")), messaging.GameActionMessage{
			Action: messaging.GameActionKan, WaitID: 4, Play: play.Some(play.KanAction(play.KanClosed, id(t, 8))),
		}},
		{"added kan", gameAction(messaging.GameActionKan, tileField(8), kanTypeField("added")), messaging.GameActionMessage{
			Action: messaging.GameActionKan, WaitID: 4, Play: play.Some(play.KanAction(play.KanAdded, id(t, 8))),
		}},
		{"pass with stray fields", gameAction(messaging.GameActionPass, tileField(999), heldField()), messaging.GameActionMessage{
			Action: messaging.GameActionPass, WaitID: 4, Play: play.Some(play.PassAction()),
		}},
		{"confirm round", gameAction(messaging.GameActionConfirmRound), messaging.GameActionMessage{
			Action: messaging.GameActionConfirmRound, WaitID: 4,
		}},
	} {
		t.Run(c.name, func(t *testing.T) {
			got, err := messaging.ParseClientMessage(c.message)
			if err != nil || got != c.want {
				t.Errorf("%s: ParseClientMessage = %+v, %v; want %+v", c.name, got, err, c.want)
			}
		})
	}
}

func TestParseClientMessage_WhenAGameActionIsMalformed_ShouldRefuseIt(t *testing.T) {
	for _, c := range []struct {
		name    string
		message wire.Map
	}{
		{"no wait id", wire.Map{
			{Key: wire.KeyEventType, Value: wire.Int(messaging.ClientGameAction)},
			{Key: wire.KeyAction, Value: wire.Int(messaging.GameActionPass)},
		}},
		{"boolean wait id", with(gameAction(messaging.GameActionPass), wire.KeyWaitID, wire.Bool(true))},
		{"string wait id", with(gameAction(messaging.GameActionPass), wire.KeyWaitID, wire.Str("3"))},
		{"float wait id", with(gameAction(messaging.GameActionPass), wire.KeyWaitID, wire.Float(3))},
		{"negative wait id", with(gameAction(messaging.GameActionPass), wire.KeyWaitID, wire.Int(-1))},
		{"unknown action", gameAction(99)},
		{"discard without a tile", gameAction(messaging.GameActionDiscard)},
		{"boolean tile", gameAction(messaging.GameActionDiscard, wire.Field{Key: wire.KeyTileID, Value: wire.Bool(true)})},
		{"string tile", gameAction(messaging.GameActionDiscard, wire.Field{Key: wire.KeyTileID, Value: wire.Str("5")})},
		{"float tile", gameAction(messaging.GameActionDiscard, wire.Field{Key: wire.KeyTileID, Value: wire.Float(5)})},
		{"negative tile", gameAction(messaging.GameActionDiscard, tileField(-1))},
		{"tile above 135", gameAction(messaging.GameActionDiscard, tileField(136))},
		{"kan without a kan type", gameAction(messaging.GameActionKan, tileField(8))},
		{"kan of an unknown type", gameAction(messaging.GameActionKan, tileField(8), kanTypeField("closed_kan"))},
		{"pon without held tiles", gameAction(messaging.GameActionPon, tileField(40))},
		{"chi with one held tile", gameAction(messaging.GameActionChi, tileField(40), heldField(wire.Int(44)))},
		{"chi with a boolean held tile", gameAction(messaging.GameActionChi, tileField(40), heldField(wire.Bool(true), wire.Int(42)))},
		{"chi with a held tile out of range", gameAction(messaging.GameActionChi, tileField(0), heldField(wire.Int(4), wire.Int(200)))},
	} {
		t.Run(c.name, func(t *testing.T) {
			got, err := messaging.ParseClientMessage(c.message)
			if !isInvalidMessage(err) {
				t.Errorf("%s: ParseClientMessage = %+v, %v; want an InvalidMessageError", c.name, got, err)
			}
		})
	}
}

func TestParseClientMessage_WhenASessionMessageIsWellFormed_ShouldCarryItsTicket(t *testing.T) {
	longest := strings.Repeat("é", 2000)
	for _, c := range []struct {
		name    string
		message wire.Map
		want    messaging.ClientMessage
	}{
		{"reconnect", ticketMessage(messaging.ClientReconnect, "some-ticket"), messaging.ReconnectMessage{Ticket: "some-ticket"}},
		{"join game", ticketMessage(messaging.ClientJoinGame, longest), messaging.JoinGameMessage{Ticket: longest}},
		{"resync", wire.Map{{Key: wire.KeyEventType, Value: wire.Int(messaging.ClientResync)}}, messaging.ResyncMessage{}},
	} {
		t.Run(c.name, func(t *testing.T) {
			got, err := messaging.ParseClientMessage(c.message)
			if err != nil || got != c.want {
				t.Errorf("ParseClientMessage(%v) = %v, %v; want %v", c.message, got, err, c.want)
			}
		})
	}
}

func TestParseClientMessage_WhenASessionMessageIsMalformedOrUnknown_ShouldRefuseIt(t *testing.T) {
	for _, c := range []struct {
		name    string
		message wire.Map
	}{
		{"no type", wire.Map{{Key: wire.KeyGameTicket, Value: wire.Str("some-ticket")}}},
		{"unknown type", ticketMessage(99, "some-ticket")},
		{"ping", wire.Map{{Key: wire.KeyEventType, Value: wire.Int(messaging.ClientPing)}}},
		{"reconnect without a ticket", wire.Map{{Key: wire.KeyEventType, Value: wire.Int(messaging.ClientReconnect)}}},
		{"join with an empty ticket", ticketMessage(messaging.ClientJoinGame, "")},
		{"join with a ticket over 2000 characters", ticketMessage(messaging.ClientJoinGame, strings.Repeat("a", 2001))},
	} {
		t.Run(c.name, func(t *testing.T) {
			got, err := messaging.ParseClientMessage(c.message)
			if !isInvalidMessage(err) {
				t.Errorf("%s: ParseClientMessage = %v, %v; want an InvalidMessageError", c.name, got, err)
			}
		})
	}
}

func TestRefusedWaitID_ShouldReadOnlyTheWaitIDOfAGameAction(t *testing.T) {
	for _, c := range []struct {
		name    string
		message wire.Map
		want    int
		ok      bool
	}{
		{"game action", gameAction(messaging.GameActionPass), 4, true},
		{"negative wait id", with(gameAction(messaging.GameActionPass), wire.KeyWaitID, wire.Int(-1)), 0, false},
		{"boolean wait id", with(gameAction(messaging.GameActionPass), wire.KeyWaitID, wire.Bool(true)), 0, false},
		{"not a game action", with(gameAction(messaging.GameActionPass), wire.KeyEventType, wire.Int(messaging.ClientResync)), 0, false},
	} {
		t.Run(c.name, func(t *testing.T) {
			got, ok := messaging.RefusedWaitID(c.message)
			if ok != c.ok || (ok && got != c.want) {
				t.Errorf("%s: RefusedWaitID = %d, %v; want %d, %v", c.name, got, ok, c.want, c.ok)
			}
		})
	}
}
