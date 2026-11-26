package tenhou

import "github.com/MahjongRepository/ronin/backend/game_v2/engine/play"

const (
	DoraID    = 52
	UraDoraID = 53
	AkaDoraID = 54
)

// YakuID returns the id Tenhou's AGARI lists y by, among the yaku or the yakuman; false for a
// number that is no yaku.
func YakuID(y play.YakuID) (int, bool) {
	switch y {
	case play.YakuTsumo:
		return 0, true
	case play.YakuRiichi:
		return 1, true
	case play.YakuIppatsu:
		return 2, true
	case play.YakuChankan:
		return 3, true
	case play.YakuRinshan:
		return 4, true
	case play.YakuHaitei:
		return 5, true
	case play.YakuHoutei:
		return 6, true
	case play.YakuDaburuRiichi:
		return 21, true
	case play.YakuPinfu:
		return 7, true
	case play.YakuTanyao:
		return 8, true
	case play.YakuIipeikou:
		return 9, true
	case play.YakuHaku:
		return 18, true
	case play.YakuHatsu:
		return 19, true
	case play.YakuChun:
		return 20, true
	case play.YakuSeatWindEast:
		return 10, true
	case play.YakuSeatWindSouth:
		return 11, true
	case play.YakuSeatWindWest:
		return 12, true
	case play.YakuSeatWindNorth:
		return 13, true
	case play.YakuRoundWindEast:
		return 14, true
	case play.YakuRoundWindSouth:
		return 15, true
	case play.YakuRoundWindWest:
		return 16, true
	case play.YakuRoundWindNorth:
		return 17, true
	case play.YakuSanshoku:
		return 25, true
	case play.YakuIttsu:
		return 24, true
	case play.YakuChantai:
		return 23, true
	case play.YakuHonroutou:
		return 31, true
	case play.YakuToitoi:
		return 28, true
	case play.YakuSanankou:
		return 29, true
	case play.YakuSankantsu:
		return 27, true
	case play.YakuSanshokuDoukou:
		return 26, true
	case play.YakuChiitoitsu:
		return 22, true
	case play.YakuShousangen:
		return 30, true
	case play.YakuHonitsu:
		return 34, true
	case play.YakuJunchan:
		return 33, true
	case play.YakuRyanpeikou:
		return 32, true
	case play.YakuChinitsu:
		return 35, true
	case play.YakuKokushiMusou:
		return 47, true
	case play.YakuChuurenPoutou:
		return 45, true
	case play.YakuSuuankou:
		return 40, true
	case play.YakuDaisangen:
		return 39, true
	case play.YakuShousuushii:
		return 50, true
	case play.YakuRyuuiisou:
		return 43, true
	case play.YakuSuukantsu:
		return 51, true
	case play.YakuTsuuiisou:
		return 42, true
	case play.YakuChinroutou:
		return 44, true
	case play.YakuDaisuushii:
		return 49, true
	case play.YakuDaburuKokushiMusou:
		return 48, true
	case play.YakuSuuankouTanki:
		return 41, true
	case play.YakuDaburuChuurenPoutou:
		return 46, true
	case play.YakuTenhou:
		return 37, true
	case play.YakuChiihou:
		return 38, true
	}
	return 0, false
}

// LimitCode returns the limit code of Tenhou's AGARI ten: 1 for mangan to 5 for yakuman. A win
// below mangan has code 0, which no limit returns.
func LimitCode(limit play.Limit) int {
	return int(limit) + 1
}
