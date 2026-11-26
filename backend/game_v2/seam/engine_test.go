package seam_test

import (
	"cmp"
	"errors"
	"fmt"
	"reflect"
	"slices"
	"strconv"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	twinGames     = 4
	decisionGames = 4
)

func TestNewGame_WhenTheSetupHasNoWall_ShouldReturnNoGameAndANoFixedWallError(t *testing.T) {
	g, events, err := engine.NewGame(engine.Setup{Walls: play.Fixed{}})

	if _, ok := errors.AsType[engine.NoFixedWallError](err); !ok {
		t.Errorf("NewGame error = %v, want a NoFixedWallError", err)
	}

	assertEqual(t, "events", events, nil)
	assertSameGame(t, "game", g, engine.Game{})
}

func TestSeedFunctions_WhenGivenTheSeedOfAGame_ShouldDescribeItsStartAndSeating(t *testing.T) {
	seed := seedOf(t, "ab")
	_, events := newGame(t, engine.Setup{Walls: play.Seeded{Seed: seed}})

	dealer, first, second := engine.FirstDealer(seed)
	_, dice := engine.RoundWall(seed, 0)
	permutation := engine.SeatPermutation(seed)
	assertEqual[play.Event](t, "game started", events[0].Event, play.GameStarted{
		FirstDealer: dealer, Dice: [2]tile.Dice{first, second}, Ruleset: play.RulesetTenhou, AkaDora: tile.AkaDoraEnabled,
		RiichiStickValue: 1000, HonbaValue: 300,
	})
	started, ok := events[1].Event.(play.RoundStarted)
	if !ok {
		t.Fatalf("second event = %#v, want a RoundStarted", events[1].Event)
	}

	assertEqual(t, "first round dice", started.Header.Dice, dice)
	sorted := permutation
	slices.SortFunc(sorted[:], func(a, b tile.Seat) int { return cmp.Compare(a.Index(), b.Index()) })
	assertEqual(t, "seated", sorted, tile.Seats())
}

func TestDealRound_WhenGivenTheSeedOfAGame_ShouldDealItsFirstRound(t *testing.T) {
	seed := seedOf(t, "ab")
	g, dealt := newGame(t, engine.Setup{Walls: play.Seeded{Seed: seed}})
	_, drew := begun(t, g)
	dealer, _, _ := engine.FirstDealer(seed)

	deal := engine.DealRound(seed, 0, dealer)

	var hands [tile.SeatCount][]tile.TileID
	var draws []play.Drew
	for _, e := range slices.Concat(dealt, drew) {
		if started, ok := e.Event.(play.RoundStarted); ok {
			hands[started.Seat.Index()] = started.Hand
			assertEqual(t, "dora indicators", started.DoraIndicators, []tile.TileID{deal.DoraIndicator})
		}

		if drew, ok := e.Event.(play.Drew); ok {
			draws = append(draws, drew)
		}
	}
	assertEqual(t, "hands", deal.Hands, hands)
	assertEqual(t, "draws", draws, []play.Drew{{Seat: dealer, Tile: deal.DealerDraw}})
	owned := slices.SortedFunc(slices.Values(slices.Concat(deal.Live, deal.DeadWall)), tile.TileID.Compare)
	allIDs := tile.AllTileIDs()
	assertEqual(t, "owned tiles", owned, allIDs[:])
}

func TestTsumogiriAgents_WhenTheyPlayASeededGame_ShouldReachItsStandingsWithTheLastEvent(t *testing.T) {
	g, initial := newGame(t, seededSetup(t, "cd"))
	sink := &recorder{}

	standings, err := playGame(&g, initial, tsumogiriAgents(), sink, maxGameSteps)
	assertEqual(t, "error", err, nil)
	assertEqual(t, "standings", g.Standings(), play.Some(standings))
	points := 0
	for _, p := range standings.Points {
		points += p
	}

	assertEqual(t, "totals", [2]int{scoreTotal(standings.Scores), points}, [2]int{tablePoints, 0})
	ends := slices.IndexFunc(sink.events, func(e play.Emitted) bool { _, ok := e.Event.(play.GameEnded); return ok })
	assertEqual(t, "game end index", ends, len(sink.events)-1)
	assertEqual[play.Event](t, "last event", sink.events[len(sink.events)-1].Event, play.GameEnded{Standings: standings})
	if rounds := len(g.View(seat(t, 0)).Record.History); rounds <= 1 {
		t.Errorf("history holds %d rounds, want more than 1", rounds)
	}
}

