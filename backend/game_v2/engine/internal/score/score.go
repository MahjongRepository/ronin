package score

import (
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

type Rules struct {
	OpenTanyao          bool
	DoubleYakuman       bool
	KiriageMangan       bool
	FuForOpenPinfu      bool
	FuForPinfuTsumo     bool
	FuForDoubleWindPair int
	KazoeYakuman        bool
	RiichiStickValue    int
	HonbaValue          int
}

func HandRules(ruleset rules.Ruleset) Rules {
	return Rules{
		OpenTanyao:          ruleset.OpenTanyao,
		DoubleYakuman:       ruleset.DoubleYakuman,
		KiriageMangan:       ruleset.KiriageMangan,
		FuForOpenPinfu:      ruleset.FuForOpenPinfu,
		FuForPinfuTsumo:     ruleset.FuForPinfuTsumo,
		FuForDoubleWindPair: ruleset.FuForDoubleWindPair,
		KazoeYakuman:        ruleset.KazoeYakuman,
		RiichiStickValue:    ruleset.RiichiStickValue,
		HonbaValue:          ruleset.HonbaValue,
	}
}

type Win uint8

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
