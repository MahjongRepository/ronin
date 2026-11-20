package session_test

import (
	"context"
	"errors"
	"io/fs"
	"slices"
	"strings"
	"sync/atomic"
	"testing"
	"testing/synctest"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func noWaits(timing *session.Timing) {
	timing.GameStartConfirm = 0
	timing.AITurnDelay = 0
}

func soloDealer(t *testing.T, options ...option) (*harness, *fakeConn) {
	t.Helper()
	seed := seedSeating(t, 0)
	h := newHarness(t, append([]option{withSeed(seed), withWalls(shuffledWall(seed, 0), shuffledWall(seed, 1))},
		options...)...)
	return h, h.start("Alice")[0]
}

func lastDraw(t *testing.T, conn *fakeConn) wire.Map {
	t.Helper()
	draws := ofEvent(conn.messages(), wire.EventDraw)
	if len(draws) == 0 {
		t.Fatalf("%s got no draw", conn.id)
	}
	return draws[len(draws)-1]
}

func lastOpening(t *testing.T, conn *fakeConn) wire.Map {
	t.Helper()
	for _, m := range slices.Backward(conn.messages()) {
		if _, ok := m.Get(wire.KeyBankSeconds); ok && sessionType(m) == "" {
			return m
		}
	}
	t.Fatalf("%s got no opening", conn.id)
	return nil
}

func defaultAnswer(t *testing.T, opening wire.Map) messaging.GameActionMessage {
	t.Helper()
	waitID := intOf(t, opening, wire.KeyWaitID)
	if typ, _ := eventType(opening); typ == wire.EventCallPrompt {
		return answer(waitID, play.PassAction())
	}
	return discard(waitID, drawnTile(t, opening))
}

func TestTurnTimeout_WhenBaseAndBankRunOut_ShouldDiscardTheDrawnTileAndEmptyTheBank(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, alice := soloDealer(t, withTiming(noWaits))
		drawn := drawnTile(t, lastDraw(t, alice))

		sleep(30*time.Second - time.Millisecond)
		if got := len(ofEvent(alice.messages(), wire.EventDiscard)); got != 0 {
			t.Fatalf("the seat timed out before its base and bank ran out")
		}
		sleep(time.Millisecond)

		discards := ofEvent(alice.messages(), wire.EventDiscard)
		if len(discards) == 0 {
			t.Fatal("the timeout discarded nothing")
		}
		move, err := wire.UnpackDiscard(intOf(t, discards[0], wire.KeyPackedMove))
		if err != nil || move.Tile != drawn || !move.Tsumogiri {
			t.Errorf("timeout discard = %+v (%v), want tsumogiri of %d", move, err, drawn.Index())
		}
		if got, _ := lastOpening(t, alice).Get(wire.KeyBankSeconds); got != wire.Int(0) {
			t.Errorf("next opening bank = %v, want whole 0", got)
		}
		if got := h.m.Stats().TurnTimeouts; got != 1 {
			t.Errorf("TurnTimeouts = %d, want 1", got)
		}
		h.assertSeatLogged(t, "turn timeout, auto-discarding")
	})
}

func TestBank_WhenTheSeatActsPastItsBaseTime_ShouldKeepWhatIsLeftWholeOrFractional(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, alice := soloDealer(t, withTiming(noWaits))

		for _, tc := range []struct {
			after time.Duration
			want  wire.Value
		}{
			{15 * time.Second, wire.Int(15)},
			{12500 * time.Millisecond, wire.Float(12.5)},
		} {
			opening := lastOpening(t, alice)
			sleep(tc.after)
			h.act(alice, defaultAnswer(t, opening))

			if got, _ := lastOpening(t, alice).Get(wire.KeyBankSeconds); got != tc.want {
				t.Errorf("bank after acting at %v = %v, want %v", tc.after, got, tc.want)
			}
		}
	})
}