func TestFollow_WhenASeatFollowsTheEventsOfADiscard_ShouldReachItsViewAfterIt(t *testing.T) {
	g, _ := newGame(t, seededSetup(t, "cd"))
	g, _ = begun(t, g)
	discarder := turnSeat(t, g)
	watcher := discarder.Next()
	seen := g.View(watcher).Record

	next, events := act(t, g, discarder, play.DiscardAction(g.View(discarder).Record.Drawn.Value))
	afterDiscard := engine.Follow(seen, events[0])
	for _, e := range events {
		seen = engine.Follow(seen, e)
	}

	assertEqual(t, "record after every event", seen, next.View(watcher).Record)
	assertEqual(t, "live tiles after the discard alone", afterDiscard.LiveTiles, g.View(watcher).Record.LiveTiles)
	assertEqual(t, "latest discard after the discard alone", afterDiscard.LatestDiscard, play.Some(discarder))
}

func TestDecision_ShouldCarryTheLegalActionsAndDefaultActionOfItsSeat(t *testing.T) {
	var contexts [3]bool
	for gameIndex := range decisionGames {
		g, _ := newGame(t, seededSetup(t, fmt.Sprintf("%02x", gameIndex)))
		picker := newRandomLegal(uint64(gameIndex))
		for steps := 0; ; steps++ {
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

				assertEqual(t, "default", [2]any{fallback, hasDefault}, [2]any{decision.Default, true})
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

			if _, over := g.Awaiting().(play.AwaitingGameOver); over {
				break
			}

			s, ok := firstAwaited(g)
			if !ok {
				g, _ = dealOrBegin(t, g)
				continue
			}

			decision, _ := g.Decision(s)
			action, _ := picker.decide(decision)
			g, _ = act(t, g, s, action)
		}
	}
	assertEqual(t, "contexts", contexts, [3]bool{true, true, true})
}

func firstAwaited(g engine.Game) (tile.Seat, bool) {
	switch awaiting := g.Awaiting().(type) {
	case play.AwaitingTurn:
		return awaiting.Seat, true
	case play.AwaitingCall:
		return awaiting.Seats[0], true
	case play.AwaitingDealt, play.AwaitingRoundOver, play.AwaitingGameOver:
	}

	return tile.Seat{}, false
}

type twinCase struct {
	setup  engine.Setup
	seated agents
}

func twinCases(t *testing.T) []twinCase {
	t.Helper()
	cases := []twinCase{{setup: fixedSetup(t, threePinWall(t)), seated: tsumogiriAgents()}}
	for game := range uint64(twinGames) {
		cases = append(cases, twinCase{setup: seededSetup(t, fmt.Sprintf("%02x", game+0x10)), seated: selfPlayAgents(game + 1)})
	}

	return cases
}

func playTwins(t *testing.T, c twinCase, probe func(g engine.Game, events []play.Emitted) engine.Game) {
	t.Helper()
	probed, events := newGame(t, c.setup)
	twin, _ := newGame(t, c.setup)
	for steps := 0; ; steps++ {
		assertSameGame(t, "the probe's result", probe(probed, events), twin)
		assertSameGame(t, "the probed game", probed, twin)
		if steps >= maxGameSteps {
			t.Fatal("the game does not end")
		}

		if _, over := twin.Awaiting().(play.AwaitingGameOver); over {
			return
		}

		s, ok := firstAwaited(twin)
		if !ok {
			probed, events = dealOrBegin(t, probed)
			twin, _ = dealOrBegin(t, twin)
			continue
		}

		decision, _ := twin.Decision(s)
		action, _ := c.seated[s.Index()].decide(decision)
		probed, events = act(t, probed, s, action)
		twin, _ = act(t, twin, s, action)
	}
}

type scribbled struct {
	called, afterCall, prompt, win bool
}

