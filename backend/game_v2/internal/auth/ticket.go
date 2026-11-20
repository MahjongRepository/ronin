// Package auth holds the game server's two credentials: the HMAC-signed game ticket the lobby
// hands a player, and the internal bearer secret the lobby presents on its credential-bearing
// calls.
//
// A ticket is base64url(payload) "." base64url(signature), both padded. The payload is the JSON the
// lobby writes, keys sorted, `expires_at` a JSON float of epoch seconds; the signature is
// HMAC-SHA256 of the payload bytes under the shared ticket secret. Decoding takes padded base64url
// only: the padding is required and the alphabet is the URL one, as the lobby writes it, where
// Python also took the standard alphabet and skipped other characters; line breaks are skipped,
// as in Python. The game keys a participant by the exact ticket string anyway.
//
// Ported from ronin's Python shared auth: its game ticket module and the game server's internal
// caller check.
package auth

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"strconv"
	"strings"
	"time"
	"unicode/utf16"
)

// Ticket is the payload a signed game ticket carries.
type Ticket struct {
	UserID    string
	Username  string
	RoomID    string
	ExpiresAt float64
}

// The reasons VerifyTicket refuses a ticket.
var (
	ErrNoSecret        = errors.New("no ticket secret configured")
	ErrTicketEncoding  = errors.New("game ticket is not two base64url parts")
	ErrTicketSignature = errors.New("game ticket signature mismatch")
	ErrTicketPayload   = errors.New("game ticket malformed payload")
	ErrTicketExpiry    = errors.New("game ticket invalid expires_at")
	ErrTicketExpired   = errors.New("game ticket expired")
)

const ticketParts = 2

var ticketKeys = [...]string{"expires_at", "room_id", "user_id", "username"}

// SignTicket returns the signed token for a ticket with a finite ExpiresAt, byte for byte the one
// the lobby signs for it.
func SignTicket(t Ticket, secret string) string {
	payload := ticketPayload(t)
	return base64.URLEncoding.EncodeToString(payload) + "." +
		base64.URLEncoding.EncodeToString(signature(payload, secret))
}

// VerifyTicket checks a token's signature under secret and its expiry against now, and returns the
// ticket it carries. The payload must hold exactly the four ticket fields, the three ids as strings
// and `expires_at` as a finite JSON float; an integer is refused, as the lobby never writes one.
func VerifyTicket(token, secret string, now time.Time) (Ticket, error) {
	if secret == "" {
		return Ticket{}, ErrNoSecret
	}

	parts := strings.Split(token, ".")
	if len(parts) != ticketParts {
		return Ticket{}, ErrTicketEncoding
	}

	payload, payloadErr := base64.URLEncoding.DecodeString(parts[0])
	provided, sigErr := base64.URLEncoding.DecodeString(parts[1])
	if payloadErr != nil || sigErr != nil {
		return Ticket{}, ErrTicketEncoding
	}

	if !hmac.Equal(provided, signature(payload, secret)) {
		return Ticket{}, ErrTicketSignature
	}

	ticket, err := parseTicketPayload(payload)
	if err != nil {
		return Ticket{}, err
	}

	if unixSeconds(now) > ticket.ExpiresAt {
		return Ticket{}, ErrTicketExpired
	}

	return ticket, nil
}

func signature(payload []byte, secret string) []byte {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(payload)
	return mac.Sum(nil)
}

func unixSeconds(t time.Time) float64 {
	return float64(t.UnixNano()) / float64(time.Second)
}

func parseTicketPayload(payload []byte) (Ticket, error) {
	var fields map[string]json.RawMessage
	if json.Unmarshal(payload, &fields) != nil || len(fields) != len(ticketKeys) {
		return Ticket{}, ErrTicketPayload
	}

	var t Ticket
	for _, target := range []struct {
		key  string
		into *string
	}{{"user_id", &t.UserID}, {"username", &t.Username}, {"room_id", &t.RoomID}} {
		raw, ok := fields[target.key]
		if !ok || !bytes.HasPrefix(raw, []byte(`"`)) || json.Unmarshal(raw, target.into) != nil {
			return Ticket{}, ErrTicketPayload
		}
	}

	raw, ok := fields["expires_at"]
	if !ok {
		return Ticket{}, ErrTicketPayload
	}

	expiresAt, err := parseJSONFloat(raw)
	if err != nil {
		return Ticket{}, err
	}

	t.ExpiresAt = expiresAt
	return t, nil
}

func parseJSONFloat(raw json.RawMessage) (float64, error) {
	isNumber := len(raw) > 0 && (raw[0] == '-' || ('0' <= raw[0] && raw[0] <= '9'))
	if !isNumber || !bytes.ContainsAny(raw, ".eE") {
		return 0, ErrTicketExpiry
	}

	f, err := strconv.ParseFloat(string(raw), 64)
	if err != nil {
		return 0, ErrTicketExpiry
	}

	return f, nil
}

func ticketPayload(t Ticket) []byte {
	values := [...]string{
		pythonFloat(t.ExpiresAt),
		pythonString(t.RoomID),
		pythonString(t.UserID),
		pythonString(t.Username),
	}

	var b strings.Builder
	b.WriteByte('{')
	for i, key := range ticketKeys {
		if i > 0 {
			b.WriteString(", ")
		}
		b.WriteString(pythonString(key))
		b.WriteString(": ")
		b.WriteString(values[i])
	}
	b.WriteByte('}')
	return []byte(b.String())
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
