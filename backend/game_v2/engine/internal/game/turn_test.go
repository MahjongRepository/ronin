package game_test

import (
	"errors"
	"math"
	"strings"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rng"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/wall"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func fixedSeed(t *testing.T) rng.Seed {
	t.Helper()
	seed, err := rng.ParseSeed(strings.Repeat("ab", rng.SeedBytes))
	if err != nil {
		t.Fatalf("ParseSeed error = %v", err)
	}
	return seed
}

func seeded(t *testing.T) play.WallSource {
	t.Helper()
	return play.Seeded{Seed: fixedSeed(t)}
}

func stagedWall(t *testing.T) testkit.StartWall {
	t.Helper()
	return testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			ids(t, 0, 4, 8, 12, 36, 40, 44, 48, 72, 76, 80, 84, 108),
			ids(t, 1, 5, 9, 13, 37, 41, 45, 49, 73, 77, 81, 85, 112),
			ids(t, 2, 6, 10, 14, 38, 42, 46, 50, 74, 78, 82, 86, 116),
			ids(t, 3, 7, 11, 15, 39, 43, 47, 51, 75, 79, 83, 87, 120),
		},
		Draws: ids(t, 124, 125, 126, 127),
	}
}

func evenDice() tile.Dice {
	return tile.Dice{First: 1, Second: 1}
}

func TestNew_WhenTheWallIsFixed_ShouldDealSeatZeroAndAnnounceEveryHand(t *testing.T) {
	g, events := newGame(t, fixed(wallTiles(t, testkit.StartWall{}, seat(t, 0))), noStart())

	header := play.RoundHeader{Wind: tile.East, RoundInWind: 1, Dealer: seat(t, 0), Dice: evenDice()}
	want := []play.Emitted{{To: play.ToAll(), Event: play.GameStarted{
		FirstDealer: seat(t, 0), Dice: [2]tile.Dice{evenDice(), evenDice()},
	}}}
	for _, s := range tile.Seats() {
		want = append(want, play.Emitted{To: play.ToSeat(s), Event: play.RoundStarted{
			Seat:           s,
			Header:         header,
			Scores:         [tile.SeatCount]int{25000, 25000, 25000, 25000},
			Hand:           g.Hand(s)[:wall.StartingHandSize],
			DoraIndicators: ids(t, 124),
			LiveTiles:      70,
		}})
	}
	assertEqual(t, "first events", events[:5], want)
	assertEqual(t, "phase", g.Phase(), play.PhasePlaying)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 0)))
	assertEqual(t, "header", g.Header(), header)
	if err := g.CheckOwnership(); err != nil {
		t.Errorf("CheckOwnership error = %v", err)
	}
}

func TestNew_WhenSeeded_ShouldTakeTheFirstDealerAndTheRoundZeroWallFromTheSeed(t *testing.T) {
	g, events := newGame(t, seeded(t), noStart())

	assertEqual[play.Event](t, "first event", events[0].Event, play.GameStarted{
		FirstDealer: seat(t, 0), Dice: [2]tile.Dice{{First: 2, Second: 2}, {First: 5, Second: 1}},
	})
	assertEqual(t, "dealer hand", g.Hand(seat(t, 0)), ids(t, 0, 6, 26, 35, 43, 54, 55, 62, 67, 73, 79, 88, 100, 72))
	assertEqual(t, "dice", g.Header().Dice, tile.Dice{First: 5, Second: 5})
	assertEqual[play.Event](t, "draw", events[5].Event, play.Drew{Seat: seat(t, 0), Tile: id(t, 72)})
}

