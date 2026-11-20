package auth_test

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/auth"
)

const lobbyTicketsPath = "testdata/lobby_tickets.json"

type lobbyTicket struct {
	Name     string `json:"name"`
	Token    string `json:"token"`
	Accepted bool   `json:"accepted"`
	Ticket   struct {
		UserID    string  `json:"user_id"`
		Username  string  `json:"username"`
		RoomID    string  `json:"room_id"`
		ExpiresAt float64 `json:"expires_at"`
	} `json:"ticket"`
}

type lobbyTickets struct {
	Secret  string        `json:"secret"`
	Tickets []lobbyTicket `json:"tickets"`
}

var fixtureNow = time.Date(2026, 11, 20, 0, 0, 0, 0, time.UTC)

func loadLobbyTickets(t *testing.T) lobbyTickets {
	t.Helper()
	content, err := os.ReadFile(lobbyTicketsPath)
	if err != nil {
		t.Fatalf("read %s: %v", lobbyTicketsPath, err)
	}

	var fixtures lobbyTickets
	err = json.Unmarshal(content, &fixtures)
	if err != nil {
		t.Fatalf("decode %s: %v", lobbyTicketsPath, err)
	}
	return fixtures
}

func (f lobbyTicket) want() auth.Ticket {
	return auth.Ticket{
		UserID:    f.Ticket.UserID,
		Username:  f.Ticket.Username,
		RoomID:    f.Ticket.RoomID,
		ExpiresAt: f.Ticket.ExpiresAt,
	}
}

func signedPayload(payload, secret string) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(payload))
	return base64.URLEncoding.EncodeToString([]byte(payload)) + "." +
		base64.URLEncoding.EncodeToString(mac.Sum(nil))
}

func TestVerifyTicket_WhenTheLobbySignedIt_ShouldReachThePythonVerdict(t *testing.T) {
	fixtures := loadLobbyTickets(t)
	rejections := map[string]error{
		"expired":        auth.ErrTicketExpired,
		"integer_expiry": auth.ErrTicketExpiry,
		"nan_expiry":     auth.ErrTicketPayload,
	}
	for _, f := range fixtures.Tickets {
		got, err := auth.VerifyTicket(f.Token, fixtures.Secret, fixtureNow)
		if f.Accepted {
			if err != nil || got != f.want() {
				t.Errorf("%s: VerifyTicket = %+v, %v; want %+v", f.Name, got, err, f.want())
			}
			continue
		}
		if !errors.Is(err, rejections[f.Name]) {
			t.Errorf("%s: VerifyTicket error = %v, want %v", f.Name, err, rejections[f.Name])
		}
	}
}

func TestSignTicket_WhenGivenATicketTheLobbySigned_ShouldProduceTheLobbysToken(t *testing.T) {
	fixtures := loadLobbyTickets(t)
	for _, f := range fixtures.Tickets {
		if !f.Accepted {
			continue
		}
		got := auth.SignTicket(f.want(), fixtures.Secret)
		if got != f.Token {
			t.Errorf("%s: SignTicket = %s, want %s", f.Name, got, f.Token)
		}
	}
}

func TestSignTicket_WhenTheTicketNeedsPythonsRareJSONForms_ShouldWriteThemAsPythonDoes(t *testing.T) {
	for _, c := range []struct {
		ticket  auth.Ticket
		payload string
	}{
		{
			auth.Ticket{ExpiresAt: 1e16, Username: "\n\r\t\b\f\x01"},
			`{"expires_at": 1e+16, "room_id": "", "user_id": "", "username": "\n\r\t\b\f\u0001"}`,
		},
		{auth.Ticket{ExpiresAt: 0.00001}, `{"expires_at": 1e-05, "room_id": "", "user_id": "", "username": ""}`},
		{auth.Ticket{ExpiresAt: 0.0001}, `{"expires_at": 0.0001, "room_id": "", "user_id": "", "username": ""}`},
		{
			auth.Ticket{ExpiresAt: 1234567890123456.0},
			`{"expires_at": 1234567890123456.0, "room_id": "", "user_id": "", "username": ""}`,
		},
	} {
		got := auth.SignTicket(c.ticket, "secret")
		if want := signedPayload(c.payload, "secret"); got != want {
			t.Errorf("SignTicket(%+v) = %s, want the token of %s", c.ticket, got, c.payload)
		}
	}
}

