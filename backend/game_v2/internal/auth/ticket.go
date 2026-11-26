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

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/pyjson"
)

// Ticket is the payload a signed game ticket carries.
type Ticket struct {
	UserID    string
	Username  string
	RoomID    string
	ExpiresAt float64
}

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
		pyjson.Float(t.ExpiresAt),
		pyjson.Quote(t.RoomID),
		pyjson.Quote(t.UserID),
		pyjson.Quote(t.Username),
	}

	var b strings.Builder
	b.WriteByte('{')
	for i, key := range ticketKeys {
		if i > 0 {
			b.WriteString(", ")
		}
		b.WriteString(pyjson.Quote(key))
		b.WriteString(": ")
		b.WriteString(values[i])
	}
	b.WriteByte('}')
	return []byte(b.String())
}