func TestNew_WhenSeededWithAStartPosition_ShouldDealThatRoundsWall(t *testing.T) {
	start := play.StartPosition{
		Scores:       [tile.SeatCount]int{30000, 19000, 25000, 24000},
		Honba:        1,
		RiichiSticks: 2,
		Dealer:       seat(t, 1),
		Wind:         tile.South,
		RoundNumber:  3,
	}

	g, events := newGame(t, seeded(t), play.Some(start))

	w := wall.FromSeed(fixedSeed(t), 3, seat(t, 1))
	hands := w.Deal(seat(t, 1))
	for _, s := range tile.Seats() {
		assertEqual(t, "hand", g.Hand(s)[:wall.StartingHandSize], hands[s.Index()][:])
	}
	assertEqual(t, "header", g.Header(), play.RoundHeader{
		RoundNumber: 3, Wind: tile.South, RoundInWind: 2, Dealer: seat(t, 1), Honba: 1, RiichiSticks: 2,
		Dice: w.Dice(),
	})
	assertEqual(t, "scores", g.Scores(), start.Scores)
	if started, ok := events[0].Event.(play.GameStarted); !ok || started.FirstDealer != seat(t, 0) {
		t.Errorf("first event = %+v, want GameStarted with first dealer 0", events[0].Event)
	}
}

func TestNew_WhenTheWallIsFixedWithAStartPosition_ShouldDealTheStagedHandsFromItsDealer(t *testing.T) {
	start := play.StartPosition{
		Scores: [tile.SeatCount]int{25000, 25000, 25000, 25000}, Dealer: seat(t, 2), Wind: tile.West, RoundNumber: 9,
	}
	w := stagedWall(t)

	g := begun(t, w, play.Some(start))

	for _, n := range []int{0, 1, 3} {
		assertEqual(t, "hand", g.Hand(seat(t, n)), w.Hands[n])
	}
	assertEqual(t, "dealer hand", g.Hand(seat(t, 2)), append(w.Hands[2], id(t, 124)))
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 2)))
	assertEqual(t, "round in wind", g.Header().RoundInWind, 3)
}

func TestNew_WhenTheFixedSetupIsMalformed_ShouldRefuseIt(t *testing.T) {
	_, _, err := game.New(fixed(), noStart())
	if !errors.Is(err, game.NoFixedWallError{}) {
		t.Errorf("New(no walls) error = %v, want NoFixedWallError", err)
	}

	repeated := tile.AllTileIDs()
	repeated[1] = id(t, 0)
	_, _, err = game.New(fixed(repeated), noStart())
	if !errors.Is(err, game.InvalidWallError{Err: wall.DuplicateTileError{Tile: id(t, 0)}}) ||
		!errors.Is(err, wall.DuplicateTileError{Tile: id(t, 0)}) {
		t.Errorf("New(repeated tile) error = %v, want InvalidWallError of tile 0", err)
	}
}

func TestNew_WhenNoWallSourceIsGiven_ShouldRefuseItAsNoFixedWall(t *testing.T) {
	if _, _, err := game.New(nil, noStart()); !errors.Is(err, game.NoFixedWallError{}) {
		t.Errorf("New(nil) error = %v, want NoFixedWallError", err)
	}
}

func startError(t *testing.T, scores [tile.SeatCount]int, riichiSticks int, wind tile.Wind) error {
	t.Helper()
	start := play.StartPosition{Scores: scores, RiichiSticks: riichiSticks, Dealer: seat(t, 0), Wind: wind}
	_, _, err := game.New(seeded(t), play.Some(start))
	return err
}

func TestNew_WhenAStartScoreIsOffTheHundreds_ShouldRefuseIt(t *testing.T) {
	err := startError(t, [tile.SeatCount]int{25000, 25050, 24950, 25000}, 0, tile.East)
	if !errors.Is(err, game.StartScoreOffHundredsError{Seat: seat(t, 1)}) {
		t.Errorf("error = %v, want StartScoreOffHundredsError of seat 1", err)
	}
}

func TestNew_WhenAStartScoreIsBelowTheTobiThreshold_ShouldRefuseIt(t *testing.T) {
	err := startError(t, [tile.SeatCount]int{50100, 25000, 25000, -100}, 0, tile.East)
	if !errors.Is(err, game.StartScoreBelowTobiError{Seat: seat(t, 3)}) {
		t.Errorf("error = %v, want StartScoreBelowTobiError of seat 3", err)
	}
}