func TestVerifyTicket_WhenTheTokenIsNotWhatTheLobbySigned_ShouldRefuseIt(t *testing.T) {
	fixtures := loadLobbyTickets(t)
	token := fixtures.Tickets[0].Token
	payloadPart, signaturePart, _ := strings.Cut(token, ".")
	otherPayload, _, _ := strings.Cut(fixtures.Tickets[1].Token, ".")
	for _, c := range []struct {
		name   string
		token  string
		secret string
		want   error
	}{
		{"another secret", token, "other-secret", auth.ErrTicketSignature},
		{"another payload", otherPayload + "." + signaturePart, fixtures.Secret, auth.ErrTicketSignature},
		{"unpadded", strings.TrimRight(payloadPart, "=") + "." + signaturePart, fixtures.Secret, auth.ErrTicketEncoding},
		{"standard alphabet", strings.ReplaceAll(token, "_", "/"), fixtures.Secret, auth.ErrTicketEncoding},
		{"three parts", token + ".", fixtures.Secret, auth.ErrTicketEncoding},
		{"one part", payloadPart, fixtures.Secret, auth.ErrTicketEncoding},
		{"no secret configured", token, "", auth.ErrNoSecret},
	} {
		_, err := auth.VerifyTicket(c.token, c.secret, fixtureNow)
		if !errors.Is(err, c.want) {
			t.Errorf("%s: VerifyTicket error = %v, want %v", c.name, err, c.want)
		}
	}
}

func TestVerifyTicket_WhenTheSignedPayloadIsNotATicket_ShouldRefuseIt(t *testing.T) {
	const secret = "secret"
	for _, c := range []struct {
		name    string
		payload string
		want    error
	}{
		{"not json", `{"expires_at": 4102444800.0,`, auth.ErrTicketPayload},
		{"an array", `[4102444800.0, "r", "u", "n"]`, auth.ErrTicketPayload},
		{"a missing field", `{"expires_at": 4102444800.0, "room_id": "r", "user_id": "u"}`, auth.ErrTicketPayload},
		{
			"an extra field",
			`{"expires_at": 4102444800.0, "is_admin": true, "room_id": "r", "user_id": "u", "username": "n"}`,
			auth.ErrTicketPayload,
		},
		{
			"a renamed field",
			`{"expires_at": 4102444800.0, "room": "r", "user_id": "u", "username": "n"}`,
			auth.ErrTicketPayload,
		},
		{
			"a numeric user id",
			`{"expires_at": 4102444800.0, "room_id": "r", "user_id": 7, "username": "n"}`,
			auth.ErrTicketPayload,
		},
		{
			"no expiry field",
			`{"expiry": 4102444800.0, "room_id": "r", "user_id": "u", "username": "n"}`,
			auth.ErrTicketPayload,
		},
		{
			"a string expiry",
			`{"expires_at": "4102444800.0", "room_id": "r", "user_id": "u", "username": "n"}`,
			auth.ErrTicketExpiry,
		},
		{
			"a null expiry",
			`{"expires_at": null, "room_id": "r", "user_id": "u", "username": "n"}`,
			auth.ErrTicketExpiry,
		},
		{
			"an overflowing expiry",
			`{"expires_at": 1e400, "room_id": "r", "user_id": "u", "username": "n"}`,
			auth.ErrTicketExpiry,
		},
	} {
		_, err := auth.VerifyTicket(signedPayload(c.payload, secret), secret, fixtureNow)
		if !errors.Is(err, c.want) {
			t.Errorf("%s: VerifyTicket error = %v, want %v", c.name, err, c.want)
		}
	}
}

func TestVerifyTicket_WhenNowReachesTheExpiry_ShouldAcceptItUntilNowPassesIt(t *testing.T) {
	const secret = "secret"
	expiry := fixtureNow.Add(24 * time.Hour)
	ticket := auth.Ticket{
		UserID:    "u",
		Username:  "n",
		RoomID:    "r",
		ExpiresAt: float64(expiry.Unix()) + 0.5,
	}
	token := auth.SignTicket(ticket, secret)

	atExpiry := expiry.Add(500 * time.Millisecond)
	got, err := auth.VerifyTicket(token, secret, atExpiry)
	if err != nil || got != ticket {
		t.Errorf("VerifyTicket at the expiry = %+v, %v; want %+v", got, err, ticket)
	}

	_, err = auth.VerifyTicket(token, secret, atExpiry.Add(time.Millisecond))
	if !errors.Is(err, auth.ErrTicketExpired) {
		t.Errorf("VerifyTicket past the expiry error = %v, want %v", err, auth.ErrTicketExpired)
	}
}
