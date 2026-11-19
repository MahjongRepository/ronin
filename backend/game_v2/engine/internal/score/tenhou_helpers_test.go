package score_test

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/score"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	tenhouRiichi       = 1
	tenhouIppatsu      = 2
	tenhouChankan      = 3
	tenhouRinshan      = 4
	tenhouHaitei       = 5
	tenhouHoutei       = 6
	tenhouDaburuRiichi = 21
	tenhouRenhou       = 36
	tenhouTenhou       = 37
	tenhouChiihou      = 38
)

type tenhouMeld struct {
	Kind  string `json:"kind"`
	Tiles []int  `json:"tiles"`
}

type tenhouWin struct {
	ID             string       `json:"id"`
	Aka            bool         `json:"aka"`
	Kuitan         bool         `json:"kuitan"`
	RoundWind      int          `json:"round_wind"`
	SeatWind       int          `json:"seat_wind"`
	Honba          int          `json:"honba"`
	RiichiSticks   int          `json:"riichi_sticks"`
	Tsumo          bool         `json:"tsumo"`
	Closed         []int        `json:"closed"`
	Melds          []tenhouMeld `json:"melds"`
	WinTile        int          `json:"win_tile"`
	DoraIndicators []int        `json:"dora_indicators"`
	UraIndicators  []int        `json:"ura_indicators"`
	Fu             int          `json:"fu"`
	Yaku           [][2]int     `json:"yaku"`
	Yakuman        []int        `json:"yakuman"`
}

type tenhouCheck struct {
	wins       int
	hanFuWins  int
	mismatches []string
}

func checkTenhouWins(r io.Reader) (tenhouCheck, error) {
	var check tenhouCheck
	scanner := bufio.NewScanner(r)
	scanner.Buffer(make([]byte, 1<<20), 1<<20)
	for scanner.Scan() {
		var win tenhouWin
		err := json.Unmarshal(scanner.Bytes(), &win)
		if err != nil {
			return check, err
		}

		check.wins++
		if len(win.Yakuman) == 0 {
			check.hanFuWins++
		}
		mismatch := checkTenhouWin(win)
		if mismatch != "" {
			check.mismatches = append(check.mismatches, win.ID+": "+mismatch)
		}
	}
	return check, scanner.Err()
}

func checkTenhouWin(win tenhouWin) string {
	h, situation, dora, rules, err := tenhouInput(win)
	if err != nil {
		return err.Error()
	}

	value, err := score.EstimateHandValue(h, situation, dora, rules)
	if err != nil {
		return "EstimateHandValue error = " + err.Error()
	}
	if len(win.Yakuman) > 0 {
		return ""
	}

	han := 0
	for _, yaku := range win.Yaku {
		han += yaku[1]
	}
	want := play.Han{Han: han, Fu: win.Fu}
	if value.Value != want {
		return fmt.Sprintf("value = %v, want %v", value.Value, want)
	}
	return ""
}

func tenhouInput(win tenhouWin) (score.Hand, score.Situation, score.Dora, score.Rules, error) {
	aka := tile.AkaDoraDisabled
	if win.Aka {
		aka = tile.AkaDoraEnabled
	}
	closed := slices.Clone(win.Closed)
	at := slices.Index(closed, win.WinTile)
	if at < 0 {
		return score.Hand{}, score.Situation{}, score.Dora{}, score.Rules{},
			fmt.Errorf("the closed tiles hold no winning tile %d", win.WinTile)
	}
	closed = slices.Delete(closed, at, at+1)

	concealed, err := tenhouTiles(closed, aka)
	if err != nil {
		return score.Hand{}, score.Situation{}, score.Dora{}, score.Rules{}, err
	}
	winTile, err := tenhouTiles([]int{win.WinTile}, aka)
	if err != nil {
		return score.Hand{}, score.Situation{}, score.Dora{}, score.Rules{}, err
	}
	melds, err := tenhouMelds(win.Melds, aka)
	if err != nil {
		return score.Hand{}, score.Situation{}, score.Dora{}, score.Rules{}, err
	}
	indicators, err := tenhouTiles(win.DoraIndicators, aka)
	if err != nil {
		return score.Hand{}, score.Situation{}, score.Dora{}, score.Rules{}, err
	}
	uraIndicators, err := tenhouTiles(win.UraIndicators, aka)
	if err != nil {
		return score.Hand{}, score.Situation{}, score.Dora{}, score.Rules{}, err
	}
	situation, err := tenhouSituation(win)
	if err != nil {
		return score.Hand{}, score.Situation{}, score.Dora{}, score.Rules{}, err
	}

	h := score.Hand{Concealed: concealed, WinTile: winTile[0], Melds: melds}
	dora := score.Dora{Indicators: indicators, UraIndicators: uraIndicators}
	rules := score.Rules{OpenTanyao: win.Kuitan, FuForOpenPinfu: true}
	return h, situation, dora, rules, nil
}