func TestNew_WhenStartPointsAreOffTheTableTotal_ShouldRefuseThem(t *testing.T) {
	for _, c := range []struct {
		scores       [tile.SeatCount]int
		riichiSticks int
		found        int
	}{
		{[tile.SeatCount]int{25000, 25000, 25000, 25000}, 1, 101000},
		{[tile.SeatCount]int{40000, 30000, 30000, 20000}, 0, 120000},
	} {
		err := startError(t, c.scores, c.riichiSticks, tile.South)
		if !errors.Is(err, game.StartPointsOffTotalError{Found: c.found, Expected: 100000}) {
			t.Errorf("error = %v, want StartPointsOffTotalError found %d", err, c.found)
		}
	}
}

func TestNew_WhenStartPointsOverflow_ShouldReportTheTotalSaturated(t *testing.T) {
	largest := math.MaxInt - math.MaxInt%100
	for _, c := range []struct {
		scores       [tile.SeatCount]int
		riichiSticks int
	}{
		{[tile.SeatCount]int{largest, largest, 0, 0}, 0},
		{[tile.SeatCount]int{0, 0, 0, 100000}, math.MaxInt / 10},
	} {
		err := startError(t, c.scores, c.riichiSticks, tile.East)
		if !errors.Is(err, game.StartPointsOffTotalError{Found: math.MaxInt, Expected: 100000}) {
			t.Errorf("error = %v, want StartPointsOffTotalError found MaxInt", err)
		}
	}
}

func TestNew_WhenAStartCountIsNegative_ShouldRefuseIt(t *testing.T) {
	err := startError(t, [tile.SeatCount]int{25000, 25000, 25000, 26000}, -1, tile.East)
	if !errors.Is(err, game.NegativeStartCountError{}) {
		t.Errorf("negative sticks error = %v, want NegativeStartCountError", err)
	}

	start := play.StartPosition{Scores: [tile.SeatCount]int{25000, 25000, 25000, 25000}, Honba: -1}
	if _, _, err := game.New(seeded(t), play.Some(start)); !errors.Is(err, game.NegativeStartCountError{}) {
		t.Errorf("negative honba error = %v, want NegativeStartCountError", err)
	}
}

func TestNew_WhenTheStartIsInNorthOrPastIt_ShouldRefuseIt(t *testing.T) {
	for _, wind := range []tile.Wind{tile.North, tile.North + 1} {
		if err := startError(t, [tile.SeatCount]int{25000, 25000, 25000, 25000}, 0, wind); !errors.Is(err, game.StartInNorthError{}) {
			t.Errorf("wind %d error = %v, want StartInNorthError", wind, err)
		}
	}
}

func TestNew_WhenTheStartHasSticksPaidFromTheScoresAndASeatAtZero_ShouldTakeIt(t *testing.T) {
	if err := startError(t, [tile.SeatCount]int{49000, 25000, 24000, 0}, 2, tile.West); err != nil {
		t.Errorf("error = %v, want none", err)
	}
}

func TestBegin_ShouldDrawForTheDealerAndNotifyTheOthers(t *testing.T) {
	g, events := newGame(t, fixed(wallTiles(t, stagedWall(t), seat(t, 0))), noStart())

	notice := func(to int) play.Emitted {
		return play.Emitted{To: play.ToSeat(seat(t, to)), Event: play.DrewNotice{Seat: seat(t, 0)}}
	}
	drew := play.Emitted{To: play.ToSeat(seat(t, 0)), Event: play.Drew{Seat: seat(t, 0), Tile: id(t, 124)}}
	assertEqual(t, "draw events", events[5:], []play.Emitted{drew, notice(1), notice(2), notice(3)})
	assertEqual(t, "phase", g.Phase(), play.PhasePlaying)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 0)))
	assertEqual(t, "live tiles", g.LiveTiles(), 69)
}

func TestDealNextRound_WhenNoRoundIsOver_ShouldBeNotAwaitedAndChangeNothing(t *testing.T) {
	g := begun(t, stagedWall(t), noStart())

	next, events, refused := g.DealNextRound()

	assertEqual(t, "refusal", refused, play.Some(refusal(play.RefusalNotAwaited, play.CodeWrongPhase)))
	assertEqual(t, "events", events, []play.Emitted(nil))
	assertSameGame(t, next, g)
}

