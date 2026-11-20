package wire

import (
	"bytes"
	"errors"
	"reflect"
	"strings"
	"testing"
)

func nested(depth int) Value {
	var v Value = Int(1)
	for range depth {
		v = Array{v}
	}
	return v
}

func TestDecode_WhenEveryKindOfValueIsSent_ShouldReadBackWhatEncodeWrote(t *testing.T) {
	message := Map{
		{Key: KeyEventType, Value: Int(-5)},
		{Key: KeyGameTicket, Value: Str(strings.Repeat("t", 300))},
		{Key: KeyWaitElapsed, Value: Float(1.25)},
		{Key: KeyFuriten, Value: Bool(true)},
		{Key: KeyIsRiichi, Value: Bool(false)},
		{Key: KeyName, Value: Nil{}},
		{Key: KeyTiles, Value: Bin{1, 2, 3}},
		{Key: KeyCallers, Value: Array{Int(1 << 40), Int(-1 << 40), Int(70000), Int(-300)}},
		{Key: KeyScores, Value: StrMap{{Key: "0", Value: Int(250)}, {Key: "3", Value: Int(-10)}}},
		{Key: KeyRoundResult, Value: Map{{Key: KeyScoreChanges, Value: StrMap{}}}},
		{Key: KeyMyTiles, Value: nested(maxNesting - 1)},
	}

	content, err := Encode(message)
	if err != nil {
		t.Fatalf("Encode(%v): %v", message, err)
	}
	decoded, err := Decode(content)
	if err != nil {
		t.Fatalf("Decode(Encode(m)): %v", err)
	}
	if !reflect.DeepEqual(decoded, message) {
		t.Errorf("Decode(Encode(m)) = %v; want %v", decoded, message)
	}
	if n, ok := decoded.Int(KeyEventType); n != -5 || !ok {
		t.Errorf("Int(KeyEventType) = %d, %v; want -5, true", n, ok)
	}
	if _, ok := decoded.Int(KeyWaitElapsed); ok {
		t.Error("Int(KeyWaitElapsed) read a float as an integer")
	}
	if s, ok := decoded.Str(KeyGameTicket); s != strings.Repeat("t", 300) || !ok {
		t.Errorf("Str(KeyGameTicket) = %q, %v; want the ticket, true", s, ok)
	}
	if _, ok := decoded.Str(KeyName); ok {
		t.Error("Str(KeyName) read nil as a string")
	}
}

func TestDecode_WhenAFloatIsSentAsFloat32_ShouldReadItAsAFloat(t *testing.T) {
	decoded, err := Decode(hexBytes(t, "8152ca41a00000"))

	want := Map{{Key: KeyWaitElapsed, Value: Float(20)}}
	if err != nil || !reflect.DeepEqual(decoded, want) {
		t.Errorf("Decode(float32 20) = %v, %v; want %v", decoded, err, want)
	}
}

