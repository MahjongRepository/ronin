package tenhou

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replay"
)

const (
	dealer        = 0
	dragonCaller  = 1
	dragonFeeder  = 2
	sou9Discarder = 3
	kanCaller     = 1
)

func daisangenRonReplay(t *testing.T) []byte {
	t.Helper()
	dragons := copies(t, 2, "567z")
	callerDiscards := copies(t, 0, "123z")
	north, sou9 := copyOf(t, 0, "4z"), copyOf(t, 1, "9s")
	wall := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			join(dragons[:1], copies(t, 1, "123456789m123p")),
			join(copies(t, 0, "556677z123m9s"), callerDiscards),
			join(dragons[1:], copies(t, 2, "2468m2468p246s")),
			join(copies(t, 2, "1357m1357p1357s"), copies(t, 3, "9m")),
		},
		draws: join(copies(t, 2, "9s"), copies(t, 1, "99p"), []tile.TileID{north, sou9}),
	}

	feeders := []int{dealer, dragonFeeder, dragonFeeder}
	var actions []replay.SeatAction
	for i, dragon := range dragons {
		pair := copies(t, 0, []string{"55z", "66z", "77z"}[i])
		actions = append(actions,
			act(t, feeders[i], play.DiscardAction(dragon)),
			act(t, dragonCaller, play.PonAction([2]tile.TileID(pair))),
			act(t, dragonCaller, play.DiscardAction(callerDiscards[i])))
	}

	actions = append(actions,
		act(t, dragonFeeder, play.DiscardAction(north)),
		act(t, sou9Discarder, play.DiscardAction(sou9)),
		act(t, dealer, play.RonAction()),
		act(t, dragonCaller, play.RonAction()))
	start := play.Some(play.StartPosition{
		Scores: [tile.SeatCount]int{25000, 25000, 25000, 24000}, Honba: 1, RiichiSticks: 1,
	})
	return playedReplay(t, stagedSetup(t, wall, start), actions)
}

func TestConvert_WhenADaisangenDoubleRonFollowsALiablePon_ShouldWriteEachWinFromTheScoresTheOneBeforeLeft(t *testing.T) {
	xml := converted(t, daisangenRonReplay(t))

	got := tags(xml, agariTags)
	want := []string{
		`<AGARI ba="1,1" hai="1,5,9,13,17,21,25,29,33,37,41,45,105,106" machi="105" ten="40,3900,0" yaku="24,2"` +
			` doraHai="113" who="0" fromWho="3" sc="250,52,250,0,250,0,240,-42" />`,
		`<AGARI ba="1,0" hai="0,4,8,104,105" m="51817,50281,48747" machi="105" ten="40,32000,5" yakuman="39"` +
			` doraHai="113" who="1" fromWho="3" paoWho="2" sc="302,0,250,320,250,-160,198,-160"` +
			` owari="302,10.2,570,67.0,90,-31.0,38,-46.2" />`,
	}
	if !slices.Equal(got, want) {
		t.Errorf("AGARI tags =\n%q\nwant\n%q", got, want)
	}
}

func TestConvert_WhenAnAddedKanCallerWinsOnTheRinshanTile_ShouldListOnlyTheKanAmongItsMelds(t *testing.T) {
	pon3p, added3p := copyOf(t, 2, "3p"), copyOf(t, 3, "3p")
	ponDiscard, west := copyOf(t, 0, "4z"), copyOf(t, 1, "3z")
	souths := copies(t, 1, "222z")
	wall := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			join([]tile.TileID{pon3p}, copies(t, 1, "1357m1357s1579p")),
			join(copies(t, 0, "33p123456789m3z"), []tile.TileID{ponDiscard}),
			join(copies(t, 2, "2468m2468s2468p"), copies(t, 2, "7z")),
			join(copies(t, 3, "2468m2468s2468p"), copies(t, 3, "7z")),
		},
		draws:   join(souths, copies(t, 1, "4z"), []tile.TileID{added3p}),
		rinshan: []tile.TileID{west},
	}
	actions := []replay.SeatAction{
		act(t, dealer, play.DiscardAction(pon3p)),
		act(t, kanCaller, play.PonAction([2]tile.TileID(copies(t, 0, "33p")))),
		act(t, kanCaller, play.DiscardAction(ponDiscard)),
		act(t, 2, play.DiscardAction(souths[1])),
		act(t, 3, play.DiscardAction(souths[2])),
		act(t, dealer, play.DiscardAction(copyOf(t, 1, "4z"))),
		act(t, kanCaller, play.KanAction(play.KanAdded, added3p)),
		act(t, kanCaller, play.TsumoAction()),
	}

	xml := converted(t, playedReplay(t, stagedSetup(t, wall, play.Option[play.StartPosition]{}), actions))
	if got := tags(xml, callTags); !slices.Equal(got, []string{`<N who="1" m="18027" />`, `<N who="1" m="18035" />`}) {
		t.Errorf("N tags = %q, want the pon then its added kan", got)
	}

	agari := `<AGARI ba="0,0" hai="0,4,8,12,16,20,24,28,32,116,117" m="18035" machi="117"`
	if got := tags(xml, agariMachiTags); !slices.Equal(got, []string{agari}) {
		t.Errorf("AGARI = %q, want %q", got, agari)
	}
}
