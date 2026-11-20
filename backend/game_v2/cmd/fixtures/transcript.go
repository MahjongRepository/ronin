package main

import (
	"cmp"
	"errors"
	"math"
	"slices"
	"strconv"
	"strings"
	"time"
	"unicode/utf16"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	kindOpened   = "opened"
	kindReceived = "received"
	kindSent     = "sent"
	kindClosed   = "closed"
)

var errNotJSON = errors.New("a transcript value has no JSON form")

type transcriptEvent struct {
	at     time.Duration
	kind   string
	fields wire.StrMap
	label  string
}

func (e transcriptEvent) object() wire.StrMap {
	object := wire.StrMap{
		{Key: "at", Value: wire.Int((e.at + time.Millisecond/2) / time.Millisecond)},
		{Key: "kind", Value: wire.Str(e.kind)},
	}
	object = append(object, e.fields...)
	if e.label != "" {
		object = append(object, wire.StrField{Key: "label", Value: wire.Str(e.label)})
	}
	return object
}

type transcript struct {
	scenario string
	gameID   string
	seat     int
	events   []transcriptEvent
}

func (t transcript) fileName() string {
	return t.scenario + "_seat_" + strconv.Itoa(t.seat) + ".json"
}

func (t transcript) text() (string, error) {
	var b strings.Builder
	b.WriteString("{\n")
	b.WriteString(`  "game_id": ` + pythonString(t.gameID) + ",\n")
	b.WriteString(`  "scenario": ` + pythonString(t.scenario) + ",\n")
	b.WriteString(`  "seat": ` + strconv.Itoa(t.seat) + ",\n")
	b.WriteString(`  "events": [` + "\n")
	for i, e := range t.events {
		if i > 0 {
			b.WriteString(",\n")
		}
		b.WriteString("    ")
		err := writeJSON(&b, e.object())
		if err != nil {
			return "", err
		}
	}
	b.WriteString("\n  ]\n}\n")
	return b.String(), nil
}

func writeJSON(b *strings.Builder, v wire.Value) error {
	switch x := v.(type) {
	case wire.Nil:
		b.WriteString("null")
	case wire.Bool:
		b.WriteString(strconv.FormatBool(bool(x)))
	case wire.Int:
		b.WriteString(strconv.FormatInt(int64(x), 10))
	case wire.Float:
		if math.IsNaN(float64(x)) || math.IsInf(float64(x), 0) {
			return errNotJSON
		}
		b.WriteString(pythonFloat(float64(x)))
	case wire.Str:
		b.WriteString(pythonString(string(x)))
	case wire.Bin:
		return errNotJSON
	case wire.Array:
		return writeArray(b, x)
	case wire.Map:
		return writeMap(b, x)
	case wire.StrMap:
		return writeStrMap(b, x)
	}
	return nil
}

func writeArray(b *strings.Builder, items wire.Array) error {
	b.WriteByte('[')
	for i, item := range items {
		if i > 0 {
			b.WriteString(", ")
		}
		err := writeJSON(b, item)
		if err != nil {
			return err
		}
	}
	b.WriteByte(']')
	return nil
}

func writeMap(b *strings.Builder, m wire.Map) error {
	fields := slices.SortedFunc(slices.Values(m), func(x, y wire.Field) int { return cmp.Compare(x.Key, y.Key) })
	object := make(wire.StrMap, 0, len(fields))
	for _, f := range fields {
		object = append(object, wire.StrField{Key: strconv.Itoa(int(f.Key)), Value: f.Value})
	}
	return writeObject(b, object)
}

func writeStrMap(b *strings.Builder, m wire.StrMap) error {
	return writeObject(b, slices.SortedFunc(slices.Values(m), func(x, y wire.StrField) int {
		return strings.Compare(x.Key, y.Key)
	}))
}

func writeObject(b *strings.Builder, sorted wire.StrMap) error {
	b.WriteByte('{')
	for i, f := range sorted {
		if i > 0 {
			b.WriteString(", ")
		}
		b.WriteString(pythonString(f.Key) + ": ")
		err := writeJSON(b, f.Value)
		if err != nil {
			return err
		}
	}
	b.WriteByte('}')
	return nil
}

func pythonFloat(f float64) string {
	scientific := strconv.FormatFloat(f, 'e', -1, 64)
	_, exponent, _ := strings.Cut(scientific, "e")
	if e, err := strconv.Atoi(exponent); err == nil && (e < -4 || e >= 16) {
		return scientific
	}

	fixed := strconv.FormatFloat(f, 'f', -1, 64)
	if !strings.Contains(fixed, ".") {
		fixed += ".0"
	}
	return fixed
}

func pythonString(s string) string {
	var b strings.Builder
	b.WriteByte('"')
	for _, r := range s {
		switch {
		case r == '"':
			b.WriteString(`\"`)
		case r == '\\':
			b.WriteString(`\\`)
		case r == '\n':
			b.WriteString(`\n`)
		case r == '\r':
			b.WriteString(`\r`)
		case r == '\t':
			b.WriteString(`\t`)
		case r == '\b':
			b.WriteString(`\b`)
		case r == '\f':
			b.WriteString(`\f`)
		case r >= ' ' && r <= '~':
			b.WriteRune(r)
		case r > 0xffff:
			high, low := utf16.EncodeRune(r)
			writeUnicodeEscape(&b, high)
			writeUnicodeEscape(&b, low)
		default:
			writeUnicodeEscape(&b, r)
		}
	}
	b.WriteByte('"')
	return b.String()
}

func writeUnicodeEscape(b *strings.Builder, r rune) {
	hex := strconv.FormatInt(int64(r), 16)
	b.WriteString(`\u`)
	b.WriteString(strings.Repeat("0", 4-len(hex)))
	b.WriteString(hex)
}
