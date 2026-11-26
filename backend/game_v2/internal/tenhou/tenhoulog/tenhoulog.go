package tenhoulog

import (
	"bufio"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"iter"
	"slices"
	"strings"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/tenhou"
)

const maxLineBytes = 1 << 20

// Meld is a declared meld of a Win: its kind, chi, pon, daiminkan, chakan or ankan, and its tile
// ids.
type Meld struct {
	Kind  string `json:"kind"`
	Tiles []int  `json:"tiles"`
}

type Win struct {
	ID             string   `json:"id"`
	LogID          string   `json:"log_id"`
	RoundIndex     int      `json:"round_index"`
	Aka            bool     `json:"aka"`
	Kuitan         bool     `json:"kuitan"`
	RoundWind      int      `json:"round_wind"`
	Honba          int      `json:"honba"`
	RiichiSticks   int      `json:"riichi_sticks"`
	Dealer         int      `json:"dealer"`
	Who            int      `json:"who"`
	FromWho        int      `json:"from_who"`
	Tsumo          bool     `json:"tsumo"`
	Closed         []int    `json:"closed"`
	Melds          []Meld   `json:"melds"`
	WinTile        int      `json:"win_tile"`
	DoraIndicators []int    `json:"dora_indicators"`
	UraIndicators  []int    `json:"ura_indicators"`
	Fu             int      `json:"fu"`
	Points         int      `json:"points"`
	Limit          int      `json:"limit"`
	Yaku           [][2]int `json:"yaku"`
	Yakuman        []int    `json:"yakuman"`
	Pao            *int     `json:"pao"`
	ScoreDeltas    []int    `json:"score_deltas"`
	IsFirstAgari   bool     `json:"is_first_agari"`
}

// Check names what a Mismatch compares.
type Check string

const (
	CheckInput  Check = "input"
	CheckScore  Check = "score"
	CheckHanFu  Check = "han-fu"
	CheckYaku   Check = "yaku"
	CheckLimit  Check = "limit"
	CheckPoints Check = "points"
	CheckDeltas Check = "deltas"
)

// Mismatch is one way the engine disagrees with Tenhou on the win WinID names, or on every win
// of a round it could not settle, their ids joined by commas.
type Mismatch struct {
	WinID  string
	Check  Check
	Detail string
}

// Wins reads the Wins of a shard, one JSON object per line, stopping at the first line it cannot
// decode, which it yields with its error.
func Wins(r io.Reader) iter.Seq2[Win, error] {
	return func(yield func(Win, error) bool) {
		scanner := bufio.NewScanner(r)
		scanner.Buffer(make([]byte, maxLineBytes), maxLineBytes)
		for scanner.Scan() {
			var win Win
			err := json.Unmarshal(scanner.Bytes(), &win)
			if err != nil {
				yield(Win{}, err)
				return
			}

			if !yield(win, nil) {
				return
			}
		}

		if err := scanner.Err(); err != nil {
			yield(Win{}, err)
		}
	}
}

// Rounds groups the Wins of Wins(r) by round: each yield holds the consecutive wins of one log's
// round, two for a double ron. A read error is yielded with no wins and ends the rounds.
func Rounds(r io.Reader) iter.Seq2[[]Win, error] {
	return func(yield func([]Win, error) bool) {
		var round []Win
		for win, err := range Wins(r) {
			if err != nil {
				yield(nil, err)
				return
			}

			if len(round) > 0 && (win.LogID != round[0].LogID || win.RoundIndex != round[0].RoundIndex) {
				if !yield(round, nil) {
					return
				}

				round = nil
			}

			round = append(round, win)
		}

		if len(round) > 0 {
			yield(round, nil)
		}
	}
}

func Compare(round []Win) []Mismatch {
	ids := make([]string, len(round))
	for i, win := range round {
		ids[i] = win.ID
	}

	failed := func(check Check, err error) []Mismatch {
		return []Mismatch{{WinID: strings.Join(ids, ","), Check: check, Detail: err.Error()}}
	}

	settled, err := settle(round)
	if errors.Is(err, errInput) {
		return failed(CheckInput, err)
	}

	if err != nil {
		return failed(CheckScore, err)
	}

	var mismatches []Mismatch
	for i, win := range round {
		mismatches = append(mismatches, compareWin(win, settled[i])...)
	}

	return mismatches
}

var errInput = errors.New("not a round the engine takes")

