package game_test

import (
	"errors"
	"fmt"
	"slices"
	"strings"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rng"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/wall"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const maxGameSteps = 20000

func dealerTenpaiWall(t *testing.T, dealer tile.Seat) testkit.StartWall {
	t.Helper()
	var w testkit.StartWall
	junkCopy := 1
	for _, s := range tile.Seats() {
		if s == dealer {
			w.Hands[s.Index()] = copies(t, 0, "123456789m1234p")
			continue
		}
		w.Hands[s.Index()] = junk(t, junkCopy)
		junkCopy++
	}
	return w
}

func startAt(t *testing.T, dealer int, wind tile.Wind, scores [tile.SeatCount]int, riichiSticks int) play.Option[play.StartPosition] {
	t.Helper()
	return play.Some(play.StartPosition{Scores: scores, RiichiSticks: riichiSticks, Dealer: seat(t, dealer), Wind: wind})
}

func awaitedSeats(g game.Game) []tile.Seat {
	switch a := g.Awaiting().(type) {
	case play.AwaitingTurn:
		return []tile.Seat{a.Seat}
	case play.AwaitingCall:
		return a.Seats
	case play.AwaitingRoundOver, play.AwaitingGameOver:
	}
	return nil
}

func isOver(g game.Game) bool {
	return g.Phase() != play.PhasePlaying
}

func finishRoundByDefaults(t *testing.T, g game.Game) (game.Game, []play.Emitted) {
	t.Helper()
	for range maxGameSteps {
		seats := awaitedSeats(g)
		if len(seats) == 0 {
			t.Fatal("the round is not in play")
		}
		for _, s := range seats {
			action, _ := g.DefaultAction(s)
			var events []play.Emitted
			g, events = script(t, g, act(s, action))
			if isOver(g) {
				return g, events
			}
		}
	}
	t.Fatal("the round does not end")
	return g, nil
}

func gameEnded(t *testing.T, events []play.Emitted) play.Standings {
	t.Helper()
	kinds := testkit.EventKinds(events)
	if len(kinds) < 2 || !slices.Equal(kinds[len(kinds)-2:], []string{"round_ended", "game_ended"}) {
		t.Fatalf("event kinds = %v, want them to end with round_ended, game_ended", kinds)
	}
	ended, _ := events[len(events)-1].Event.(play.GameEnded)
	return ended.Standings
}

func assertGameOver(t *testing.T, g game.Game, events []play.Emitted) play.Standings {
	t.Helper()
	standings := gameEnded(t, events)
	assertEqual(t, "phase", g.Phase(), play.PhaseGameOver)
	assertEqual(t, "awaiting", g.Awaiting(), play.Awaiting(play.AwaitingGameOver{}))
	assertEqual(t, "standings", g.Standings(), play.Some(standings))
	_, _, refused := g.DealNextRound()
	assertEqual(t, "deal refusal", refused, play.Some(refusal(play.RefusalNotAwaited, play.CodeWrongPhase)))
	return standings
}

func endCauseAfterRound(t *testing.T, w testkit.StartWall, start play.Option[play.StartPosition]) play.Option[play.GameEndCause] {
	t.Helper()
	g, events := finishRoundByDefaults(t, begun(t, w, start))
	if g.Phase() == play.PhaseRoundOver {
		if kinds := testkit.EventKinds(events); kinds[len(kinds)-1] != "round_ended" {
			t.Errorf("last event = %s, want round_ended", kinds[len(kinds)-1])
		}
		return play.Option[play.GameEndCause]{}
	}
	return play.Some(assertGameOver(t, g, events).Cause)
}

func TestDealNextRound_ShouldDealTheNextFixedWallFromTheNewDealer(t *testing.T) {
	var hands [tile.SeatCount][]tile.TileID
	for i := range hands {
		hands[i] = copies(t, i, "123456789m1234p")
	}
	dealerDraw := tileOf(t, 0, "9p")
	second := testkit.StartWall{Hands: hands, Draws: []tile.TileID{dealerDraw}}
	g, _ := newGame(t, fixed(wallTiles(t, notenWall(t), seat(t, 0)), wallTiles(t, second, seat(t, 1))), noStart())
	g, _ = finishRoundByDefaults(t, g)
	assertEqual(t, "awaiting", g.Awaiting(), play.Awaiting(play.AwaitingRoundOver{}))

	g, events, refused := g.DealNextRound()

	assertEqual(t, "refusal", refused, play.Option[play.Refusal]{})
	header := play.RoundHeader{
		RoundNumber: 1, Wind: tile.East, RoundInWind: 2, Dealer: seat(t, 1), Honba: 1,
		Dice: evenDice(),
	}
	for i, s := range tile.Seats() {
		started, _ := events[i].Event.(play.RoundStarted)
		assertEqual(t, "dealt", [3]any{started.Seat, started.Header, started.Hand}, [3]any{s, header, hands[i]})
	}
	assertEqual(t, "phase", g.Phase(), play.PhasePlaying)
	assertEqual(t, "header", g.Header(), header)
	assertEqual[play.Event](t, "draw", events[4].Event, play.Drew{Seat: seat(t, 1), Tile: dealerDraw})
}

func TestNew_WhenALaterFixedWallRepeatsATile_ShouldRefuseTheSetup(t *testing.T) {
	valid := wallTiles(t, notenWall(t), seat(t, 0))
	repeating := valid
	repeating[1] = repeating[0]

	_, _, err := game.New(fixed(valid, repeating), noStart())

	if want := (game.InvalidWallError{Err: wall.DuplicateTileError{Tile: repeating[0]}}); !errors.Is(err, want) {
		t.Errorf("error = %v, want %v", err, want)
	}
}

func TestDealNextRound_WhenTheLastFixedWallWasDealt_ShouldEndTheGame(t *testing.T) {
	g, _ := finishRoundByDefaults(t, begun(t, notenWall(t), noStart()))

	g, events, _ := g.DealNextRound()

	assertEqual(t, "kinds", testkit.EventKinds(events), []string{"game_ended"})
	ended, _ := events[0].Event.(play.GameEnded)
	assertEqual(t, "standings", ended.Standings, play.Standings{
		Cause:      play.EndFixedWallsDealt,
		Scores:     [tile.SeatCount]int{25000, 25000, 25000, 25000},
		Placements: [tile.SeatCount]int{1, 2, 3, 4},
		Points:     [tile.SeatCount]int{350, 50, -150, -250},
	})
	assertEqual(t, "phase", g.Phase(), play.PhaseGameOver)
	assertEqual(t, "awaiting", g.Awaiting(), play.Awaiting(play.AwaitingGameOver{}))
	assertEqual(t, "game standings", g.Standings(), play.Some(ended.Standings))
	_, _, refused := g.DealNextRound()
	assertEqual(t, "refusal", refused, play.Some(refusal(play.RefusalNotAwaited, play.CodeWrongPhase)))
}

func TestFinishRound_WhenAScoreFallsBelowZero_ShouldEndTheGameByTobiRightAfterTheRound(t *testing.T) {
	start := startAt(t, 0, tile.East, [tile.SeatCount]int{49500, 25000, 25000, 500}, 0)

	g, events := finishRoundByDefaults(t, begun(t, dealerTenpaiWall(t, seat(t, 0)), start))

	standings := assertGameOver(t, g, events)
	assertEqual(t, "standings", standings, play.Standings{
		Cause:      play.EndTobi,
		Scores:     [tile.SeatCount]int{52500, 24000, 24000, -500},
		Placements: [tile.SeatCount]int{1, 2, 3, 4},
		Points:     [tile.SeatCount]int{625, 40, -160, -505},
	})
	assertEqual(t, "scores", g.Scores(), standings.Scores)
}

func TestFinishRound_WhenAScoreIsExactlyZero_ShouldPlayOn(t *testing.T) {
	start := startAt(t, 0, tile.East, [tile.SeatCount]int{49000, 25000, 25000, 1000}, 0)

	assertEqual(t, "cause", endCauseAfterRound(t, dealerTenpaiWall(t, seat(t, 0)), start), play.Option[play.GameEndCause]{})
}

func TestDealNextRound_WhenEastFourEndsWithASeatAtTheThreshold_ShouldPlaySouthOne(t *testing.T) {
	start := startAt(t, 3, tile.East, [tile.SeatCount]int{35000, 21700, 21700, 21600}, 0)
	source := fixed(wallTiles(t, notenWall(t), seat(t, 3)), wallTiles(t, notenWall(t), seat(t, 0)))
	g, _ := newGame(t, source, start)
	g, _ = finishRoundByDefaults(t, g)

	g, _, _ = g.DealNextRound()

	header := g.Header()
	assertEqual(t, "position", [4]any{header.Wind, header.RoundInWind, header.Dealer, header.Honba},
		[4]any{tile.South, 1, seat(t, 0), 1})
}

func TestFinishRound_WhenSouthFourEndsWithASeatAtTheThreshold_ShouldEndTheGameByLength(t *testing.T) {
	start := startAt(t, 3, tile.South, [tile.SeatCount]int{35000, 21700, 21700, 21600}, 0)

	g, events := finishRoundByDefaults(t, begun(t, notenWall(t), start))

	standings := assertGameOver(t, g, events)
	assertEqual(t, "cause", standings.Cause, play.EndLength)
	assertEqual(t, "placements", standings.Placements, [tile.SeatCount]int{1, 2, 3, 4})
}

func TestFinishRound_WhenSouthFourEndsBelowTheThreshold_ShouldPlayIntoWest(t *testing.T) {
	start := startAt(t, 3, tile.South, [tile.SeatCount]int{29000, 24000, 24000, 23000}, 0)

	assertEqual(t, "cause", endCauseAfterRound(t, notenWall(t), start), play.Option[play.GameEndCause]{})
}

func TestFinishRound_WhenAWestRoundEndsWithASeatAtTheThreshold_ShouldEndTheGameByTarget(t *testing.T) {
	start := startAt(t, 0, tile.West, [tile.SeatCount]int{30000, 25000, 22000, 23000}, 0)

	assertEqual(t, "cause", endCauseAfterRound(t, notenWall(t), start), play.Some(play.EndTargetReached))
}

func TestFinishRound_WhenWestFourEndsBelowTheThreshold_ShouldEndTheGameByTheExtensionLimit(t *testing.T) {
	start := startAt(t, 3, tile.West, [tile.SeatCount]int{25000, 25000, 25000, 25000}, 0)

	assertEqual(t, "cause", endCauseAfterRound(t, notenWall(t), start), play.Some(play.EndExtensionLimit))
}

func TestFinishRound_WhenTheSouthFourDealerIsTenpaiFirstAtTheTarget_ShouldStopAndTakeTheSticksLeft(t *testing.T) {
	start := startAt(t, 3, tile.South, [tile.SeatCount]int{24000, 23000, 23000, 28000}, 2)

	g, events := finishRoundByDefaults(t, begun(t, dealerTenpaiWall(t, seat(t, 3)), start))

	roundEnded, _ := events[len(events)-2].Event.(play.RoundEnded)
	assertEqual(t, "round end", [2]any{roundEnded.Scores, roundEnded.RiichiSticks},
		[2]any{[tile.SeatCount]int{23000, 22000, 22000, 31000}, 2})
	standings := assertGameOver(t, g, events)
	assertEqual(t, "cause", standings.Cause, play.EndLength)
	assertEqual(t, "scores", standings.Scores, [tile.SeatCount]int{23000, 22000, 22000, 33000})
	assertEqual(t, "placements", standings.Placements, [tile.SeatCount]int{2, 3, 4, 1})
	assertEqual(t, "sticks", g.RiichiSticks(), 0)
}

func TestFinishRound_WhenTheSouthFourDealerIsTenpaiBelowTheTarget_ShouldRepeat(t *testing.T) {
	start := startAt(t, 3, tile.South, [tile.SeatCount]int{24000, 23000, 23000, 26000}, 4)

	assertEqual(t, "cause", endCauseAfterRound(t, dealerTenpaiWall(t, seat(t, 3)), start), play.Option[play.GameEndCause]{})
}

func seededBy(t *testing.T, pair string) play.WallSource {
	t.Helper()
	seed, err := rng.ParseSeed(strings.Repeat(pair, rng.SeedBytes))
	if err != nil {
		t.Fatalf("ParseSeed error = %v", err)
	}
	return play.Seeded{Seed: seed}
}

func tsumogiri(decision play.Decision) play.Action {
	for _, win := range []play.Action{play.TsumoAction(), play.RonAction()} {
		if slices.Contains(decision.Legal, win) {
			return win
		}
	}
	return decision.Default
}

type randomLegal struct {
	state uint64
}

func (r *randomLegal) decide(decision play.Decision) play.Action {
	r.state ^= r.state << 13
	r.state ^= r.state >> 7
	r.state ^= r.state << 17
	return decision.Legal[r.state%uint64(len(decision.Legal))]
}

func playToTheEnd(t *testing.T, g game.Game, decide func(play.Decision) play.Action) (game.Game, []play.Emitted) {
	t.Helper()
	var events []play.Emitted
	for range maxGameSteps {
		if g.Phase() == play.PhaseGameOver {
			return g, events
		}
		if g.Phase() == play.PhaseRoundOver {
			var batch []play.Emitted
			g, batch, _ = g.DealNextRound()
			events = append(events, batch...)
			continue
		}
		for _, s := range awaitedSeats(g) {
			decision, _ := g.Decision(s)
			var batch []play.Emitted
			g, batch = script(t, g, act(s, decide(decision)))
			events = append(events, batch...)
		}
		if err := g.CheckInvariants(); err != nil {
			t.Fatalf("CheckInvariants error = %v", err)
		}
	}
	t.Fatal("the game does not end")
	return g, events
}

func TestNew_WhenTsumogiriAgentsPlayASeededGame_ShouldReachItsStandings(t *testing.T) {
	g, initial := newGame(t, seededBy(t, "cd"), noStart())

	g, events := playToTheEnd(t, g, tsumogiri)

	standings := g.Standings()
	if !standings.OK {
		t.Fatal("the game has no standings")
	}
	scores, points := 0, 0
	for i := range standings.Value.Scores {
		scores += standings.Value.Scores[i]
		points += standings.Value.Points[i]
	}
	assertEqual(t, "totals", [2]int{scores, points}, [2]int{100000, 0})
	all := slices.Concat(initial, events)
	ends := slices.IndexFunc(all, func(e play.Emitted) bool { _, ok := e.Event.(play.GameEnded); return ok })
	assertEqual(t, "game end index", ends, len(all)-1)
	assertEqual[play.Event](t, "last event", all[len(all)-1].Event, play.GameEnded{Standings: standings.Value})
	if len(g.History()) <= 1 {
		t.Errorf("history holds %d rounds, want more than 1", len(g.History()))
	}
}

func TestDecision_ShouldCarryTheLegalActionsAndDefaultActionOfItsSeat(t *testing.T) {
	var contexts [3]bool
	for gameIndex := range 4 {
		g, _ := newGame(t, seededBy(t, fmt.Sprintf("%02x", gameIndex)), noStart())
		agent := randomLegal{state: uint64(gameIndex)}
		if gameIndex == 0 {
			agent.state = 0x9E3779B97F4A7C15
		}
		for steps := 0; g.Phase() != play.PhaseGameOver; steps++ {
			if steps >= maxGameSteps {
				t.Fatalf("game %d does not end", gameIndex)
			}
			for _, s := range tile.Seats() {
				decision, ok := g.Decision(s)
				fallback, hasDefault := g.DefaultAction(s)
				if !ok {
					if hasDefault || len(g.LegalActions(s)) != 0 {
						t.Fatalf("seat %d without a decision has actions", s.Index())
					}
					continue
				}
				assertEqual(t, "default", fallback, decision.Default)
				assertEqual(t, "legal", g.LegalActions(s), decision.Legal)
				if !slices.Contains(decision.Legal, decision.Default) {
					t.Fatalf("default %v is not legal", decision.Default)
				}
				switch decision.Context.(type) {
				case play.TurnAfterDraw:
					contexts[0] = true
				case play.TurnAfterCall:
					contexts[1] = true
				case play.Call:
					contexts[2] = true
				}
			}
			if g.Phase() == play.PhaseRoundOver {
				g, _, _ = g.DealNextRound()
				continue
			}
			s := awaitedSeats(g)[0]
			decision, _ := g.Decision(s)
			g, _ = script(t, g, act(s, agent.decide(decision)))
		}
	}
	assertEqual(t, "contexts", contexts, [3]bool{true, true, true})
}