func TestBank_WhenTheNextHandIsDealt_ShouldResetToFull(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		_, alice := soloDealer(t, withTiming(noWaits))

		sleep(time.Hour)

		messages := alice.messages()
		deals := 0
		for _, m := range messages {
			typ, _ := eventType(m)
			if typ == wire.EventRoundStarted {
				deals++
			}
			if typ == wire.EventDraw && deals == 2 {
				if got, _ := m.Get(wire.KeyBankSeconds); got != wire.Int(20) {
					t.Errorf("first draw of the second hand bank = %v, want whole 20", got)
				}
				return
			}
		}
		t.Fatalf("no draw in a second hand (%d deals)", deals)
	})
}

func TestAITurns_WhenAIPlayersFollowAHuman_ShouldPlayOneTurnPerDelay(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, alice := soloDealer(t, withTiming(func(timing *session.Timing) { timing.GameStartConfirm = 0 }))
		draw := lastDraw(t, alice)
		h.act(alice, discard(intOf(t, draw, wire.KeyWaitID), drawnTile(t, draw)))

		for want := 1; want <= 3; want++ {
			if got := len(ofEvent(alice.messages(), wire.EventDiscard)); got != want {
				t.Fatalf("discards before AI turn %d = %d, want %d", want, got, want)
			}
			sleep(time.Second)
		}
		if got := len(ofEvent(alice.messages(), wire.EventDiscard)); got != 4 {
			t.Errorf("discards after three AI turns = %d, want 4", got)
		}
		if got := intOf(t, lastOpening(t, alice), wire.KeyWaitID); got != 2 {
			t.Errorf("alice's latest wait id = %d, want her second decision's", got)
		}
	})
}

func TestGameAction_WhenItEchoesAnOldWaitID_ShouldAnswerStaleActionAndChangeNothing(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, alice := soloDealer(t, withTiming(noWaits))
		draw := lastDraw(t, alice)
		waitID := intOf(t, draw, wire.KeyWaitID)

		h.act(alice, discard(waitID-1, drawnTile(t, draw)))

		errs := ofEvent(alice.messages(), wire.EventError)
		if len(errs) != 1 || intOf(t, errs[0], wire.KeyWaitID) != waitID-1 {
			t.Fatalf("errors = %v, want one stale action echoing wait %d", errs, waitID-1)
		}
		if got := len(ofEvent(alice.messages(), wire.EventDiscard)); got != 0 {
			t.Error("a stale action reached the engine")
		}
		h.assertSeatLogged(t, "stale game action")
		h.act(alice, discard(waitID, drawnTile(t, draw)))
		if got := len(ofEvent(alice.messages(), wire.EventDiscard)); got == 0 {
			t.Error("the turn stopped answering its own wait id")
		}
	})
}

func TestGameAction_WhenTheTileIsNotHeld_ShouldClose1008AndSeatAnAIPlayer(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, alice, bob := twoHumans(t, withTiming(func(timing *session.Timing) { timing.GameStartConfirm = 0 }))
		draw := lastDraw(t, alice)
		hand := ofEvent(bob.messages(), wire.EventRoundStarted)[0]
		bobsTile, _ := hand.Get(wire.KeyMyTiles)
		notHeld, _ := tile.NewTileID(int(bobsTile.(wire.Array)[0].(wire.Int)))

		h.act(alice, discard(intOf(t, draw, wire.KeyWaitID), notHeld))

		if code, closed := alice.closeCode(); !closed || code != session.CloseInvalidAction {
			t.Errorf("alice close = %v, %v, want 1008", code, closed)
		}
		control := ofSession(bob.messages(), "seat_control")
		if len(control) != 1 || intOf(t, control[0], wire.KeySeat) != 0 {
			t.Fatalf("bob seat_control = %v, want seat 0 handed to an AI player", control)
		}
		sleep(time.Second)
		if got := len(ofEvent(bob.messages(), wire.EventDiscard)); got != 1 {
			t.Errorf("discards bob saw = %d, want the AI player's for seat 0", got)
		}
	})
}

