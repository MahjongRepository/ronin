package tenhou

import (
	"errors"
	"os"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func TestEscapeName_WhenANameHoldsMoreThanLettersDigitsAndUnderscores_ShouldPercentEncodeItsOtherBytes(t *testing.T) {
	if got, want := escapeName(`Bob_7 "<&>%`+"姫"), `Bob_7%20%22%3C%26%3E%25%E5%A7%AB`; got != want {
		t.Errorf("escapeName = %q, want %q", got, want)
	}
}

func TestConvertEvents_WhenASeatDiscardsATileItDoesNotHold_ShouldFailAtThatRecord(t *testing.T) {
	content, err := os.ReadFile(rewrittenChankanPath)
	if err != nil {
		t.Fatalf("read %s: %v", rewrittenChankanPath, err)
	}
	records, err := wire.DecodeReplay(content)
	if err != nil {
		t.Fatalf("DecodeReplay error = %v", err)
	}
	const dealersFirstDiscard = 4
	unheld, _ := tile.NewTileID(135)
	records[dealersFirstDiscard] = wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(wire.EventDiscard)},
		{Key: wire.KeyPackedMove, Value: wire.Int(wire.PackDiscard(wire.Move{Seat: seat(t, dealer), Tile: unheld}))},
	}

	_, err = convertEvents(records[1:])
	if recordErr, ok := errors.AsType[RecordError](err); !ok || recordErr.Record != dealersFirstDiscard+1 {
		t.Errorf("convertEvents error = %v, want a RecordError at record %d", err, dealersFirstDiscard+1)
	}
}
