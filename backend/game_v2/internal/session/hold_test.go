package session_test

import (
	"slices"
	"testing"
	"testing/synctest"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func withDiscardHold(d time.Duration) option {
	return func(c *session.Config) { c.DiscardHold = func() time.Duration { return d } }
}

func TestDiscardHold_WhenNobodyAnswersTheDiscard_ShouldShowItAtOnceAndTheNextDrawAtTheDeadline(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, alice := soloDealer(t, withTiming(noWaits), withDiscardHold(500*time.Millisecond))
		draw := lastDraw(t, alice)
		turn := discard(intOf(t, draw, wire.KeyWaitID), drawnTile(t, draw))

		h.act(alice, turn)
		h.act(alice, turn)
		sleep(500*time.Millisecond - time.Millisecond)

		if got := len(ofEvent(alice.messages(), wire.EventDiscard)); got != 1 {
			t.Fatalf("discards shown during the hold = %d, want alice's own", got)
		}
		if got := len(ofEvent(alice.messages(), wire.EventDrawNotice)); got != 0 {
			t.Fatalf("draws shown before the hold ran out = %d, want none", got)
		}
		if got := len(ofEvent(alice.messages(), wire.EventError)); got != 1 {
			t.Errorf("errors for an action sent during the hold = %d, want one stale action", got)
		}

		sleep(time.Millisecond)
		if got := len(ofEvent(alice.messages(), wire.EventDrawNotice)); got != 1 {
			t.Errorf("draws shown at the hold's deadline = %d, want the next seat's", got)
		}
	})
}

func heldCall(t *testing.T) (h *harness, bob, carol *fakeConn) {
	t.Helper()
	h = newHarness(t, withSeed(seedSeating(t, 0, 1, 2)), withWalls(ronAndPonWall(t)), withDiscardHold(2*time.Second),
		withTiming(func(timing *session.Timing) {
			noWaits(timing)
			timing.BaseTurn = time.Second
		}))
	conns := h.start("Alice", "Bob", "Carol")
	draw := lastDraw(t, conns[0])
	h.act(conns[0], discard(intOf(t, draw, wire.KeyWaitID), drawnTile(t, draw)))
	return h, conns[1], conns[2]
}

func TestDiscardHold_WhenPonOutranksAnUnansweredChiAfterTheFloor_ShouldShowTheMeldAtOnce(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		wall := fixedWall(t, [tile.SeatCount][]tile.TileID{
			junkHand(t, 2), copies(t, 0, "1357m2468p346s57z"),
			copies(t, 1, "1357m2468p55s79s6z"), junkHand(t, 3),
		}, copies(t, 3, "5s"))
		const hold = time.Second
		h := newHarness(t, withSeed(seedSeating(t, 0, 1, 2)), withWalls(wall), withTiming(noWaits), withDiscardHold(hold))
		conns := h.start("Alice", "Bob", "Carol")
		alice, bob, carol := conns[0], conns[1], conns[2]
		draw := lastDraw(t, alice)
		h.act(alice, discard(intOf(t, draw, wire.KeyWaitID), drawnTile(t, draw)))
		callPrompt(t, bob)
		pair := copies(t, 1, "55s")
		sleep(300 * time.Millisecond)
		h.act(carol, messaging.GameActionMessage{
			Action: messaging.GameActionPon,
			WaitID: intOf(t, callPrompt(t, carol), wire.KeyWaitID),
			Play:   play.Some(play.PonAction([2]tile.TileID{pair[0], pair[1]})),
		})

		melds := ofEvent(alice.messages(), wire.EventMeld)
		if len(melds) != 1 {
			t.Fatalf("melds at the pon response = %d, want Carol's pon", len(melds))
		}
		meld, err := wire.UnpackMeld(intOf(t, melds[0], wire.KeyPackedMeld))
		if err != nil || meld.Kind != play.MeldPon {
			t.Errorf("meld = %+v (%v), want pon", meld, err)
		}
	})
}

func TestDiscardHold_WhenEveryCallerPassesEarly_ShouldDrawAtTheFloorAndChargeNoSeatForTheHold(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, bob, carol := heldCall(t)
		ronPrompt, ponPrompt := callPrompt(t, bob), callPrompt(t, carol)

		sleep(50 * time.Millisecond)
		h.act(carol, answer(intOf(t, ponPrompt, wire.KeyWaitID), play.PassAction()))
		sleep(50 * time.Millisecond)
		h.act(bob, answer(intOf(t, ronPrompt, wire.KeyWaitID), play.PassAction()))
		sleep(49 * time.Millisecond)
		if got := len(ofEvent(bob.messages(), wire.EventDraw)); got != 0 {
			t.Fatalf("bob drew %d times before the hold ran out, want none", got)
		}
		if got := len(ofEvent(bob.messages(), wire.EventFuriten)); got != 1 {
			t.Errorf("furiten changes bob got with his last pass = %d, want 1, as with a caller still open", got)
		}

		sleep(time.Millisecond)
		if got, _ := lastDraw(t, bob).Get(wire.KeyBankSeconds); got != wire.Int(20) {
			t.Errorf("bob's bank at his draw = %v, want the full 20 s", got)
		}
		sleep(21*time.Second - time.Millisecond)
		if got := h.m.Stats().TurnTimeouts; got != 0 {
			t.Fatalf("bob's turn timed out before a base turn and his bank passed from the deadline")
		}
		sleep(time.Millisecond)
		if got := h.m.Stats().TurnTimeouts; got != 1 {
			t.Errorf("TurnTimeouts a base turn and bob's bank after the deadline = %d, want 1", got)
		}
	})
}

