package play

// YakuID is a yaku, numbered by its yaku id: 0 to 39 regular, 100 to 116 yakuman, some unused.
// Only the named constants are yaku; any other number has no name and no han.
type YakuID uint8

const (
	YakuTsumo               YakuID = 0
	YakuRiichi              YakuID = 1
	YakuIppatsu             YakuID = 3
	YakuChankan             YakuID = 4
	YakuRinshan             YakuID = 5
	YakuHaitei              YakuID = 6
	YakuHoutei              YakuID = 7
	YakuDaburuRiichi        YakuID = 8
	YakuPinfu               YakuID = 12
	YakuTanyao              YakuID = 13
	YakuIipeikou            YakuID = 14
	YakuHaku                YakuID = 15
	YakuHatsu               YakuID = 16
	YakuChun                YakuID = 17
	YakuSeatWindEast        YakuID = 18
	YakuSeatWindSouth       YakuID = 19
	YakuSeatWindWest        YakuID = 20
	YakuSeatWindNorth       YakuID = 21
	YakuRoundWindEast       YakuID = 22
	YakuRoundWindSouth      YakuID = 23
	YakuRoundWindWest       YakuID = 24
	YakuRoundWindNorth      YakuID = 25
	YakuSanshoku            YakuID = 26
	YakuIttsu               YakuID = 27
	YakuChantai             YakuID = 28
	YakuHonroutou           YakuID = 29
	YakuToitoi              YakuID = 30
	YakuSanankou            YakuID = 31
	YakuSankantsu           YakuID = 32
	YakuSanshokuDoukou      YakuID = 33
	YakuChiitoitsu          YakuID = 34
	YakuShousangen          YakuID = 35
	YakuHonitsu             YakuID = 36
	YakuJunchan             YakuID = 37
	YakuRyanpeikou          YakuID = 38
	YakuChinitsu            YakuID = 39
	YakuKokushiMusou        YakuID = 100
	YakuChuurenPoutou       YakuID = 101
	YakuSuuankou            YakuID = 102
	YakuDaisangen           YakuID = 103
	YakuShousuushii         YakuID = 104
	YakuRyuuiisou           YakuID = 105
	YakuSuukantsu           YakuID = 106
	YakuTsuuiisou           YakuID = 107
	YakuChinroutou          YakuID = 108
	YakuDaisuushii          YakuID = 111
	YakuDaburuKokushiMusou  YakuID = 112
	YakuSuuankouTanki       YakuID = 113
	YakuDaburuChuurenPoutou YakuID = 114
	YakuTenhou              YakuID = 115
	YakuChiihou             YakuID = 116
)

const YakuCount = 51

type yakuData struct {
	name      string
	hanOpen   int
	hanClosed int
}

// AllYaku returns every yaku in yaku id order.
func AllYaku() [YakuCount]YakuID {
	return allYaku
}

// Name returns y's English name, such as "Menzen Tsumo".
func (y YakuID) Name() string {
	return yakuTable[y].name
}

// HanOpen returns y's han on an open hand; false for a yaku that needs a closed hand.
func (y YakuID) HanOpen() (int, bool) {
	han := yakuTable[y].hanOpen
	return han, han != 0
}

// HanClosed returns y's han on a closed hand, 13 for a yakuman and 26 for a double yakuman form.
func (y YakuID) HanClosed() int {
	return yakuTable[y].hanClosed
}

// IsYakuman reports whether y is a yakuman: its id is 100 or above.
func (y YakuID) IsYakuman() bool {
	return y >= YakuKokushiMusou
}

// IsDoubleYakuman reports whether y is one of the forms worth two yakuman when double yakuman is
// on; they keep their names and count 13 han without it.
func (y YakuID) IsDoubleYakuman() bool {
	return y == YakuDaburuKokushiMusou || y == YakuSuuankouTanki || y == YakuDaburuChuurenPoutou ||
		y == YakuDaisuushii
}
