package messaging_test

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func FuzzParseClientMessage_WhenGivenAnyDecodedMessage_ShouldParseOrRefuseIt(f *testing.F) {
	for _, m := range []wire.Map{
		gameAction(messaging.GameActionChi, tileField(8), heldField(wire.Int(4), wire.Int(12))),
		gameAction(messaging.GameActionKan, tileField(0), kanTypeField("added")),
		ticketMessage(messaging.ClientJoinGame, "some-ticket"),
	} {
		content, err := wire.Encode(m)
		if err != nil {
			f.Fatalf("Encode(%v): %v", m, err)
		}

		f.Add(content)
	}

	f.Fuzz(func(t *testing.T, data []byte) {
		m, err := wire.Decode(data)
		if err != nil {
			return
		}

		message, err := messaging.ParseClientMessage(m)
		if (err == nil && message == nil) || (err != nil && !isInvalidMessage(err)) {
			t.Fatalf("ParseClientMessage(%v) = %v, %v; want a message or an InvalidMessageError", m, message, err)
		}
	})
}