func TestDiscardHold_WhenTheLastCallerPassesAfterTheFloor_ShouldDrawAtOnce(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, bob, carol := heldCall(t)
		ronPrompt, ponPrompt := callPrompt(t, bob), callPrompt(t, carol)

		sleep(50 * time.Millisecond)
		h.act(carol, answer(intOf(t, ponPrompt, wire.KeyWaitID), play.PassAction()))
		sleep(1450 * time.Millisecond)
		if got := len(ofEvent(bob.messages(), wire.EventDraw)); got != 0 {
			t.Fatalf("draws while Bob can still ron = %d, want none", got)
		}
		h.act(bob, answer(intOf(t, ronPrompt, wire.KeyWaitID), play.PassAction()))

		if got := len(ofEvent(bob.messages(), wire.EventDraw)); got != 1 {
			t.Errorf("bob's draws once the late passes are in = %d, want 1", got)
		}
		if got, _ := lastDraw(t, bob).Get(wire.KeyBankSeconds); got != wire.Float(19.5) {
			t.Errorf("bob's bank at his draw = %v, want 19.5 s after his late pass", got)
		}
		messages := bob.messages()
		isEvent := func(event wire.EventType) func(wire.Map) bool {
			return func(m wire.Map) bool { return len(ofEvent([]wire.Map{m}, event)) == 1 }
		}
		furitenAt, drawAt := slices.IndexFunc(messages, isEvent(wire.EventFuriten)), slices.IndexFunc(messages, isEvent(wire.EventDraw))
		if furitenAt < 0 || furitenAt > drawAt {
			t.Errorf("bob's furiten at message %d and draw at %d, want the furiten first, as with a caller still open",
				furitenAt, drawAt)
		}
	})
}

func TestDiscardHold_WhenASeatResyncsDuringIt_ShouldSnapshotTheDiscardAndReleaseNothing(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, alice := soloDealer(t, withTiming(noWaits), withDiscardHold(500*time.Millisecond))
		draw := lastDraw(t, alice)
		h.act(alice, discard(intOf(t, draw, wire.KeyWaitID), drawnTile(t, draw)))

		h.m.Resync(alice)
		synctest.Wait()

		messages := alice.messages()
		snapshot := reconnected(t, alice)
		if sessionType(messages[len(messages)-1]) != "game_reconnected" {
			t.Errorf("message after the snapshot = %v, want none: no decision is open", messages[len(messages)-1])
		}
		if _, discarded := snapshot.Get(wire.KeyLatestDiscardSeat); !discarded {
			t.Error("the snapshot holds no latest discard, want alice's")
		}
		if got := intOf(t, snapshot, wire.KeyTilesRemaining); got != 69 {
			t.Errorf("live tiles in the snapshot = %d, want 69, the next draw still held", got)
		}

		sleep(500 * time.Millisecond)
		if got := len(ofEvent(alice.messages(), wire.EventDrawNotice)); got != 1 {
			t.Errorf("draws shown at the hold's deadline = %d, want the next seat's once", got)
		}
	})
}

func TestDiscardHold_WhenTheDiscardBringsItsSeatFuriten_ShouldTellTheSeatWithTheDiscard(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		wall := fixedWall(t, [tile.SeatCount][]tile.TileID{
			copies(t, 0, "123456789m123p5s"), junkHand(t, 1), junkHand(t, 2), junkHand(t, 3),
		}, copies(t, 1, "5s"))
		h := newHarness(t, withSeed(seedSeating(t, 0)), withWalls(wall), withTiming(noWaits),
			withDiscardHold(500*time.Millisecond))
		alice := h.start("Alice")[0]
		draw := lastDraw(t, alice)

		h.act(alice, discard(intOf(t, draw, wire.KeyWaitID), drawnTile(t, draw)))

		if got := len(ofEvent(alice.messages(), wire.EventFuriten)); got != 1 {
			t.Errorf("furiten changes shown with the discard = %d, want alice's", got)
		}
		if got := len(ofEvent(alice.messages(), wire.EventDrawNotice)); got != 0 {
			t.Errorf("draws shown with the discard = %d, want none before the hold ran out", got)
		}
	})
}

