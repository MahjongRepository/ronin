package seam_test

import (
	"encoding/binary"
	"slices"
	"strconv"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	selfPlayGames    = 32
	selfPlayMaxSteps = 50000
)

func selfPlaySeed(game uint64) engine.Seed {
	var seed engine.Seed
	for i := range seed {
		seed[i] = 0x5a
	}
	binary.LittleEndian.PutUint64(seed[:8], game)
	return seed
}

func selfPlayAgents(game uint64) agents {
	var seated agents
	for i := range seated {
		at := uint64(i)
		if game>>at&1 == 0 {
			seated[i] = newRandomLegal(game*tile.SeatCount + at)
		} else {
			seated[i] = tsumogiri{}
		}
	}
	return seated
}

func TestPlayGameChecked_WhenRandomAndTsumogiriAgentsPlaySeededHanchans_ShouldKeepEveryInvariantToTheEnd(t *testing.T) {
	for game := range uint64(selfPlayGames) {
		t.Run(strconv.FormatUint(game, 10), func(t *testing.T) {
			t.Parallel()
			seed := selfPlaySeed(game)
			g, initial := newGame(t, engine.Setup{Walls: play.Seeded{Seed: seed}})

			standings, err := playGameChecked(&g, initial, selfPlayAgents(game), noSink{}, selfPlayMaxSteps)
			if err != nil {
				t.Fatalf("seed %v: %v", seed, err)
			}

			assertEqual[play.Awaiting](t, "awaiting", g.Awaiting(), play.AwaitingGameOver{})
			assertEqual(t, "final score total", scoreTotal(standings.Scores), tablePoints)
		})
	}
}

type fixedScenario struct {
	t    *testing.T
	game engine.Game
}

func (s *fixedScenario) act(at int, action play.Action) []play.Emitted {
	s.t.Helper()
	var events []play.Emitted
	s.game, events = act(s.t, s.game, seat(s.t, at), action)
	s.checkInvariants()
	return events
}

func (s *fixedScenario) deal() play.RoundHeader {
	s.t.Helper()
	s.game, _ = dealNextRound(s.t, s.game)
	s.checkInvariants()
	return s.game.View(seat(s.t, 0)).Record.Header
}

func (s *fixedScenario) checkInvariants() {
	s.t.Helper()
	if err := s.game.CheckInvariants(); err != nil {
		s.t.Fatalf("CheckInvariants error = %v", err)
	}
}

func ronOf(t *testing.T, events []play.Emitted) (winners []tile.Seat, discarder tile.Seat, changes [tile.SeatCount]int) {
	t.Helper()
	result := roundResult(t, events)
	ron, ok := result.(play.Ron)
	if !ok {
		t.Fatalf("result = %#v, want a ron", result)
	}
	for _, win := range ron.Wins {
		winners = append(winners, win.Winner)
	}
	return winners, ron.Discarder, result.TotalScoreChanges()
}

func TestGame_WhenFixedWallsPlayARiichiARonAndADealerRenchan_ShouldKeepEveryInvariant(t *testing.T) {
	riichiThenRon := startWall{
		hands: [tile.SeatCount][]tile.TileID{
			copies(t, 0, "123456789m1234p"),
			copies(t, 1, "234567m234p678s5p"),
			junk(t, 2),
			junk(t, 3),
		},
		draws: []tile.TileID{copyOf(t, 0, "7z"), copyOf(t, 0, "1z"), copyOf(t, 0, "2z"), copyOf(t, 0, "3z"), copyOf(t, 2, "5p")},
	}
	dealerRon := startWall{
		hands: [tile.SeatCount][]tile.TileID{junk(t, 1), copies(t, 0, "234567m234p678s5p"), junk(t, 2), junk(t, 3)},
		draws: []tile.TileID{copyOf(t, 0, "7z"), copyOf(t, 1, "5p")},
	}
	noten := startWall{hands: [tile.SeatCount][]tile.TileID{junk(t, 0), junk(t, 1), junk(t, 2), junk(t, 3)}}
	g, _ := newGame(t, engine.Setup{Walls: play.Fixed{Walls: [][tile.TileIDCount]tile.TileID{
		riichiThenRon.tiles(t, seat(t, 0)),
		dealerRon.tiles(t, seat(t, 1)),
		noten.tiles(t, seat(t, 1)),
	}}})
	s := &fixedScenario{t: t, game: g}
	s.checkInvariants()

	riichi := s.act(0, play.RiichiAction(copyOf(t, 0, "7z")))
	deposited := play.RiichiDeposited{Seat: seat(t, 0), Score: startingScore - riichiCost, RiichiSticks: 1}
	if !slices.ContainsFunc(riichi, func(e play.Emitted) bool { return e.Event == play.Event(deposited) }) {
		t.Errorf("riichi events = %#v, want %#v", riichi, deposited)
	}
	record := s.game.View(seat(t, 0)).Record
	assertEqual(t, "sticks and score after the riichi", [2]int{record.RiichiSticks, record.Players[0].Score}, [2]int{1, startingScore - riichiCost})
	for at, wind := range []string{"1z", "2z", "3z"} {
		s.act(at+1, play.DiscardAction(copyOf(t, 0, wind)))
	}

	s.act(0, play.DiscardAction(copyOf(t, 2, "5p")))
	winners, discarder, changes := ronOf(t, s.act(1, play.RonAction()))
	assertEqual(t, "first ron", [2]any{winners, discarder}, [2]any{[]tile.Seat{seat(t, 1)}, seat(t, 0)})
	assertEqual(t, "first ron changes", changes, [tile.SeatCount]int{changes[0], riichiStickPoints - changes[0], 0, 0})
	if changes[0] >= 0 {
		t.Errorf("the discarder's change is %d, want a loss", changes[0])
	}
	record = s.game.View(seat(t, 0)).Record
	assertEqual(t, "sticks and phase after the ron", [2]any{record.RiichiSticks, record.Phase}, [2]any{0, play.PhaseRoundOver})
	header := s.deal()
	assertEqual(t, "second round", [3]any{header.Dealer, header.Honba, header.RoundNumber}, [3]any{seat(t, 1), 0, uint32(1)})

	s.act(1, play.DiscardAction(copyOf(t, 0, "7z")))
	s.act(2, play.DiscardAction(copyOf(t, 1, "5p")))
	assertEqual[play.Awaiting](t, "callers", s.game.Awaiting(), play.AwaitingCall{Seats: []tile.Seat{seat(t, 1), seat(t, 3)}})
	s.act(3, play.PassAction())
	winners, discarder, changes = ronOf(t, s.act(1, play.RonAction()))
	assertEqual(t, "dealer ron", [2]any{winners, discarder}, [2]any{[]tile.Seat{seat(t, 1)}, seat(t, 2)})
	assertEqual(t, "dealer ron change total", scoreTotal(changes), 0)
	assertEqual(t, "phase", s.game.View(seat(t, 0)).Record.Phase, play.PhaseRoundOver)
	header = s.deal()
	assertEqual(t, "third round", [3]any{header.Dealer, header.Honba, header.RoundNumber}, [3]any{seat(t, 1), 1, uint32(2)})
}
