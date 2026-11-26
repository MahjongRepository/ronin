package pyjson

import (
	"strconv"
	"strings"
	"unicode/utf16"
)

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