func TestDiscardHold_WhenASeatDeclaresAClosedKan_ShouldShowTheKanAtOnceAndItsDrawAtTheDeadline(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		wall := fixedWall(t, [tile.SeatCount][]tile.TileID{
			copies(t, 0, "222m2468p1379s66z"), junkHand(t, 1), junkHand(t, 2), junkHand(t, 3),
		}, copies(t, 3, "2m"))
		h := newHarness(t, withSeed(seedSeating(t, 0)), withWalls(wall), withTiming(noWaits),
			withDiscardHold(500*time.Millisecond))
		alice := h.start("Alice")[0]
		draw := lastDraw(t, alice)

		h.act(alice, messaging.GameActionMessage{
			Action: messaging.GameActionKan, WaitID: intOf(t, draw, wire.KeyWaitID),
			Play: play.Some(play.KanAction(play.KanClosed, drawnTile(t, draw))),
		})
		sleep(500*time.Millisecond - time.Millisecond)
		if got := len(ofEvent(alice.messages(), wire.EventMeld)); got != 1 {
			t.Fatalf("melds shown during the hold = %d, want alice's kan", got)
		}
		if got := len(ofEvent(alice.messages(), wire.EventDoraRevealed)); got != 0 {
			t.Errorf("kan dora shown before the hold ran out = %d, want none: a robbed kan reveals none", got)
		}
		if got := len(ofEvent(alice.messages(), wire.EventDraw)); got != 1 {
			t.Fatalf("alice's draws before the hold ran out = %d, want her first only", got)
		}

		sleep(time.Millisecond)
		if got := len(ofEvent(alice.messages(), wire.EventDraw)); got != 2 {
			t.Errorf("alice's draws at the hold's deadline = %d, want her rinshan draw too", got)
		}
	})
}

func TestRandomDiscardHold_ShouldPauseAboutEightInAHundredDiscardsWithinItsBounds(t *testing.T) {
	const draws = 100_000
	pauses, total := 0, time.Duration(0)
	for range draws {
		hold := session.RandomDiscardHold()
		if hold < 150*time.Millisecond || hold > 2100*time.Millisecond {
			t.Fatalf("hold = %v, want within 150 ms and 2.1 s", hold)
		}
		if hold > 150*time.Millisecond {
			pauses++
			total += hold
		}
	}

	if share := float64(pauses) / draws; share < 0.07 || share > 0.09 {
		t.Errorf("share of pauses = %.3f, want about 0.08", share)
	}
	if mean := total / time.Duration(pauses); mean < time.Second || mean > 1150*time.Millisecond {
		t.Errorf("mean pause = %v, want about 1.07 s", mean)
	}
}

func TestDiscardHold_WhenASeatLeavesWhileTheGamesEndIsHeld_ShouldCompleteTheGameFirst(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		bustedDealer := play.StartPosition{Scores: [tile.SeatCount]int{1000, 33000, 33000, 33000}}
		h := newHarness(t, withSeed(seedSeating(t, 0, 1, 2)), withTiming(noWaits), withDiscardHold(2*time.Second),
			func(c *session.Config) {
				c.Setup = func(engine.Seed) engine.Setup {
					return engine.Setup{
						Walls: play.Fixed{Walls: [][tile.TileIDCount]tile.TileID{doubleRonWall(t)}},
						Start: play.Some(bustedDealer),
					}
				}
			})
		conns := h.start("Alice", "Bob", "Carol")
		alice, bob, carol := conns[0], conns[1], conns[2]
		draw := lastDraw(t, alice)
		h.act(alice, discard(intOf(t, draw, wire.KeyWaitID), drawnTile(t, draw)))
		h.act(bob, answer(intOf(t, callPrompt(t, bob), wire.KeyWaitID), play.RonAction()))
		h.act(carol, answer(intOf(t, callPrompt(t, carol), wire.KeyWaitID), play.RonAction()))
		if got := len(ofEvent(bob.messages(), wire.EventRoundEnd)); got != 0 {
			t.Fatalf("round ends shown before the hold ran out = %d, want none", got)
		}

		h.m.Disconnect(alice)
		synctest.Wait()

		if got := len(ofEvent(bob.messages(), wire.EventGameEnd)); got != 1 {
			t.Errorf("game ends bob got once alice left = %d, want 1", got)
		}
		if reason, _ := h.playedGame(t); reason.String != "completed" {
			t.Errorf("end_reason = %q, want completed: the engine had ended the game", reason.String)
		}
		records := h.replay(t)
		if typ, _ := eventType(records[len(records)-1]); typ != wire.EventGameEnd {
			t.Errorf("last replay record = %v, want the game end, no seat control after it", records[len(records)-1])
		}
	})
}