func TestDisconnect_WhenTheLastHumanLeaves_ShouldAbandonTheGameAndDiscardItsReplay(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, alice, bob := twoHumans(t)

		h.m.Disconnect(alice)
		synctest.Wait()
		if got := len(ofSession(bob.messages(), "seat_control")); got != 1 {
			t.Errorf("bob got %d seat_control, want 1", got)
		}
		h.m.Disconnect(bob)
		synctest.Wait()

		if got := h.m.GameCounts(); got != (session.GameCounts{}) {
			t.Errorf("GameCounts = %+v, want none", got)
		}
		if reason, _ := h.playedGame(t); reason.String != "abandoned" {
			t.Errorf("end_reason = %q, want abandoned", reason.String)
		}
		_, err := store.NewReplays(h.replayDir).Read(testGameID)
		if !errors.Is(err, fs.ErrNotExist) {
			t.Errorf("Replays.Read error = %v, want no replay stored", err)
		}
	})
}

func threeHumans(t *testing.T, wall [tile.TileIDCount]tile.TileID) (*harness, [3]*fakeConn) {
	t.Helper()
	h := newHarness(t, withSeed(seedSeating(t, 0, 1, 2)), withWalls(wall), withTiming(noWaits))
	conns := h.start("Alice", "Bob", "Carol")
	return h, [3]*fakeConn{conns[0], conns[1], conns[2]}
}

func callPrompt(t *testing.T, conn *fakeConn) wire.Map {
	t.Helper()
	prompts := ofEvent(conn.messages(), wire.EventCallPrompt)
	if len(prompts) != 1 {
		t.Fatalf("%s got %d call prompts, want 1", conn.id, len(prompts))
	}
	return prompts[0]
}

func answer(waitID int, action play.Action) messaging.GameActionMessage {
	kinds := map[play.ActionKind]messaging.GameAction{
		play.ActionPass: messaging.GameActionPass, play.ActionRon: messaging.GameActionRon,
	}
	return messaging.GameActionMessage{Action: kinds[action.Kind()], WaitID: waitID, Play: play.Some(action)}
}

func TestCallTimers_WhenOneOfTwoCallersPasses_ShouldKeepTheOtherCallersPromptAndDeadline(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, seats := threeHumans(t, ronAndPonWall(t))
		alice, bob, carol := seats[0], seats[1], seats[2]
		draw := lastDraw(t, alice)
		h.act(alice, discard(intOf(t, draw, wire.KeyWaitID), drawnTile(t, draw)))
		callPrompt(t, carol)
		ronPrompt := callPrompt(t, bob)

		sleep(5 * time.Second)
		h.act(bob, answer(intOf(t, ronPrompt, wire.KeyWaitID), play.PassAction()))
		if got := len(ofEvent(carol.messages(), wire.EventCallPrompt)); got != 1 {
			t.Errorf("carol got %d call prompts after bob passed, want her first only", got)
		}

		sleep(25*time.Second - time.Millisecond)
		if got := h.m.Stats().MeldTimeouts; got != 0 {
			t.Fatalf("carol timed out before her own deadline")
		}
		sleep(time.Millisecond)
		if got := h.m.Stats().MeldTimeouts; got != 1 {
			t.Errorf("MeldTimeouts at carol's deadline = %d, want 1", got)
		}
		if got := len(ofEvent(bob.messages(), wire.EventDraw)); got != 1 {
			t.Errorf("bob draws after the calls = %d, want 1", got)
		}
	})
}

