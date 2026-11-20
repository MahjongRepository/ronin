package tenhou

import (
	"regexp"
	"slices"
	"strconv"
	"strings"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replay"
)

func defaultActionGame(t *testing.T, seed engine.Seed) []replay.Step {
	t.Helper()
	g, events, err := engine.NewGame(engine.Setup{Walls: play.Seeded{Seed: seed}})
	if err != nil {
		t.Fatalf("NewGame error = %v", err)
	}
	steps := []replay.Step{{Events: events, Game: g}}
	for {
		var refusal play.Option[play.Refusal]
		switch awaiting := g.Awaiting().(type) {
		case play.AwaitingGameOver:
			return steps
		case play.AwaitingRoundOver:
			g, events, refusal = g.DealNextRound()
		case play.AwaitingDealt:
			g, events, refusal = g.Begin()
		case play.AwaitingTurn:
			g, events, refusal = actDefault(t, g, awaiting.Seat)
		case play.AwaitingCall:
			g, events, refusal = actDefault(t, g, awaiting.Seats[0])
		}
		if refusal.OK {
			t.Fatalf("the engine refused: %+v", refusal.Value)
		}
		steps = append(steps, replay.Step{Events: events, Game: g})
	}
}

func actDefault(t *testing.T, g engine.Game, s tile.Seat) (engine.Game, []play.Emitted, play.Option[play.Refusal]) {
	t.Helper()
	action, ok := g.DefaultAction(s)
	if !ok {
		t.Fatalf("seat %d has no default action", s.Index())
	}
	return g.Act(s, action)
}

func TestConvert_WhenTheFirstDealerIsNotSeat0_ShouldSeatThePlayersFromItAndCountRoundsFrom0(t *testing.T) {
	seed := engine.Seed{0x5a, 17}
	firstDealer, _, _ := engine.FirstDealer(seed)
	if firstDealer.Index() != 1 {
		t.Fatalf("seed's first dealer = %d, want 1", firstDealer.Index())
	}

	xml := converted(t, recordedReplay(t, seed, defaultActionGame(t, seed)))

	if got := tags(xml, `<UN n0="\w+" n1="\w+" n2="\w+" n3="\w+"`); !slices.Equal(got, []string{`<UN n0="P1" n1="P2" n2="P3" n3="P0"`}) {
		t.Errorf("UN = %q, want the players from the first dealer", got)
	}
	var want [][]string
	for round := range 12 {
		counter := strconv.Itoa(round)
		want = append(want, []string{counter, counter, strconv.Itoa(round % tile.SeatCount)})
	}
	var got [][]string
	for _, init := range regexp.MustCompile(`<INIT seed="(\d+),(\d+),[^>]* oya="(\d)"`).FindAllStringSubmatch(xml, -1) {
		got = append(got, init[1:])
	}
	if !slices.EqualFunc(got, want, slices.Equal) {
		t.Errorf("INIT round counters, honba and dealers = %q, want %q", got, want)
	}
	if got := tags(xml, `<TAIKYOKU oya="\d"/><INIT [^>]*/><T\d+/>`); len(got) != 1 || !strings.HasPrefix(got[0], `<TAIKYOKU oya="0"/>`) {
		t.Errorf("game start = %q, want seat 0 to deal and draw first", got)
	}
	owari := `<RYUUKYOKU ba="11,0" sc="250,0,250,0,250,0,250,0" owari="250,35.0,250,5.0,250,-15.0,250,-25.0" /></mjloggm>`
	if !strings.HasSuffix(xml, owari) {
		t.Errorf("log ends %q, want %q", xml[max(0, len(xml)-len(owari)):], owari)
	}
}
