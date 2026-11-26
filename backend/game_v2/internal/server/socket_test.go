package server_test

import (
	"bytes"
	"context"
	"errors"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/coder/websocket"
	"github.com/google/go-cmp/cmp"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/server"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

var undecodable = []byte{0xff, 0xff, 0xff}

func TestSocket_WhenGameIDInvalid_ShouldRefuseTheHandshake(t *testing.T) {
	h := newHarness(t)

	got := h.get("/ws/bad%20id!")
	if got.status != http.StatusForbidden {
		t.Errorf("GET /ws/bad id! status = %d, want 403 before any upgrade", got.status)
	}
}

func TestSocket_WhenAForeignOriginDials_ShouldUpgrade(t *testing.T) {
	h := newHarness(t)
	ws := h.dial(testGameID, http.Header{"Origin": {"http://phone.local:5175"}})

	send(t, ws, typed(messaging.ClientPing))
	if got := readMessage(t, ws); sessionType(got) != "pong" {
		t.Errorf("answer to a ping = %v, want pong", got)
	}
}

func TestSocket_WhenThePlayerJoins_ShouldAnswerTheJoinAndStartTheGame(t *testing.T) {
	h := newHarness(t)
	h.create("alice")

	ws := h.joinAlice()

	readUntil(t, ws, isGameStarted)
	if active := counter(t, h.status(), "active_games"); active != 1 {
		t.Errorf("/status active_games = %d, want 1", active)
	}
}

func TestSocket_WhenJoinTicketInvalid_ShouldAnswerInvalidTicket(t *testing.T) {
	h := newHarness(t)
	h.create("alice")
	ws := h.dial(testGameID, nil)

	send(t, ws, joinMessage("not-a-valid-ticket"))
	if got := readMessage(t, ws); errorCode(got) != string(messaging.SessionInvalidTicket) {
		t.Errorf("answer to a forged ticket = %v, want invalid_ticket", got)
	}
}

func TestSocket_WhenTicketNamesAnotherGame_ShouldAnswerInvalidTicket(t *testing.T) {
	h := newHarness(t)
	h.create("alice")
	ws := h.dial("game-0002", nil)

	send(t, ws, joinMessage(ticketFor(testGameID, "alice")))
	if got := readMessage(t, ws); errorCode(got) != string(messaging.SessionInvalidTicket) {
		t.Errorf("answer to another game's ticket = %v, want invalid_ticket", got)
	}
}

func TestSocket_WhenPingSent_ShouldPongWithoutRouting(t *testing.T) {
	h := newHarness(t)
	ws := h.dial(testGameID, nil)

	send(t, ws, typed(messaging.ClientPing))
	if got := readMessage(t, ws); !cmp.Equal(got, messaging.Pong()) {
		t.Errorf("answer to a ping = %v, want %v", got, messaging.Pong())
	}

	status := h.status()
	if got := []int{counter(t, status, "messages_in"), counter(t, status, "handled_messages")}; !cmp.Equal(got, []int{1, 0}) {
		t.Errorf("/status messages_in, handled_messages = %v, want [1 0]", got)
	}
}

func TestSocket_WhenMessageInvalid_ShouldAnswerInvalidMessageWithoutItsInput(t *testing.T) {
	h := newHarness(t)
	ws := h.dial(testGameID, nil)

	send(t, ws, passOutsideAGame(wire.Str("secret-input")))
	want := messaging.SessionError(messaging.SessionInvalidMessage, "Invalid message", noWaitID())
	if got := readMessage(t, ws); !cmp.Equal(got, want) {
		t.Errorf("answer to an invalid message = %v, want %v", got, want)
	}
	if strings.Contains(h.logs.String(), "secret-input") {
		t.Error("the server logged the invalid message's input")
	}
	if malformed := counter(t, h.status(), "malformed_messages"); malformed != 1 {
		t.Errorf("/status malformed_messages = %d, want 1", malformed)
	}
}

func TestSocket_WhenFramesUndecodable_ShouldAnswerInvalidMessageAndKeepTheConnection(t *testing.T) {
	h := newHarness(t)
	h.create("alice")
	ws := h.dial(testGameID, nil)

	sendRaw(t, ws, undecodable)
	binary := readMessage(t, ws)
	err := ws.Write(t.Context(), websocket.MessageText, []byte("not a binary frame"))
	if err != nil {
		t.Fatalf("write text frame: %v", err)
	}

	text := readMessage(t, ws)
	send(t, ws, joinMessage(ticketFor(testGameID, "alice")))

	if errorCode(binary) != "invalid_message" || errorCode(text) != "invalid_message" {
		t.Errorf("answers to undecodable frames = %v, %v, want invalid_message", binary, text)
	}
	if joined := readMessage(t, ws); sessionType(joined) != "game_joined" {
		t.Errorf("answer to the join after them = %v, want game_joined", joined)
	}
	if malformed := counter(t, h.status(), "malformed_messages"); malformed != 2 {
		t.Errorf("/status malformed_messages = %d, want 2", malformed)
	}
}

func TestSocket_WhenDecodeErrorsHitTheLimit_ShouldCloseWith4004(t *testing.T) {
	h := newHarness(t, withSocket(func(c *server.SocketConfig) { c.MaxDecodeErrors = 3 }))
	ws := h.dial(testGameID, nil)

	for range 3 {
		sendRaw(t, ws, undecodable)
	}

	closed := readClose(t, ws)
	if closed.Code != 4004 || closed.Reason != "too_many_decode_errors" {
		t.Errorf("close = %d %q, want 4004 too_many_decode_errors", closed.Code, closed.Reason)
	}

	eventually(t, func() bool { return counter(t, h.status(), "closes_4004") == 1 })
}

func TestSocket_WhenAValidMessageFollowsDecodeErrors_ShouldResetTheStrikes(t *testing.T) {
	h := newHarness(t, withSocket(func(c *server.SocketConfig) { c.MaxDecodeErrors = 3 }))
	ws := h.dial(testGameID, nil)

	for _, frame := range [][]byte{undecodable, undecodable, nil, undecodable, undecodable} {
		if frame == nil {
			send(t, ws, passOutsideAGame(wire.Int(0)))
		} else {
			sendRaw(t, ws, frame)
		}
		readMessage(t, ws)
	}

	send(t, ws, typed(messaging.ClientPing))

	if got := readMessage(t, ws); sessionType(got) != "pong" {
		t.Errorf("answer after four strikes split by a valid message = %v, want pong", got)
	}
}

func TestSocket_WhenTheBurstIsSpent_ShouldAnswerRateLimitedNamingTheWaitID(t *testing.T) {
	h := newHarness(t, withSocket(func(c *server.SocketConfig) { c.Rate, c.Burst = 0, 2 }))
	ws := h.dial(testGameID, nil)
	sendRaw(t, ws, undecodable)
	readMessage(t, ws)
	send(t, ws, passOutsideAGame(wire.Int(0)))
	readMessage(t, ws)

	send(t, ws, passOutsideAGame(wire.Int(7)))
	named := readMessage(t, ws)
	send(t, ws, passOutsideAGame(wire.Str("7")))
	unnamed := readMessage(t, ws)

	wantNamed := messaging.SessionError(messaging.SessionRateLimited, "Too many messages", some(7))
	wantUnnamed := messaging.SessionError(messaging.SessionRateLimited, "Too many messages", noWaitID())
	if !cmp.Equal(named, wantNamed) || !cmp.Equal(unnamed, wantUnnamed) {
		t.Errorf("rate-limited answers = %v, %v, want %v, %v", named, unnamed, wantNamed, wantUnnamed)
	}
	if limited := counter(t, h.status(), "rate_limited_messages"); limited != 2 {
		t.Errorf("/status rate_limited_messages = %d, want 2", limited)
	}
}

func TestSocket_WhenUndecodableFramesArriveOverBudget_ShouldDropTheirRepliesAndClose(t *testing.T) {
	h := newHarness(t, withSocket(func(c *server.SocketConfig) { c.Rate, c.Burst, c.MaxDecodeErrors = 0, 2, 4 }))
	ws := h.dial(testGameID, nil)
	for range 2 {
		send(t, ws, passOutsideAGame(wire.Int(0)))
		readMessage(t, ws)
	}

	for range 4 {
		sendRaw(t, ws, undecodable)
	}

	if closed := readClose(t, ws); closed.Code != 4004 {
		t.Errorf("the first frame after the budget = close %d, want no reply and 4004", closed.Code)
	}

	status := h.status()
	if got := []int{counter(t, status, "malformed_messages"), counter(t, status, "rate_limited_messages")}; !cmp.Equal(got, []int{4, 4}) {
		t.Errorf("/status malformed, rate_limited = %v, want [4 4]", got)
	}
}

func TestSocket_WhenTheResyncBudgetIsSpent_ShouldAnswerRateLimited(t *testing.T) {
	h := newHarness(t, withSocket(func(c *server.SocketConfig) { c.ResyncRate, c.ResyncBurst = 0, 1 }))
	ws := h.dial(testGameID, nil)
	send(t, ws, typed(messaging.ClientResync))
	first := readMessage(t, ws)

	send(t, ws, typed(messaging.ClientResync))
	want := messaging.SessionError(messaging.SessionRateLimited, "Too many resync requests", noWaitID())
	if errorCode(first) != string(messaging.SessionNotInGame) {
		t.Errorf("answer to the first resync = %v, want not_in_game from the session", first)
	}
	if got := readMessage(t, ws); !cmp.Equal(got, want) {
		t.Errorf("answer to the second resync = %v, want %v", got, want)
	}
}

func TestSocket_WhenAFrameIsOversized_ShouldCloseWith1009(t *testing.T) {
	h := newHarness(t)
	ws := h.dial(testGameID, nil)

	sendRaw(t, ws, bytes.Repeat([]byte{0}, wire.MaxMessageBytes+1))
	if closed := readClose(t, ws); closed.Code != websocket.StatusMessageTooBig {
		t.Errorf("close = %d, want %d", closed.Code, websocket.StatusMessageTooBig)
	}
}

func TestSocket_WhenTheParticipantReconnects_ShouldCloseTheOldSocketWith4002(t *testing.T) {
	h := newHarness(t)
	h.create("alice")
	old := h.joinAlice()
	readUntil(t, old, isGameStarted)
	fresh := h.dial(testGameID, nil)

	send(t, fresh, reconnectMessage(ticketFor(testGameID, "alice")))

	readUntil(t, fresh, func(m wire.Map) bool { return sessionType(m) == "game_reconnected" })
	if closed := readClose(t, old); closed.Code != 4002 {
		t.Errorf("old socket close = %d, want 4002", closed.Code)
	}
}

func TestSocket_WhenThePeerStopsAnsweringPings_ShouldDropItAsADisconnect(t *testing.T) {
	h := newHarness(t, withSocket(func(c *server.SocketConfig) { c.PingInterval, c.PingTimeout = 20*time.Millisecond, 20*time.Millisecond }))
	h.create("alice")
	h.joinAlice()

	eventually(t, func() bool {
		return h.get("/players/user-alice").status == http.StatusNotFound && counter(t, h.status(), "connections") == 0
	})
}

func TestSocket_WhenTheRequestContextEndsOnAnIdleSocket_ShouldDropItWithoutAClose(t *testing.T) {
	h := newHarness(t)
	requests, endRequests := context.WithCancel(context.Background())
	defer endRequests()
	idle := httptest.NewUnstartedServer(h.srv.Handler())
	idle.Config.BaseContext = func(net.Listener) context.Context { return requests }
	idle.Start()
	defer idle.Close()
	ws, _, err := websocket.Dial(t.Context(), "ws"+strings.TrimPrefix(idle.URL, "http")+"/ws/"+testGameID, &websocket.DialOptions{ //nolint:bodyclose // websocket.Dial closes the response body itself
		HTTPClient: idle.Client(),
	})
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer func() { _ = ws.CloseNow() }()
	send(t, ws, typed(messaging.ClientPing))
	readMessage(t, ws)

	endRequests()

	_, err = read(t, ws)
	if err == nil || errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("read after the request context ended = %v, want the socket dropped", err)
	}
	if code := websocket.CloseStatus(err); code != -1 {
		t.Errorf("close = %d, want the socket dropped without a close frame", code)
	}
}