func TestRoundAdvancePause_WhenADoubleRonEndsTheRound_ShouldWaitOncePerWinner(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, seats := threeHumans(t, doubleRonWall(t))
		alice, bob, carol := seats[0], seats[1], seats[2]
		draw := lastDraw(t, alice)
		h.act(alice, discard(intOf(t, draw, wire.KeyWaitID), drawnTile(t, draw)))
		h.act(bob, answer(intOf(t, callPrompt(t, bob), wire.KeyWaitID), play.RonAction()))
		h.act(carol, answer(intOf(t, callPrompt(t, carol), wire.KeyWaitID), play.RonAction()))

		ends := ofEvent(alice.messages(), wire.EventRoundEnd)
		if len(ends) != 1 {
			t.Fatalf("alice got %d round ends, want 1", len(ends))
		}
		if got, _ := ends[0].Get(wire.KeyRoundAdvanceSeconds); got != wire.Int(30) {
			t.Errorf("round end pause timeout = %v, want whole 30", got)
		}

		sleep(30*time.Second - time.Millisecond)
		if got := h.m.Stats().RoundAdvanceTimeouts; got != 0 {
			t.Fatalf("the pause timed out before twice the round advance")
		}
		sleep(time.Millisecond)
		if got := h.m.Stats().RoundAdvanceTimeouts; got != 3 {
			t.Errorf("RoundAdvanceTimeouts = %d, want each of the three seats", got)
		}
	})
}

type leakyClock struct{}

func (leakyClock) Now() time.Time {
	return time.Now()
}

func (leakyClock) AfterFunc(d time.Duration, f func()) func() bool {
	time.AfterFunc(d, f)
	return func() bool { return false }
}

func TestTurnTimer_WhenItFiresAfterTheSeatActedAndItWasCancelled_ShouldBeDropped(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, alice := soloDealer(t, withTiming(noWaits), func(c *session.Config) { c.Clock = leakyClock{} })
		sleep(time.Second)
		h.act(alice, defaultAnswer(t, lastOpening(t, alice)))
		waitID := intOf(t, lastOpening(t, alice), wire.KeyWaitID)

		sleep(29*time.Second + 500*time.Millisecond)

		stats := h.m.Stats()
		if stats.TurnTimeouts+stats.MeldTimeouts != 0 {
			t.Errorf("timeouts = %+v, want the superseded timer dropped", stats)
		}
		if got := intOf(t, lastOpening(t, alice), wire.KeyWaitID); got != waitID {
			t.Errorf("alice's wait id = %d, want her open decision %d kept", got, waitID)
		}
	})
}

type stubAgent func(ctx context.Context, decision play.Decision) (play.Action, error)

func (f stubAgent) Decide(ctx context.Context, view play.SeatView) (play.Action, error) {
	return f(ctx, view.Decision.Value)
}

func withAgent(agent session.Agent) option {
	return func(c *session.Config) { c.Agent = agent }
}

func onTurns(answer stubAgent) stubAgent {
	return func(ctx context.Context, decision play.Decision) (play.Action, error) {
		if _, call := decision.Context.(play.Call); call {
			return decision.Default, nil
		}
		return answer(ctx, decision)
	}
}

func offered(decision play.Decision, kind play.ActionKind, unlike play.Action) play.Action {
	for _, action := range decision.Legal {
		if action.Kind() == kind && action != unlike {
			return action
		}
	}
	return decision.Default
}

func handDiscard(decision play.Decision) play.Action {
	return offered(decision, play.ActionDiscard, decision.Default)
}

