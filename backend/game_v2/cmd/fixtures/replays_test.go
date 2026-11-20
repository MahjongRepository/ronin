package main

import (
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func TestStagedGame_WhenAStagedDrawNamesAnotherSeat_ShouldFailNamingTheDraw(t *testing.T) {
	var s staging
	misseated := kyuushuWall(&s)
	misseated.draws[1] = s.draw(3, misseated.draws[1].id)

	_, err := playStaged(&s, staged("replay-check", misseated), endsAt(aborted(wire.AbortNineTerminals)),
		func(g *stagedGame) {
			g.tsumogiri(0)
			g.kyuushu(1)
		})

	assertFailureNames(t, err, "seat 1 drew staged draw 1 (staged for seat 3)")
}

func TestCutAfter_WhenTheEventOpensACall_ShouldKeepTheWholeCall(t *testing.T) {
	played, err := kansFixture()
	if err != nil {
		t.Fatalf("kans error = %v", err)
	}

	cut, err := cutAfter("probe", played, wire.EventDoraRevealed, -1)
	if err != nil {
		t.Fatalf("cutAfter error = %v", err)
	}

	var tail []int
	for _, record := range cut.records[len(cut.records)-3:] {
		event, _ := intOf(record, wire.KeyEventType)
		tail = append(tail, event)
	}
	want := []int{int(wire.EventMeld), int(wire.EventDoraRevealed), int(wire.EventDraw)}
	if diff := cmp.Diff(want, tail); diff != "" {
		t.Errorf("the cut's last records (-want +got):\n%s", diff)
	}
}