func TestDecode_WhenTheBytesBreakTheMessageRules_ShouldRefuseWithADecodeError(t *testing.T) {
	tests := []struct {
		name    string
		content []byte
		message string
	}{
		{"no bytes", nil, ""},
		{"reserved type", hexBytes(t, "8101c1"), ""},
		{"extension", hexBytes(t, "8101c70100"), ""},
		{"fixed extension", hexBytes(t, "8101d40100"), ""},
		{"truncated map", hexBytes(t, "8201"), ""},
		{"truncated float32", hexBytes(t, "8152ca41"), ""},
		{"truncated float64", hexBytes(t, "8152cb40"), ""},
		{"truncated uint16", hexBytes(t, "8101cd01"), ""},
		{"truncated int32", hexBytes(t, "8101d20101"), ""},
		{"truncated length", hexBytes(t, "811fd9"), ""},
		{"truncated string", hexBytes(t, "811fa3616263"[:10]), ""},
		{"truncated binary", hexBytes(t, "813cc40301"), ""},
		{"integer above int64", hexBytes(t, "8101cfffffffffffffffff"), ""},
		{"invalid UTF-8", hexBytes(t, "811fa1ff"), ""},
		{"string too long", append(hexBytes(t, "811fdb00010001"), strings.Repeat("a", 65537)...), ""},
		{"binary too long", append(hexBytes(t, "813cc600010001"), make([]byte, 65537)...), ""},
		{"array too long", append(hexBytes(t, "813cdc0401"), make([]byte, 1025)...), ""},
		{"map too long", hexBytes(t, "813cde0101"), "map of 257 exceeds 256"},
		{"array item truncated", hexBytes(t, "813c92cd"), ""},
		{"nesting too deep", appendValue(nil, Map{{Key: KeyMyTiles, Value: nested(maxNesting)}}), ""},
		{"data past the message", hexBytes(t, "81010200"), ""},
		{"not a map", hexBytes(t, "920102"), ""},
		{"boolean key", hexBytes(t, "81c301"), ""},
		{"string key", hexBytes(t, "81a17401"), ""},
		{"key truncated", hexBytes(t, "81cd"), ""},
		{"key past the registry", hexBytes(t, "81ccc801"), ""},
		{"replay-only key", hexBytes(t, "8100a3302e35"), ""},
		{"duplicate key", hexBytes(t, "8201010102"), ""},
		{"integer seat key", hexBytes(t, "813581000001"), ""},
		{"score map key truncated", hexBytes(t, "813581d9"), ""},
		{"score map value truncated", hexBytes(t, "813581a130cd"), ""},
		{"score map value not an integer", hexBytes(t, "813581a130c3"), ""},
		{"score map key not a seat", hexBytes(t, "813581a13401"), ""},
		{"score map key not canonical", hexBytes(t, "813581a2303001"), ""},
		{"score map seat twice", hexBytes(t, "813582a13001a13002"), ""},
		{"score map not a map", hexBytes(t, "813501"), ""},
		{"too large", append(hexBytes(t, "81dd"), make([]byte, MaxMessageBytes)...), ""},
	}
	for _, tc := range tests {
		decoded, err := Decode(tc.content)
		decodeErr, isType := errors.AsType[DecodeError](err)
		if !isType || !strings.Contains(decodeErr.Error(), tc.message) {
			t.Errorf("Decode(%s) = %v, %v; want a DecodeError", tc.name, decoded, err)
		}
	}
}

func TestEncode_WhenTheMessageBreaksTheMessageRules_ShouldRefuseIt(t *testing.T) {
	tests := []struct {
		name    string
		message Map
	}{
		{"replay-only key", Map{{Key: KeySeed, Value: Bin(make([]byte, ReplaySeedBytes))}}},
		{"key past the registry", Map{{Key: Key(keyCount), Value: Int(1)}}},
		{"invalid UTF-8", Map{{Key: KeyName, Value: Str("\xff")}}},
		{"nested invalid UTF-8", Map{{Key: KeyPlayers, Value: Array{Map{{Key: KeyName, Value: Str("\xff")}}}}}},
		{"nesting too deep", Map{{Key: KeyMyTiles, Value: nested(maxNesting)}}},
		{"string-keyed map elsewhere", Map{{Key: KeyRoundResult, Value: StrMap{}}}},
		{"score map not a map", Map{{Key: KeyScores, Value: Map{}}}},
	}
	for _, tc := range tests {
		content, err := Encode(tc.message)
		if err == nil {
			t.Errorf("Encode(%s) = %x, want an error", tc.name, content)
		}
	}
}

func TestDecodeError_ShouldUnwrapToTheCause(t *testing.T) {
	_, err := Decode(nil)

	if !errors.Is(err, errTruncated) {
		t.Errorf("Decode(nil) = %v, want it to wrap the truncation", err)
	}
}

func TestDecode_WhenAStringIsExactlyTheLongestAllowed_ShouldReadIt(t *testing.T) {
	ticket := Str(strings.Repeat("t", 64*1024))
	content := appendValue(nil, Map{{Key: KeyGameTicket, Value: ticket}})

	decoded, err := Decode(content)
	if err != nil || !bytes.Equal(appendValue(nil, decoded), content) {
		t.Errorf("Decode(a 64 KiB ticket) = %v, want it read", err)
	}
}
