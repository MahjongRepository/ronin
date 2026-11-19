package play

// YakuID is a yaku, numbered by its yaku id: 0 to 39 for regular yaku, 100 to 116 for yakuman,
// some numbers in those ranges unused. Only the named constants are yaku; any other number has no
// name, no han and no Tenhou id. Chantai is a terminal or honor in every set and Junchan a
// terminal in every set, each with at least one chi; Daisuushii, DaburuKokushiMusou (won on a
// thirteen-sided wait), SuuankouTanki (won on the pair) and DaburuChuurenPoutou (won on a
// nine-sided wait) are the double yakuman forms.
type YakuID uint8

// The yaku, in yaku id order.
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

// YakuCount is the number of yaku.
const YakuCount = 51

type yakuData struct {
	name      string
	hanOpen   int
	hanClosed int
	tenhouID  int
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

// TenhouID returns the id Tenhou lists y by in its AGARI yaku.
func (y YakuID) TenhouID() int {
	return yakuTable[y].tenhouID
}

// DoraKind is a kind of dora a winning hand counts beside its yaku, which Tenhou's AGARI lists
// among the yaku by their own ids.
type DoraKind uint8

// The dora kinds, in Tenhou id order.
const (
	Dora DoraKind = iota
	UraDora
	AkaDora
)

const doraKindTenhouStart = 52

// AllDoraKinds returns every dora kind in Tenhou id order.
func AllDoraKinds() [3]DoraKind {
	return [3]DoraKind{Dora, UraDora, AkaDora}
}

// Name returns k's English name: "Dora", "Ura Dora" or "Aka Dora".
func (k DoraKind) Name() string {
	switch k {
	case Dora:
		return "Dora"
	case UraDora:
		return "Ura Dora"
	case AkaDora:
		return "Aka Dora"
	default:
		return ""
	}
}

// TenhouID returns the id Tenhou lists k's count by, past every yaku's: 52 dora, 53 ura dora, 54
// aka dora.
func (k DoraKind) TenhouID() int {
	return doraKindTenhouStart + int(k)
}

// DoraKindFromTenhouID returns the dora kind of a Tenhou id; false for any id but 52 to 54.
func DoraKindFromTenhouID(id int) (DoraKind, bool) {
	kind := id - doraKindTenhouStart
	if kind < int(Dora) || kind > int(AkaDora) {
		return Dora, false
	}
	return DoraKind(kind), true
}
