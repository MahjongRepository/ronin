package tenhoulog_test

import (
	"compress/gzip"
	"os"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/tenhoulog"
)

func readSample(t *testing.T) [][]tenhoulog.Win {
	t.Helper()
	file, err := os.Open("testdata/sample.jsonl.gz")
	if err != nil {
		t.Fatalf("open the sample: %v", err)
	}
	t.Cleanup(func() {
		closeErr := file.Close()
		if closeErr != nil {
			t.Errorf("close the sample: %v", closeErr)
		}
	})
	compressed, err := gzip.NewReader(file)
	if err != nil {
		t.Fatalf("read the sample: %v", err)
	}

	var rounds [][]tenhoulog.Win
	for round, readErr := range tenhoulog.Rounds(compressed) {
		if readErr != nil {
			t.Fatalf("Rounds error = %v", readErr)
		}
		rounds = append(rounds, round)
	}
	return rounds
}

func firstRound(t *testing.T, rounds [][]tenhoulog.Win, match func([]tenhoulog.Win) bool) []tenhoulog.Win {
	t.Helper()
	for _, round := range rounds {
		if match(round) {
			return round
		}
	}
	t.Fatal("the sample holds no such round")
	return nil
}

func TestCompare_WhenTheSampleIsSettled_ShouldAgreeWithTenhouOnEveryWin(t *testing.T) {
	rounds := readSample(t)

	var wins, yakuman, pao, doubleRons int
	for _, round := range rounds {
		wins += len(round)
		if len(round) > 1 {
			doubleRons++
		}
		for _, win := range round {
			if len(win.Yakuman) > 0 {
				yakuman++
			}
			if win.Pao != nil {
				pao++
			}
		}
		for _, mismatch := range tenhoulog.Compare(round) {
			t.Errorf("%s %s: %s", mismatch.Check, mismatch.WinID, mismatch.Detail)
		}
	}
	if wins != 3588 || yakuman < 300 || pao < 30 || doubleRons < 60 {
		t.Errorf("the sample holds %d wins, %d yakuman, %d pao, %d double rons; want 3588, at least 300, 30 and 60",
			wins, yakuman, pao, doubleRons)
	}
}

func TestCompare_WhenTenhouPaidOtherwise_ShouldReportEachDisagreement(t *testing.T) {
	win := readSample(t)[0][0]
	win.Points += 100
	win.ScoreDeltas = []int{0, 0, 0, 0}
	win.Limit = 5
	win.Yaku = append(win.Yaku, [2]int{7, 1})

	got := map[tenhoulog.Check]bool{}
	for _, mismatch := range tenhoulog.Compare([]tenhoulog.Win{win}) {
		got[mismatch.Check] = true
	}
	want := map[tenhoulog.Check]bool{
		tenhoulog.CheckHanFu: true, tenhoulog.CheckYaku: true, tenhoulog.CheckLimit: true,
		tenhoulog.CheckPoints: true, tenhoulog.CheckDeltas: true,
	}
	if len(got) != len(want) {
		t.Errorf("Compare reported %v, want %v", got, want)
	}
	for check := range want {
		if !got[check] {
			t.Errorf("Compare reported %v, want %v", got, want)
		}
	}
}

func TestCompare_WhenASecondRonWinnerIsSettledAlone_ShouldReportItTakingTheTable(t *testing.T) {
	round := firstRound(t, readSample(t), func(round []tenhoulog.Win) bool {
		return len(round) > 1 && round[1].Honba > 0
	})

	got := tenhoulog.Compare(round[1:])
	if len(got) == 0 || got[len(got)-1].Check != tenhoulog.CheckDeltas {
		t.Errorf("Compare = %v, want the score changes to disagree", got)
	}
}

func TestCompare_WhenTheRoundIsNoneTheEngineSettles_ShouldReportIt(t *testing.T) {
	rounds := readSample(t)
	win := rounds[0][0]
	tsumo := firstRound(t, rounds, func(round []tenhoulog.Win) bool { return round[0].Tsumo })[0]
	noAka := win
	noAka.Aka = false
	noWinTile := win
	noWinTile.WinTile = -1
	misfit := win
	misfit.Melds = []tenhoulog.Meld{{Kind: "pon", Tiles: []int{0, 4, 8}}}
	misfitTsumo := tsumo
	misfitTsumo.Melds = misfit.Melds

	for name, c := range map[string]struct {
		round []tenhoulog.Win
		want  tenhoulog.Check
	}{
		"no wins":           {nil, tenhoulog.CheckInput},
		"other rules":       {[]tenhoulog.Win{noAka}, tenhoulog.CheckInput},
		"no win tile":       {[]tenhoulog.Win{noWinTile}, tenhoulog.CheckInput},
		"two tsumo":         {[]tenhoulog.Win{tsumo, tsumo}, tenhoulog.CheckInput},
		"misfit ron meld":   {[]tenhoulog.Win{misfit}, tenhoulog.CheckScore},
		"misfit tsumo meld": {[]tenhoulog.Win{misfitTsumo}, tenhoulog.CheckScore},
	} {
		got := tenhoulog.Compare(c.round)
		if len(got) != 1 || got[0].Check != c.want {
			t.Errorf("%s: Compare = %v, want one %s", name, got, c.want)
		}
	}
}