func (s *scribbled) note(value any) {
	switch v := value.(type) {
	case play.Emitted:
		if _, called := v.Event.(play.Called); called {
			s.called = true
		}

		if ended, ok := v.Event.(play.RoundEnded); ok {
			_, ron := ended.Result.(play.Ron)
			_, tsumo := ended.Result.(play.Tsumo)
			s.win = s.win || ron || tsumo
		}
	case play.Decision:
		_, afterCall := v.Context.(play.TurnAfterCall)
		s.afterCall = s.afterCall || afterCall
	case play.AwaitingCall:
		s.prompt = true
	}
}

func scribble(v reflect.Value) {
	switch kind := v.Kind(); {
	case kind == reflect.Slice:
		whole := v.Slice(0, v.Cap())
		for i := range whole.Len() {
			scribble(whole.Index(i))
			if whole.Index(i).CanSet() {
				whole.Index(i).SetZero()
			}
		}
	case kind == reflect.Array:
		for i := range v.Len() {
			scribble(v.Index(i))
		}
	case kind == reflect.Struct:
		for i := range v.NumField() {
			if v.Type().Field(i).IsExported() {
				scribble(v.Field(i))
			}
		}
	case kind == reflect.Interface && !v.IsNil():
		scribble(v.Elem())
	}
}

func playEveryTwin(t *testing.T, cases []twinCase, playCase func(t *testing.T, at int, c twinCase)) {
	t.Helper()
	t.Run("twins", func(t *testing.T) {
		for at, c := range cases {
			t.Run(strconv.Itoa(at), func(t *testing.T) {
				t.Parallel()
				playCase(t, at, c)
			})
		}
	})
}

func TestGame_WhenACallerWritesIntoEverySliceItReturns_ShouldStayAsItsTwin(t *testing.T) {
	t.Parallel()
	cases := twinCases(t)
	seenByCase := make([]scribbled, len(cases))
	playEveryTwin(t, cases, func(t *testing.T, at int, c twinCase) {
		t.Helper()
		seen := &seenByCase[at]
		playTwins(t, c, func(g engine.Game, events []play.Emitted) engine.Game {
			var returned []any
			for _, e := range events {
				returned = append(returned, e)
			}

			returned = append(returned, events, g.Awaiting())
			for _, s := range tile.Seats() {
				decision, _ := g.Decision(s)
				returned = append(returned, decision, g.LegalActions(s), g.View(s))
			}

			for _, value := range returned {
				seen.note(value)
			}

			for _, value := range returned {
				scribble(reflect.ValueOf(value))
			}

			return g
		})
	})

	var seen scribbled
	for _, s := range seenByCase {
		seen = scribbled{
			called:    seen.called || s.called,
			afterCall: seen.afterCall || s.afterCall,
			prompt:    seen.prompt || s.prompt,
			win:       seen.win || s.win,
		}
	}

	assertEqual(t, "scribbled", seen, scribbled{called: true, afterCall: true, prompt: true, win: true})
}

func refusalProbes(g engine.Game, s tile.Seat) []play.Action {
	record := g.View(s).Record
	probes := []play.Action{play.PassAction(), play.TsumoAction(), play.RonAction(), play.KyuushuAction()}
	for _, held := range record.Hand {
		probes = append(probes, play.DiscardAction(held), play.RiichiAction(held))
	}

	if len(record.Hand) >= 2 {
		pair := [2]tile.TileID{record.Hand[0], record.Hand[1]}
		probes = append(probes, play.PonAction(pair), play.ChiAction(pair))
	}

	for _, unheld := range tile.AllTileIDs() {
		if !slices.Contains(record.Hand, unheld) {
			return append(probes, play.DiscardAction(unheld))
		}
	}

	return probes
}

func isOffered(legal []play.Action, action play.Action) bool {
	held, holds := action.Held()
	if !holds {
		return slices.Contains(legal, action)
	}

	reversed := [2]tile.TileID{held[1], held[0]}
	return slices.Contains(legal, action) || slices.Contains(legal, play.PonAction(reversed)) && action.Kind() == play.ActionPon ||
		slices.Contains(legal, play.ChiAction(reversed)) && action.Kind() == play.ActionChi
}

