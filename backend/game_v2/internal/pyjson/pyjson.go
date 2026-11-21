// Package pyjson writes JSON strings and numbers as Python's json.dumps does with its defaults:
// every character outside printable ASCII escaped as \uXXXX, astral ones as a surrogate pair, and a
// float in Python's repr. Callers lay out the objects and decide what a non-finite float becomes.
package pyjson

import (
	"strconv"
	"strings"
	"unicode/utf16"
)

// Float returns a finite float as Python's json.dumps writes it: the shortest repr that reads back
// to the same value, in exponent form for a magnitude below 1e-4 or from 1e16, else fixed with at least one
// decimal. A NaN or an infinity has no JSON form, and its result is not JSON.
func Float(f float64) string {
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

// Quote returns s as a JSON string literal as Python's json.dumps writes it with ensure_ascii.
func Quote(s string) string {
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