func settle(round []Win) ([]engine.SettledWin, error) {
	if len(round) == 0 {
		return nil, fmt.Errorf("no wins: %w", errInput)
	}

	first := round[0]
	table, err := tableOf(first)
	if err != nil {
		return nil, err
	}

	hands := make([]engine.WinningHand, 0, len(round))
	for _, win := range round {
		hand, handErr := winningHand(win)
		if handErr != nil {
			return nil, fmt.Errorf("win %s: %w: %w", win.ID, handErr, errInput)
		}

		hands = append(hands, hand)
	}

	if !first.Tsumo {
		discarder, ok := tile.NewSeat(first.FromWho)
		if !ok {
			return nil, fmt.Errorf("discarder %d: %w", first.FromWho, errInput)
		}

		return engine.SettleRon(table, discarder, hands)
	}

	if len(hands) != 1 {
		return nil, fmt.Errorf("a tsumo with %d wins: %w", len(hands), errInput)
	}

	settled, err := engine.SettleTsumo(table, hands[0])
	return []engine.SettledWin{settled}, err
}

func tableOf(win Win) (engine.Table, error) {
	dealer, dealerOK := tile.NewSeat(win.Dealer)
	roundWind, windOK := tile.WindFromKind(tile.KindEast + tile.Kind(win.RoundWind))
	if !dealerOK || !windOK {
		return engine.Table{}, fmt.Errorf("dealer %d, round wind %d: %w", win.Dealer, win.RoundWind, errInput)
	}

	return engine.Table{Dealer: dealer, RoundWind: roundWind, Honba: win.Honba, RiichiSticks: win.RiichiSticks}, nil
}

func compareWin(win Win, settled engine.SettledWin) []Mismatch {
	value := settled.Value
	var mismatches []Mismatch
	add := func(check Check, format string, args ...any) {
		mismatches = append(mismatches, Mismatch{WinID: win.ID, Check: check, Detail: fmt.Sprintf(format, args...)})
	}

	if want, ok := hanFuOf(win); ok && value.Value != want {
		add(CheckHanFu, "value = %v, want %v", value.Value, want)
	}

	if got, want := yakuOf(value), wantYaku(win); !slices.Equal(got, want) {
		add(CheckYaku, "yaku = %v, want %v", got, want)
	}

	if got := limitCodeOf(value); got != win.Limit {
		add(CheckLimit, "limit = %d, want %d", got, win.Limit)
	}

	if got := value.Payment.Sum(); got != win.Points {
		add(CheckPoints, "points = %d, want %d", got, win.Points)
	}

	if got := settled.ScoreChanges[:]; !slices.Equal(got, win.ScoreDeltas) {
		add(CheckDeltas, "deltas = %v, want %v (pao %t)", got, win.ScoreDeltas, win.Pao != nil)
	}

	return mismatches
}

func winningHand(win Win) (engine.WinningHand, error) {
	if !win.Aka || !win.Kuitan {
		return engine.WinningHand{}, fmt.Errorf("aka %t and kuitan %t, the engine plays with both", win.Aka, win.Kuitan)
	}

	seat, ok := tile.NewSeat(win.Who)
	if !ok {
		return engine.WinningHand{}, fmt.Errorf("winner %d", win.Who)
	}

	var pao play.Option[tile.Seat]
	if win.Pao != nil {
		liable, liableOK := tile.NewSeat(*win.Pao)
		if !liableOK {
			return engine.WinningHand{}, fmt.Errorf("pao %d", *win.Pao)
		}

		pao = play.Some(liable)
	}

	closed := slices.Clone(win.Closed)
	at := slices.Index(closed, win.WinTile)
	if at < 0 {
		return engine.WinningHand{}, fmt.Errorf("the closed tiles hold no winning tile %d", win.WinTile)
	}

	closed = slices.Delete(closed, at, at+1)

	concealed, err := tileIDs(closed)
	if err != nil {
		return engine.WinningHand{}, err
	}

	winTile, err := tileIDs([]int{win.WinTile})
	if err != nil {
		return engine.WinningHand{}, err
	}

	melds, err := meldViews(win.Melds)
	if err != nil {
		return engine.WinningHand{}, err
	}

	dora, err := tileIDs(win.DoraIndicators)
	if err != nil {
		return engine.WinningHand{}, err
	}

	ura, err := tileIDs(win.UraIndicators)
	if err != nil {
		return engine.WinningHand{}, err
	}

	hand := engine.WinningHand{
		Seat:           seat,
		Concealed:      concealed,
		WinTile:        winTile[0],
		Melds:          melds,
		DoraIndicators: dora,
		UraIndicators:  ura,
		Win:            winKind(win),
		FirstTurn:      hasYaku(win, play.YakuTenhou) || hasYaku(win, play.YakuChiihou),
		Pao:            pao,
	}
	isDouble := hasYaku(win, play.YakuDaburuRiichi)
	if isDouble || hasYaku(win, play.YakuRiichi) {
		hand.Riichi = play.Some(play.Riichi{Double: isDouble, Ippatsu: hasYaku(win, play.YakuIppatsu)})
	}

	return hand, nil
}