func TestAct_WhenRefused_ShouldChangeNothing(t *testing.T) {
	t.Parallel()
	cases := twinCases(t)
	kindsByCase := make([][3]bool, len(cases))
	playEveryTwin(t, cases, func(t *testing.T, at int, c twinCase) {
		t.Helper()
		kinds := &kindsByCase[at]
		playTwins(t, c, func(g engine.Game, _ []play.Emitted) engine.Game {
			for _, s := range tile.Seats() {
				legal := g.LegalActions(s)
				for _, action := range refusalProbes(g, s) {
					if isOffered(legal, action) {
						continue
					}

					next, events, refusal := g.Act(s, action)
					if !refusal.OK || events != nil {
						t.Fatalf("Act(seat %d, %v) = %v, %v; want a refusal and no events", s.Index(), action, events, refusal)
					}

					kinds[refusal.Value.Kind] = true
					g = next
				}
			}

			if _, roundOver := g.Awaiting().(play.AwaitingRoundOver); !roundOver {
				next, events, refusal := g.DealNextRound()
				if !refusal.OK || events != nil {
					t.Fatalf("DealNextRound = %v, %v; want a refusal and no events", events, refusal)
				}

				g = next
			}

			return g
		})
	})

	var kinds [3]bool
	for _, caseKinds := range kindsByCase {
		for kind, seen := range caseKinds {
			kinds[kind] = kinds[kind] || seen
		}
	}
	assertEqual(t, "refusal kinds", kinds, [3]bool{true, true, true})
}

func TestShanten_WhenOnlySevenPairsIsReady_ShouldCountThatShape(t *testing.T) {
	hand, err := tile.KindCounts(copies(t, 0, "1199m1199p1199s7z"))
	if err != nil {
		t.Fatalf("KindCounts error = %v", err)
	}

	got, err := engine.Shanten(hand)
	if err != nil || got != 0 {
		t.Errorf("Shanten = %d, %v, want 0, nil", got, err)
	}
}

func TestDisguised_ShouldPickAmongTheHeldCopiesThatLookTheSameAndLeaveEveryOtherActionAsNamed(t *testing.T) {
	hand := slices.Concat(copies(t, 0, "22m3m2468p135s"), copies(t, 0, "111z"))
	w := startWall{
		hands: [tile.SeatCount][]tile.TileID{hand, junk(t, 1), junk(t, 2), junk(t, 3)},
		draws: []tile.TileID{copyOf(t, 3, "1z")},
	}
	started, _ := newGame(t, fixedSetup(t, w))
	g, _ := begun(t, started)
	dealer := seat(t, 0)
	last := func(n int) int { return n - 1 }
	chi := play.ChiAction([2]tile.TileID{copyOf(t, 0, "2m"), copyOf(t, 0, "3m")})
	unheld := play.PonAction([2]tile.TileID{copyOf(t, 0, "9s"), copyOf(t, 1, "9s")})
	added := play.KanAction(play.KanAdded, copyOf(t, 0, "1z"))
	unheldKan := play.KanAction(play.KanClosed, copyOf(t, 0, "9s"))
	twice := play.ChiAction([2]tile.TileID{copyOf(t, 0, "2m"), copyOf(t, 0, "2m")})
	halfHeld := play.ChiAction([2]tile.TileID{copyOf(t, 0, "2m"), copyOf(t, 3, "3m")})

	kan := g.Disguised(dealer, play.KanAction(play.KanClosed, copyOf(t, 0, "1z")), last)
	assertEqual(t, "closed kan", kan, play.KanAction(play.KanClosed, copyOf(t, 3, "1z")))
	assertEqual(t, "chi", g.Disguised(dealer, chi, last),
		play.ChiAction([2]tile.TileID{copyOf(t, 1, "2m"), copyOf(t, 0, "3m")}))
	assertEqual(t, "pon of tiles not held", g.Disguised(dealer, unheld, last), unheld)
	assertEqual(t, "chi of one tile twice", g.Disguised(dealer, twice, last), twice)
	assertEqual(t, "chi of a tile not held", g.Disguised(dealer, halfHeld, last), halfHeld)
	assertEqual(t, "added kan", g.Disguised(dealer, added, last), added)
	assertEqual(t, "closed kan of a kind not held", g.Disguised(dealer, unheldKan, last), unheldKan)
	assertEqual(t, "discard", g.Disguised(dealer, play.DiscardAction(hand[0]), last), play.DiscardAction(hand[0]))
	_, events := act(t, g, dealer, kan)
	if _, called := events[0].Event.(play.Called); !called {
		t.Errorf("first event of the disguised kan = %+v, want the kan's meld", events[0].Event)
	}
}
