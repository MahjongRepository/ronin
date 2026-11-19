package wire

import (
	"bytes"
	"encoding/hex"
	"math"
	"strings"
	"testing"
)

func hexBytes(t *testing.T, text string) []byte {
	t.Helper()
	content, err := hex.DecodeString(text)
	if err != nil {
		t.Fatalf("hex %q: %v", text, err)
	}
	return content
}

func TestAppendValue_ShouldEncodeEachIntegerInTheFewestBytes(t *testing.T) {
	tests := []struct {
		n    int64
		want string
	}{
		{0, "00"},
		{127, "7f"},
		{128, "cc80"},
		{255, "ccff"},
		{256, "cd0100"},
		{65535, "cdffff"},
		{65536, "ce00010000"},
		{math.MaxUint32, "ceffffffff"},
		{math.MaxUint32 + 1, "cf0000000100000000"},
		{-1, "ff"},
		{-32, "e0"},
		{-33, "d0df"},
		{-128, "d080"},
		{-129, "d1ff7f"},
		{-32768, "d18000"},
		{-32769, "d2ffff7fff"},
		{math.MinInt32, "d280000000"},
		{math.MinInt32 - 1, "d3ffffffff7fffffff"},
	}
	for _, tc := range tests {
		got := appendValue(nil, Int(tc.n))
		if want := hexBytes(t, tc.want); !bytes.Equal(got, want) {
			t.Errorf("appendValue(Int(%d)) = %x, want %x", tc.n, got, want)
		}
	}
}

func TestAppendValue_WhenAnIntAndAFloatHoldOneNumber_ShouldEncodeTheIntAsAnIntegerAndTheFloatAsFloat64(t *testing.T) {
	message := Map{{Key: KeyBankSeconds, Value: Int(20)}, {Key: KeyTimerSettings, Value: Map{{Key: KeyBankSeconds, Value: Float(20)}}}}

	got := appendValue(nil, message)

	if want := hexBytes(t, "824c146b814ccb4034000000000000"); !bytes.Equal(got, want) {
		t.Errorf("appendValue(%v) = %x, want %x", message, got, want)
	}
}

func TestAppendValue_ShouldEncodeEachLengthInTheFewestBytes(t *testing.T) {
	tests := []struct {
		name  string
		value Value
		want  string
	}{
		{"nil", Nil{}, "c0"},
		{"false", Bool(false), "c2"},
		{"true", Bool(true), "c3"},
		{"str of 31", Str(strings.Repeat("a", 31)), "bf"},
		{"str of 32", Str(strings.Repeat("a", 32)), "d920"},
		{"str of 255", Str(strings.Repeat("a", 255)), "d9ff"},
		{"str of 256", Str(strings.Repeat("a", 256)), "da0100"},
		{"str of 65536", Str(strings.Repeat("a", 65536)), "db00010000"},
		{"bin of 1", Bin{7}, "c40107"},
		{"bin of 256", Bin(make([]byte, 256)), "c50100"},
		{"bin of 65536", Bin(make([]byte, 65536)), "c600010000"},
		{"array of 15", make(Array, 15), "9f"},
		{"array of 16", make(Array, 16), "dc0010"},
		{"array of 65536", make(Array, 65536), "dd00010000"},
		{"map of 15", make(Map, 15), "8f"},
		{"map of 16", make(Map, 16), "de0010"},
		{"map of 65536", make(Map, 65536), "df00010000"},
		{"string map", StrMap{{Key: "0", Value: Int(250)}}, "81a130ccfa"},
	}
	for _, tc := range tests {
		got := appendValue(nil, tc.value)
		if want := hexBytes(t, tc.want); !bytes.HasPrefix(got, want) {
			t.Errorf("appendValue(%s) = %x..., want a prefix of %x", tc.name, got[:min(len(got), 8)], want)
		}
	}
}
