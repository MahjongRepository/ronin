package tenhoulog_test

import (
	"maps"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/tenhou/tenhoulog"
)

const (
	tenhouTsumoID  = 0
	tenhouPinfuID  = 7
	tenhouTanyaoID = 8
	tenhouIipeiID  = 9
)

func pinfuTanyaoRon() tenhoulog.Win {
	return tenhoulog.Win{
		ID: "made-up/0/0", LogID: "made-up", Aka: true, Kuitan: true,
		Who: 1, FromWho: 2,
		Closed:         []int{4, 8, 12, 20, 24, 28, 40, 44, 48, 64, 65, 92, 96, 100},
		WinTile:        12,
		DoraIndicators: []int{72},
		Fu:             30,
		Points:         2000,
		Yaku:           [][2]int{{tenhouPinfuID, 1}, {tenhouTanyaoID, 1}},
		ScoreDeltas:    []int{0, 2000, -2000, 0},
	}
}

func pinfuTanyaoTsumo() tenhoulog.Win {
	win := pinfuTanyaoRon()
	win.ID = "made-up/1/0"
	win.RoundIndex = 1
	win.Tsumo = true
	win.FromWho = 1
	win.Fu = 20
	win.Points = 2700
	win.Yaku = [][2]int{{tenhouTsumoID, 1}, {tenhouPinfuID, 1}, {tenhouTanyaoID, 1}}
	win.ScoreDeltas = []int{-1300, 2700, -700, -700}
	return win
}

func doubleRonWithHonba() []tenhoulog.Win {
	dealer := pinfuTanyaoRon()
	dealer.ID = "made-up/2/0"
	dealer.RoundIndex = 2
	dealer.Honba = 1
	dealer.Who = 0
	dealer.FromWho = 3
	dealer.Closed = []int{5, 9, 12, 21, 25, 29, 41, 45, 49, 66, 67, 93, 97, 101}
	dealer.Points = 2900
	dealer.ScoreDeltas = []int{3200, 0, 0, -3200}

	second := pinfuTanyaoRon()
	second.ID = "made-up/2/1"
	second.RoundIndex = 2
	second.Honba = 1
	second.FromWho = 3
	second.ScoreDeltas = []int{0, 2000, 0, -2000}
	return []tenhoulog.Win{dealer, second}
}

func TestCompare_WhenTheEngineScoresAsTenhouPaid_ShouldReportNothing(t *testing.T) {
	tests := []struct {
		name  string
		round []tenhoulog.Win
	}{
		{name: "ron", round: []tenhoulog.Win{pinfuTanyaoRon()}},
		{name: "tsumo", round: []tenhoulog.Win{pinfuTanyaoTsumo()}},
		{name: "double ron, honba", round: doubleRonWithHonba()},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if got := tenhoulog.Compare(tc.round); len(got) != 0 {
				t.Errorf("Compare = %v, want no mismatch", got)
			}
		})
	}
}

func TestCompare_WhenTenhouPaidOtherwise_ShouldReportEachDisagreement(t *testing.T) {
	win := pinfuTanyaoRon()
	win.Points += 100
	win.ScoreDeltas = []int{0, 0, 0, 0}
	win.Limit = 5
	win.Yaku = append(win.Yaku, [2]int{tenhouIipeiID, 1})

	got := map[tenhoulog.Check]bool{}
	for _, mismatch := range tenhoulog.Compare([]tenhoulog.Win{win}) {
		got[mismatch.Check] = true
	}

	want := map[tenhoulog.Check]bool{
		tenhoulog.CheckHanFu: true, tenhoulog.CheckYaku: true, tenhoulog.CheckLimit: true,
		tenhoulog.CheckPoints: true, tenhoulog.CheckDeltas: true,
	}
	if !maps.Equal(got, want) {
		t.Errorf("Compare reported %v, want %v", got, want)
	}
}

func TestCompare_WhenASecondRonWinnerIsSettledAlone_ShouldReportItTakingTheTable(t *testing.T) {
	round := doubleRonWithHonba()

	got := tenhoulog.Compare(round[1:])
	if len(got) == 0 || got[len(got)-1].Check != tenhoulog.CheckDeltas {
		t.Errorf("Compare = %v, want the score changes to disagree", got)
	}
}

func TestCompare_WhenTheRoundIsNoneTheEngineSettles_ShouldReportIt(t *testing.T) {
	win := pinfuTanyaoRon()
	tsumo := pinfuTanyaoTsumo()
	noAka := win
	noAka.Aka = false
	noWinTile := win
	noWinTile.WinTile = -1
	misfit := win
	misfit.Melds = []tenhoulog.Meld{{Kind: "pon", Tiles: []int{0, 4, 8}}}
	misfitTsumo := tsumo
	misfitTsumo.Melds = misfit.Melds

	tests := []struct {
		name  string
		round []tenhoulog.Win
		want  tenhoulog.Check
	}{
		{name: "no wins", round: nil, want: tenhoulog.CheckInput},
		{name: "other rules", round: []tenhoulog.Win{noAka}, want: tenhoulog.CheckInput},
		{name: "no win tile", round: []tenhoulog.Win{noWinTile}, want: tenhoulog.CheckInput},
		{name: "two tsumo", round: []tenhoulog.Win{tsumo, tsumo}, want: tenhoulog.CheckInput},
		{name: "misfit ron meld", round: []tenhoulog.Win{misfit}, want: tenhoulog.CheckScore},
		{name: "misfit tsumo meld", round: []tenhoulog.Win{misfitTsumo}, want: tenhoulog.CheckScore},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := tenhoulog.Compare(tc.round)
			if len(got) != 1 || got[0].Check != tc.want {
				t.Errorf("Compare = %v, want one %s", got, tc.want)
			}
		})
	}
}