func TestAgent_WhenItAnswersAnAITurn_ShouldPlayAnOfferedAnswerElseTheDefaultOrFailOnAPanic(t *testing.T) {
	for _, tc := range []struct {
		name          string
		agent         stubAgent
		after         time.Duration
		wantDiscards  int
		wantTsumogiri bool
		wantFallback  bool
		wantFailed    bool
	}{
		{
			name:         "an offered discard",
			agent:        func(_ context.Context, d play.Decision) (play.Action, error) { return handDiscard(d), nil },
			wantDiscards: 4,
		},
		{
			name: "an error",
			agent: func(context.Context, play.Decision) (play.Action, error) {
				return play.Action{}, errors.New("agent unreachable")
			},
			wantDiscards: 4, wantTsumogiri: true, wantFallback: true,
		},
		{
			name: "a late answer",
			agent: func(ctx context.Context, d play.Decision) (play.Action, error) {
				<-ctx.Done()
				return handDiscard(d), nil
			},
			after:        session.DefaultTiming().BaseTurn,
			wantDiscards: 2, wantTsumogiri: true, wantFallback: true,
		},
		{
			name:       "a panic",
			agent:      func(context.Context, play.Decision) (play.Action, error) { panic("agent bug") },
			wantFailed: true,
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			synctest.Test(t, func(t *testing.T) {
				h, alice := soloDealer(t, withTiming(noWaits), withAgent(onTurns(tc.agent)))
				h.allowErrs = tc.wantFailed
				draw := lastDraw(t, alice)

				h.act(alice, discard(intOf(t, draw, wire.KeyWaitID), drawnTile(t, draw)))
				sleep(tc.after)

				if tc.wantFailed {
					if code, closed := alice.closeCode(); !closed || code != session.CloseInternalError {
						t.Errorf("alice close = %v, %v, want 1011", code, closed)
					}
					return
				}
				discards := ofEvent(alice.messages(), wire.EventDiscard)
				if len(discards) != tc.wantDiscards {
					t.Fatalf("discards alice saw = %d, want %d", len(discards), tc.wantDiscards)
				}
				move, err := wire.UnpackDiscard(intOf(t, discards[1], wire.KeyPackedMove))
				if err != nil || move.Tsumogiri != tc.wantTsumogiri {
					t.Errorf("first AI discard = %+v (%v), want tsumogiri %v", move, err, tc.wantTsumogiri)
				}
				fellBack := strings.Contains(h.logs.String(), "AI agent answer unusable, playing the default")
				if fellBack != tc.wantFallback {
					t.Errorf("fallback warning logged = %v, want %v", fellBack, tc.wantFallback)
				}
			})
		})
	}
}

func TestAgent_WhenACallersSeatIsTakenBackDuringItsRequest_ShouldLetTheOtherCallerAnswerAndDropTheLateOne(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		releaseCarolsCall := make(chan struct{})
		var bobAsked, carolAsked atomic.Bool
		agent := stubAgent(func(ctx context.Context, d play.Decision) (play.Action, error) {
			if _, call := d.Context.(play.Call); !call {
				return d.Default, nil
			}
			if d.Seat.Index() == 1 {
				bobAsked.Store(true)
				<-ctx.Done()
				return offered(d, play.ActionRon, d.Default), nil
			}
			carolAsked.Store(true)
			select {
			case <-releaseCarolsCall:
			case <-ctx.Done():
			}
			return offered(d, play.ActionPon, d.Default), nil
		})
		h := newHarness(t, withSeed(seedSeating(t, 0, 1, 2)), withWalls(ronAndPonWall(t)), withTiming(noWaits),
			withAgent(agent))
		conns := h.start("Alice", "Bob", "Carol")
		alice := conns[0]
		h.m.Disconnect(conns[1])
		h.m.Disconnect(conns[2])
		synctest.Wait()
		draw := lastDraw(t, alice)

		h.act(alice, discard(intOf(t, draw, wire.KeyWaitID), drawnTile(t, draw)))
		if !bobAsked.Load() || carolAsked.Load() {
			t.Fatalf("asked before the take-back: bob %v, carol %v, want bob's AI caller only",
				bobAsked.Load(), carolAsked.Load())
		}
		bob := h.reconnect("ticket-Bob")
		if !carolAsked.Load() {
			t.Fatal("carol's AI caller was not asked once bob took his seat back")
		}
		close(releaseCarolsCall)
		synctest.Wait()
		h.act(bob, answer(intOf(t, lastOpening(t, bob), wire.KeyWaitID), play.PassAction()))

		if got := len(ofEvent(alice.messages(), wire.EventRoundEnd)); got != 0 {
			t.Errorf("round ends alice saw = %d, want none from the reclaimed seat's late ron", got)
		}
		if got := len(ofEvent(alice.messages(), wire.EventMeld)); got != 1 {
			t.Errorf("melds alice saw = %d, want carol's AI pon once bob passed", got)
		}
	})
}