func TestLegalActions_WhenOnTurn_ShouldOfferEveryHeldTileAndDefaultToTheDrawnOne(t *testing.T) {
	g := begun(t, stagedWall(t), noStart())

	legal := discards(append(stagedWall(t).Hands[0], id(t, 124)))
	assertEqual(t, "legal", g.LegalActions(seat(t, 0)), legal)
	fallback, ok := g.DefaultAction(seat(t, 0))
	if !ok || fallback != play.DiscardAction(id(t, 124)) {
		t.Errorf("DefaultAction = %v, %t, want discard of 124", fallback, ok)
	}
	decision, _ := g.Decision(seat(t, 0))
	assertEqual(t, "decision", decision, play.Decision{
		Seat:    seat(t, 0),
		Context: play.TurnAfterDraw{Drawn: id(t, 124)},
		Legal:   legal,
		Default: play.DiscardAction(id(t, 124)),
	})
	for _, n := range []int{1, 2, 3} {
		_, hasDefault := g.DefaultAction(seat(t, n))
		_, hasDecision := g.Decision(seat(t, n))
		if len(g.LegalActions(seat(t, n))) != 0 || hasDefault || hasDecision {
			t.Errorf("seat %d is offered actions while not awaited", n)
		}
	}
}

func TestDiscard_ShouldRemoveTheTileAndDrawForTheNextSeat(t *testing.T) {
	g := begun(t, stagedWall(t), noStart())

	g, events := script(t, g, act(seat(t, 0), play.DiscardAction(id(t, 108))))

	if containsAction(discards(g.Hand(seat(t, 0))), play.DiscardAction(id(t, 108))) || len(g.Hand(seat(t, 0))) != 13 {
		t.Errorf("hand after discard = %v", g.Hand(seat(t, 0)))
	}
	assertEqual(t, "discard", events[0], play.Emitted{To: play.ToAll(), Event: play.Discarded{
		Seat: seat(t, 0), Tile: id(t, 108),
	}})
	assertEqual(t, "next draw", events[1], play.Emitted{To: play.ToSeat(seat(t, 1)), Event: play.Drew{
		Seat: seat(t, 1), Tile: id(t, 125),
	}})
	assertEqual(t, "event count", len(events), 5)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 1)))
}

func TestDiscard_WhenItIsTheDrawnTile_ShouldBeTsumogiri(t *testing.T) {
	g := begun(t, stagedWall(t), noStart())

	_, events := script(t, g, act(seat(t, 0), play.DiscardAction(id(t, 124))))

	if discarded, ok := events[0].Event.(play.Discarded); !ok || !discarded.Tsumogiri {
		t.Errorf("first event = %+v, want a tsumogiri discard", events[0].Event)
	}
}

func TestDiscard_WhenTheTileIsNotHeld_ShouldBeNotOfferedAndChangeNothing(t *testing.T) {
	build := func() game.Game { return begun(t, stagedWall(t), noStart()) }

	assertRefused(t, build, seat(t, 0), play.DiscardAction(build().Hand(seat(t, 1))[0]),
		refusal(play.RefusalNotOffered, play.CodeTileNotHeld))
}

func TestDiscard_WhenNotTheSeatsTurn_ShouldBeNotAwaitedAndChangeNothing(t *testing.T) {
	build := func() game.Game { return begun(t, stagedWall(t), noStart()) }

	assertRefused(t, build, seat(t, 1), play.DiscardAction(build().Hand(seat(t, 1))[0]),
		refusal(play.RefusalNotAwaited, play.CodeSeatNotAwaited))
}

func TestAct_WhenTheActionHasNoKind_ShouldBeNotOfferedAndChangeNothing(t *testing.T) {
	build := func() game.Game { return begun(t, stagedWall(t), noStart()) }

	assertRefused(t, build, seat(t, 0), play.Action{}, refusal(play.RefusalNotOffered, play.CodeNotOffered))
}
