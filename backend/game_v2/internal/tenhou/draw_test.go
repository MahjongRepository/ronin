package tenhou

import (
	"slices"
	"strings"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replay"
)

func kyuushuGame(t *testing.T) (stagedWall, []replay.SeatAction) {
	t.Helper()
	wall := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			copies(t, 0, "19m19p19s123z2345m"),
			copies(t, 1, "2468m2468p2468s5z"),
			copies(t, 2, "2468m2468p2468s5z"),
			copies(t, 3, "2468m2468p2468s5z"),
		},
		draws: copies(t, 0, "5z"),
	}
	return wall, []replay.SeatAction{act(t, dealer, play.KyuushuAction())}
}

func fourRiichiGame(t *testing.T) (stagedWall, []replay.SeatAction) {
	t.Helper()
	winds := copies(t, 0, "1234z")
	wall := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			copies(t, 0, "123456789m123p9p"),
			copies(t, 1, "123456789m123s9s"),
			copies(t, 2, "123456789m456p7z"),
			copies(t, 3, "123456789m456s5z"),
		},
		draws: winds,
	}
	var actions []replay.SeatAction
	for s, wind := range winds {
		actions = append(actions, act(t, s, play.RiichiAction(wind)))
	}

	return wall, actions
}

func tripleRonGame(t *testing.T) (stagedWall, []replay.SeatAction) {
	t.Helper()
	pon3p, added3p := copyOf(t, 2, "3p"), copyOf(t, 3, "3p")
	ponDiscard, westDiscard := copyOf(t, 0, "4z"), copyOf(t, 0, "3z")
	souths, easts := copies(t, 1, "222z"), copies(t, 1, "11z")
	ronDiscard := copyOf(t, 3, "5m")
	wall := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			join([]tile.TileID{pon3p}, copies(t, 2, "1357m"), copies(t, 3, "9m"), copies(t, 1, "19s"),
				copies(t, 2, "9p"), copies(t, 1, "67z"), copies(t, 2, "67z")),
			join(copies(t, 0, "33p123456789m3z"), []tile.TileID{ponDiscard}),
			copies(t, 1, "22456p234678s34m"),
			join(copies(t, 2, "456p345678s"), copies(t, 0, "88p"), copies(t, 1, "67m")),
		},
		draws:   join(souths, copies(t, 1, "4z"), []tile.TileID{added3p}, easts, []tile.TileID{ronDiscard}),
		rinshan: copies(t, 1, "5m"),
	}
	actions := []replay.SeatAction{
		act(t, dealer, play.DiscardAction(pon3p)),
		act(t, kanCaller, play.PonAction([2]tile.TileID(copies(t, 0, "33p")))),
		act(t, kanCaller, play.DiscardAction(ponDiscard)),
		act(t, 2, play.DiscardAction(souths[1])),
		act(t, 3, play.DiscardAction(souths[2])),
		act(t, dealer, play.DiscardAction(copyOf(t, 1, "4z"))),
		act(t, kanCaller, play.KanAction(play.KanAdded, added3p)),
		act(t, kanCaller, play.DiscardAction(westDiscard)),
		act(t, 2, play.DiscardAction(easts[0])),
		act(t, 3, play.DiscardAction(easts[1])),
		act(t, dealer, play.DiscardAction(ronDiscard)),
		act(t, 1, play.RonAction()),
		act(t, 2, play.RonAction()),
		act(t, 3, play.RonAction()),
	}
	return wall, actions
}