func tileIDs(ids []int) ([]tile.TileID, error) {
	tiles := make([]tile.TileID, 0, len(ids))
	for _, n := range ids {
		id, ok := tile.NewTileID(n)
		if !ok {
			return nil, fmt.Errorf("tile id %d", n)
		}

		tiles = append(tiles, id)
	}

	return tiles, nil
}

func meldViews(melds []Meld) ([]play.MeldView, error) {
	views := make([]play.MeldView, 0, len(melds))
	for _, m := range melds {
		tiles, err := tileIDs(m.Tiles)
		if err != nil {
			return nil, err
		}

		kind, ok := meldKind(m.Kind)
		if !ok {
			return nil, fmt.Errorf("meld kind %q", m.Kind)
		}

		views = append(views, play.MeldView{Kind: kind, Tiles: tiles})
	}

	return views, nil
}

func meldKind(kind string) (play.MeldKind, bool) {
	switch kind {
	case "chi":
		return play.MeldChi, true
	case "pon":
		return play.MeldPon, true
	case "daiminkan":
		return play.MeldOpenKan, true
	case "chakan":
		return play.MeldAddedKan, true
	case "ankan":
		return play.MeldClosedKan, true
	default:
		return 0, false
	}
}

func winKind(win Win) engine.Win {
	switch {
	case hasYaku(win, play.YakuRinshan):
		return engine.WinRinshan
	case hasYaku(win, play.YakuChankan):
		return engine.WinChankan
	case hasYaku(win, play.YakuHaitei):
		return engine.WinHaitei
	case hasYaku(win, play.YakuHoutei):
		return engine.WinHoutei
	case win.Tsumo:
		return engine.WinTsumo
	default:
		return engine.WinRon
	}
}

func hasYaku(win Win, y play.YakuID) bool {
	id, ok := tenhou.YakuID(y)
	if !ok {
		return false
	}

	if y.IsYakuman() {
		return slices.Contains(win.Yakuman, id)
	}

	return slices.ContainsFunc(win.Yaku, func(yaku [2]int) bool { return yaku[0] == id })
}

func hanFuOf(win Win) (play.Han, bool) {
	if len(win.Yakuman) > 0 {
		return play.Han{}, false
	}

	han := 0
	for _, yaku := range win.Yaku {
		han += yaku[1]
	}

	return play.Han{Han: han, Fu: win.Fu}, true
}

func yakuOf(value engine.HandValue) [][2]int {
	_, isYakuman := value.Value.(play.Yakuman)
	var yaku [][2]int
	for _, y := range value.Yaku {
		id, ok := tenhou.YakuID(y.ID)
		if !ok {
			id = -int(y.ID)
		}

		han := y.Han
		if isYakuman {
			han = 0
		}

		yaku = append(yaku, [2]int{id, han})
	}

	for id, count := range map[int]int{
		tenhou.DoraID:    value.Dora.Dora,
		tenhou.UraDoraID: value.Dora.UraDora,
		tenhou.AkaDoraID: value.Dora.AkaDora,
	} {
		if count > 0 {
			yaku = append(yaku, [2]int{id, count})
		}
	}

	slices.SortFunc(yaku, compareYaku)
	return yaku
}

func wantYaku(win Win) [][2]int {
	var yaku [][2]int
	for _, id := range win.Yakuman {
		yaku = append(yaku, [2]int{id, 0})
	}

	if len(win.Yakuman) == 0 {
		for _, y := range win.Yaku {
			if y[1] > 0 {
				yaku = append(yaku, y)
			}
		}
	}

	slices.SortFunc(yaku, compareYaku)
	return yaku
}

func compareYaku(a, b [2]int) int {
	if a[0] != b[0] {
		return a[0] - b[0]
	}

	return a[1] - b[1]
}

func limitCodeOf(value engine.HandValue) int {
	if !value.Limit.OK {
		return 0
	}

	return tenhou.LimitCode(value.Limit.Value)
}