func tenhouSituation(win tenhouWin) (score.Situation, error) {
	hasYaku := func(id int) bool {
		return slices.ContainsFunc(win.Yaku, func(yaku [2]int) bool { return yaku[0] == id })
	}
	seatWind, seatOK := tile.WindFromKind(tile.KindEast + tile.Kind(win.SeatWind))
	roundWind, roundOK := tile.WindFromKind(tile.KindEast + tile.Kind(win.RoundWind))
	if !seatOK || !roundOK {
		return score.Situation{}, fmt.Errorf("winds %d and %d", win.SeatWind, win.RoundWind)
	}

	situation := score.Situation{
		Win:          tenhouWinKind(win, hasYaku),
		SeatWind:     seatWind,
		RoundWind:    roundWind,
		Honba:        win.Honba,
		RiichiSticks: win.RiichiSticks,
		FirstTurn: slices.ContainsFunc(win.Yakuman, func(id int) bool {
			return id == tenhouTenhou || id == tenhouChiihou || id == tenhouRenhou
		}),
	}
	isDouble := hasYaku(tenhouDaburuRiichi)
	if isDouble || hasYaku(tenhouRiichi) {
		situation.Riichi = play.Some(play.Riichi{Double: isDouble, Ippatsu: hasYaku(tenhouIppatsu)})
	}
	return situation, nil
}

func tenhouWinKind(win tenhouWin, hasYaku func(int) bool) score.Win {
	switch {
	case hasYaku(tenhouRinshan):
		return score.WinRinshan
	case hasYaku(tenhouChankan):
		return score.WinChankan
	case hasYaku(tenhouHaitei):
		return score.WinHaitei
	case hasYaku(tenhouHoutei):
		return score.WinHoutei
	case win.Tsumo:
		return score.WinTsumo
	default:
		return score.WinRon
	}
}

func tenhouTiles(ids []int, aka tile.AkaDora) ([]tile.Tile, error) {
	tiles := make([]tile.Tile, 0, len(ids))
	for _, n := range ids {
		id, ok := tile.NewTileID(n)
		if !ok {
			return nil, fmt.Errorf("tile id %d", n)
		}
		tiles = append(tiles, id.Tile(aka))
	}
	return tiles, nil
}

func tenhouMelds(melds []tenhouMeld, aka tile.AkaDora) ([]meld.Meld, error) {
	parsed := make([]meld.Meld, 0, len(melds))
	for _, m := range melds {
		tiles, err := tenhouTiles(m.Tiles, aka)
		if err != nil {
			return nil, err
		}

		var made meld.Meld
		switch {
		case m.Kind == "chi" && len(tiles) == 3:
			made, err = meld.NewChi([3]tile.Tile(tiles))
		case m.Kind == "pon" && len(tiles) == 3:
			made, err = meld.NewPon([3]tile.Tile(tiles))
		case (m.Kind == "chakan" || m.Kind == "daiminkan") && len(tiles) == 4:
			made, err = meld.NewOpenKan([4]tile.Tile(tiles))
		case m.Kind == "ankan" && len(tiles) == 4:
			made, err = meld.NewClosedKan([4]tile.Tile(tiles))
		default:
			return nil, fmt.Errorf("meld %s of %d tiles", m.Kind, len(tiles))
		}
		if err != nil {
			return nil, fmt.Errorf("meld %s %v: %w", m.Kind, m.Tiles, err)
		}
		parsed = append(parsed, made)
	}
	return parsed, nil
}