func TestConvert_WhenARoundAborts_ShouldRevealTheHandsTenhouShows(t *testing.T) {
	tests := []struct {
		name    string
		game    func(*testing.T) (stagedWall, []replay.SeatAction)
		draw    string
		riichis []string
	}{
		{
			name: "kyuushu kyuuhai shows the declarer",
			game: kyuushuGame,
			draw: `<RYUUKYOKU type="yao9" ba="0,0" sc="250,0,250,0,250,0,250,0" hai0="0,4,8,12,16,32,36,68,72,104,108,112,116,124"`,
		},
		{
			name: "four riichi shows every hand",
			game: fourRiichiGame,
			draw: `<RYUUKYOKU type="reach4" ba="0,4" sc="240,0,240,0,240,0,240,0"` +
				` hai0="0,4,8,12,16,20,24,28,32,36,40,44,68" hai1="1,5,9,13,17,21,25,29,33,73,77,81,105"` +
				` hai2="2,6,10,14,18,22,26,30,34,50,54,58,134" hai3="3,7,11,15,19,23,27,31,35,87,91,95,127"`,
			riichis: []string{
				`<REACH who="0" ten="240,250,250,250" step="2"/>`,
				`<REACH who="1" ten="240,240,250,250" step="2"/>`,
				`<REACH who="2" ten="240,240,240,250" step="2"/>`,
				`<REACH who="3" ten="240,240,240,240" step="2"/>`,
			},
		},
		{
			name: "triple ron shows the declarers without their meld tiles",
			game: tripleRonGame,
			draw: `<RYUUKYOKU type="ron3" ba="0,0" sc="250,0,250,0,250,0,250,0" hai1="0,4,8,12,16,17,20,24,28,32"` +
				` hai2="9,13,41,42,49,53,57,77,81,85,93,97,101" hai3="21,25,50,54,58,64,65,82,86,90,94,98,102"`,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			wall, actions := tc.game(t)
			xml := converted(t, playedReplay(t, stagedSetup(t, wall, play.Option[play.StartPosition]{}), actions))

			if got := tags(xml, ryuukyokuTags); len(got) != 1 || !strings.HasPrefix(got[0], tc.draw+` owari="`) {
				t.Errorf("RYUUKYOKU = %q, want %q and the owari", got, tc.draw)
			}

			if got := tags(xml, reachDepositTags); !slices.Equal(got, tc.riichis) {
				t.Errorf("riichi deposits = %q, want %q", got, tc.riichis)
			}
		})
	}
}

const nagashiSeat = 1

func nagashiWall(t *testing.T) stagedWall {
	t.Helper()
	var terminals, simples []tile.TileID
	for _, id := range tile.AllTileIDs() {
		if id.Kind().IsTerminalOrHonor() {
			terminals = append(terminals, id)
		} else {
			simples = append(simples, id)
		}
	}

	var w stagedWall
	var dealt []tile.TileID
	for s := range w.hands {
		for i := s; len(w.hands[s]) < handSize; i += tile.SeatCount {
			w.hands[s] = append(w.hands[s], simples[i])
		}

		dealt = append(dealt, w.hands[s]...)
	}

	others := slices.DeleteFunc(slices.Clone(simples), func(id tile.TileID) bool { return slices.Contains(dealt, id) })
	reversed := slices.Clone(terminals)
	slices.Reverse(reversed)
	others = append(others, reversed...)
	nagashiDraws := terminals
	for i := range liveWallSize - len(dealt) {
		if i%tile.SeatCount == nagashiSeat {
			w.draws, nagashiDraws = append(w.draws, nagashiDraws[0]), nagashiDraws[1:]
		} else {
			w.draws, others = append(w.draws, others[0]), others[1:]
		}
	}

	return w
}

func TestConvert_WhenTobiFollowsANagashiMangan_ShouldWriteAnNMRyuukyokuCarryingTheOwari(t *testing.T) {
	wall := nagashiWall(t)
	var actions []replay.SeatAction
	for i, drawn := range wall.draws {
		actions = append(actions, act(t, i%tile.SeatCount, play.DiscardAction(drawn)))
	}

	start := play.Some(play.StartPosition{Scores: [tile.SeatCount]int{1000, 97000, 1000, 1000}})
	xml := converted(t, playedReplay(t, stagedSetup(t, wall, start), actions))

	want := `<RYUUKYOKU type="nm" ba="0,0" sc="10,-40,970,80,10,-20,10,-20"` +
		` hai0="4,8,12,16,20,24,28,40,44,48,52,56,60" hai1="5,9,13,17,21,25,29,41,45,49,53,57,61"` +
		` hai2="6,10,14,18,22,26,30,42,46,50,54,58,62" hai3="7,11,15,19,23,27,31,43,47,51,55,59,63"` +
		` owari="-30,-53.0,1050,115.0,-10,-21.0,-10,-41.0" />`
	if got := tags(xml, ryuukyokuTags); !slices.Equal(got, []string{want}) {
		t.Errorf("RYUUKYOKU = %q, want %q", got, want)
	}
}
