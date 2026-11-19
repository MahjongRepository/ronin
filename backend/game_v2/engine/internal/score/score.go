// Package score values a winning hand: it checks the hand and how it was won, scores every reading
// of it on every block the winning tile completes, and keeps the one that pays most. A reading
// scores its yaku from the shape of the hand and the win, its fu from its sets, pair and wait, and
// its dora from the indicators and the red fives; the han and fu then give the limit and who pays
// how much. The rules a game scores by are Rules, the engine's from HandRules.
//
// Ported from mahjong-rs's mahjong-core at commit 0d8733f: the config, dora, fu, scores, yaku
// and hand modules.
//
// The tests check a committed sample of real Tenhou wins against Tenhou's han and fu
// (testdata/tenhou_sample.jsonl.gz, written by extract_tenhou_sample.go). The whole 2025
// phoenix-room corpus, local only, runs behind the tenhou build tag:
//
//	cd backend/game_v2 && mise exec -- go test -tags tenhou ./engine/internal/score -run WholeTenhouCorpus
//
// It reads the agari-000NN.jsonl shards from TENHOU_AGARI_DIR, by default
// ~/work/mahjong-rs/thoughts/_benchmark/agari.
package score

import (
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// Rules are the scoring rules that differ between games. OpenTanyao allows tanyao on an open hand
// (kuitan); DoubleYakuman scores the double-yakuman forms as two yakuman, as one without it;
// Kiriage rounds 4 han 30 fu and 3 han 60 fu up to mangan; FuForOpenPinfu gives an open hand won
// by ron with no other fu 2 fu, so it scores 30 fu, where an open tsumo always gets the 2 tsumo
// fu; FuForPinfuTsumo gives a pinfu hand won by tsumo 2 fu for the tsumo and no pinfu.
type Rules struct {
	OpenTanyao      bool
	DoubleYakuman   bool
	Kiriage         bool
	FuForOpenPinfu  bool
	FuForPinfuTsumo bool
}

// HandRules returns the rules the engine scores by, built from its rule constants: Tenhou's, with
// kuitan, single yakuman for the double forms, no kiriage, open pinfu at 30 fu and no pinfu tsumo
// fu.
func HandRules() Rules {
	return Rules{
		OpenTanyao:      rules.Kuitan,
		DoubleYakuman:   rules.DoubleYakuman,
		Kiriage:         rules.KiriageMangan,
		FuForOpenPinfu:  rules.FuForOpenPinfu,
		FuForPinfuTsumo: rules.FuForPinfuTsumo,
	}
}

// Win is how the winning tile came: ron on a discard, chankan on the tile another player adds to a
// pon to make a kan, houtei on the last discard of the round, tsumo on a tile drawn from the wall,
// rinshan on the replacement tile drawn after a kan, haitei on the last tile of the wall.
type Win uint8

// The wins.
const (
	WinRon Win = iota
	WinChankan
	WinHoutei
	WinTsumo
	WinRinshan
	WinHaitei
)

// IsTsumo reports whether w is won on the winner's own draw: tsumo, rinshan or haitei.
func (w Win) IsTsumo() bool {
	return w == WinTsumo || w == WinRinshan || w == WinHaitei
}

// Situation is everything about a win that the tiles do not show. Riichi is the winner's riichi,
// absent without one. FirstTurn marks a win before the winner's first discard with no call made:
// tenhou for the dealer's tsumo, chiihou for another player's. East is the dealer's seat wind.
// Honba are the repeat counters, 300 points each on a ron and 100 from each payer on a tsumo, and
// RiichiSticks the sticks on the table, 1000 points each to the winner; both count 0 or more. The
// zero value is a ron by the dealer in an East round, with no riichi, honba or sticks.
type Situation struct {
	Win          Win
	Riichi       play.Option[play.Riichi]
	FirstTurn    bool
	SeatWind     tile.Wind
	RoundWind    tile.Wind
	Honba        int
	RiichiSticks int
}

// IsDealer reports whether the winner is the dealer: its seat wind is East.
func (s Situation) IsDealer() bool {
	return s.SeatWind == tile.East
}
